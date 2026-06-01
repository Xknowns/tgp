#!/usr/bin/env python3
"""
tgp/task.py -- Task Model and Validation (Layer 2: Protocol)

Implements the TGP data model and validation logic for all object kinds:
    - task: A unit of computational work with inputs, environment, command, outputs
    - artifact: An immutable data object (blob, tree, or exec)
    - environment: Execution environment (container, native, wasm)
    - graph: A DAG of tasks as a collection of task references

Validation enforces all field rules from the TGP specification, ensuring
that objects are well-formed before they enter the CAS or execution pipeline.

Specification reference: Section 3 (Data Model)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from tgp.core import ValidationError, verify_id


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class TaskInput:
    """An input artifact reference for a task.

    Attributes:
        name: Local name the task uses to reference this input.
        ref: Content-addressed ID of the input artifact (sha256:...).
        required: If True, the input must exist before the task can execute.
    """
    name: str
    ref: str
    required: bool = True


@dataclass
class TaskOutput:
    """An expected output artifact from a task.

    Attributes:
        path: Absolute path where the task writes its output.
        expected_hash: Optional sha256:... hash the output must match.
        optional: If True, the output is not required for task success.
    """
    path: str
    expected_hash: Optional[str] = None
    optional: bool = False


@dataclass
class TaskEnvironment:
    """Execution environment specification for a task.

    Attributes:
        type: Environment type - "container", "native", or "wasm".
        image: For containers, content-addressed image ID (sha256:...).
        platform: Target platform (e.g., "linux/amd64", "linux/arm64").
    """
    type: str  # "container", "native", "wasm"
    image: Optional[str] = None
    platform: Optional[str] = None


@dataclass
class TaskResources:
    """Resource requirements for task execution.

    Attributes:
        cpu: Number of CPU cores (string, e.g., "1", "2").
        memory: Memory limit (string, e.g., "256Mi", "4Gi").
        timeout: Maximum execution time (string, e.g., "60s", "300s").
    """
    cpu: str = "1"
    memory: str = "1Gi"
    timeout: str = "300s"


@dataclass
class Task:
    """A TGP task definition.

    A task is a unit of computational work that transforms input artifacts
    into output artifacts within a specified environment.

    Attributes:
        kind: Always "task".
        inputs: List of input artifact references.
        environment: Execution environment specification.
        command: Command array to execute.
        outputs: List of expected output artifacts.
        resources: Resource requirements.
        labels: Optional key-value labels for organization.
    """
    kind: str = "task"
    inputs: List[TaskInput] = field(default_factory=list)
    environment: TaskEnvironment = field(default_factory=lambda: TaskEnvironment(type="native"))
    command: List[str] = field(default_factory=list)
    outputs: List[TaskOutput] = field(default_factory=list)
    resources: TaskResources = field(default_factory=TaskResources)
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dict suitable for CAS storage."""
        return {
            "kind": self.kind,
            "inputs": [
                {"name": inp.name, "ref": inp.ref, "required": inp.required}
                for inp in self.inputs
            ],
            "environment": {
                k: v for k, v in {
                    "type": self.environment.type,
                    "image": self.environment.image,
                    "platform": self.environment.platform,
                }.items() if v is not None
            },
            "command": self.command,
            "outputs": [
                {
                    k: v for k, v in {
                        "path": out.path,
                        "expected_hash": out.expected_hash,
                        "optional": out.optional,
                    }.items() if v is not None
                }
                for out in self.outputs
            ],
            "resources": {
                "cpu": self.resources.cpu,
                "memory": self.resources.memory,
                "timeout": self.resources.timeout,
            },
            "labels": self.labels,
        }


@dataclass
class Artifact:
    """An immutable artifact produced by task execution.

    Artifacts are content-addressed and include provenance tracking via
    the created_by field, which references the task that produced them.

    Attributes:
        kind: Always "artifact".
        type: Artifact type - "blob", "tree", or "exec".
        size: Size in bytes.
        content_type: MIME content type.
        created_by: ID of the task that produced this artifact.
    """
    kind: str = "artifact"
    type: str = "blob"  # "blob", "tree", "exec"
    size: int = 0
    content_type: str = "application/octet-stream"
    refs: List[str] = field(default_factory=list)  # For tree artifacts
    created_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dict suitable for CAS storage."""
        result: Dict[str, Any] = {
            "kind": self.kind,
            "type": self.type,
            "size": self.size,
            "content_type": self.content_type,
        }
        if self.refs:
            result["refs"] = self.refs
        if self.created_by:
            result["created_by"] = self.created_by
        return result


# ============================================================================
# VALIDATOR
# ============================================================================

class TaskValidator:
    """Validates TGP objects against the specification.

    The validator enforces all field rules from Section 3 of the TGP spec:
        - Required fields must be present
        - References must be valid sha256:... content addresses
        - Environment images must be content-addressed (not tag-based)
        - IDs must match computed content hashes
        - Kinds must be from the supported set

    Usage:
        >>> validator = TaskValidator()
        >>> validator.validate(task_dict)  # Raises ValidationError if invalid

    All validate_* methods raise ValidationError on failure and return
    None on success (Python convention for validation functions).
    """

    # Supported object kinds per spec Section 3
    REQUIRED_TASK_FIELDS: Set[str] = {"kind", "inputs", "environment", "command", "outputs"}
    VALID_KINDS: Set[str] = {"task", "artifact", "environment", "graph"}
    VALID_ENV_TYPES: Set[str] = {"container", "native", "wasm"}
    VALID_ARTIFACT_TYPES: Set[str] = {"blob", "tree", "exec"}

    @classmethod
    def validate(cls, obj: Any) -> None:
        """Validate any TGP object.

        Routes to the appropriate kind-specific validator and then
        verifies the object's content-addressed ID.

        Args:
            obj: A dict representing a TGP object (task, artifact, etc.)

        Raises:
            ValidationError: If the object fails any validation check.
        """
        if not isinstance(obj, dict):
            raise ValidationError(
                "TGP object must be a JSON object (dict), got: " + str(type(obj))
            )

        if "kind" not in obj:
            raise ValidationError("Missing required field: 'kind'")

        kind = obj["kind"]
        if kind not in cls.VALID_KINDS:
            raise ValidationError(
                "Invalid kind: '" + str(kind) + "'. " +
                "Must be one of: " + str(sorted(cls.VALID_KINDS))
            )

        # Route to kind-specific validator
        if kind == "task":
            cls._validate_task(obj)
        elif kind == "artifact":
            cls._validate_artifact(obj)
        elif kind == "environment":
            cls._validate_environment(obj)
        elif kind == "graph":
            cls._validate_graph(obj)

        # Verify content-addressed ID
        if "id" in obj and not verify_id(obj):
            raise ValidationError(
                "ID verification failed for object " + obj.get("id", "NO_ID") +
                ": computed hash does not match stored id"
            )

    @classmethod
    def _validate_task(cls, obj: Dict[str, Any]) -> None:
        """Validate a task object per spec Section 3.1.

        Checks:
            - Required fields: kind, inputs, environment, command, outputs
            - Each input has 'name' and 'ref' fields
            - Each input ref is a valid sha256:... content address
            - Environment type is valid (container/native/wasm)
            - Container environment has content-addressed image
            - Each output has a 'path' field
        """
        missing = cls.REQUIRED_TASK_FIELDS - set(obj.keys())
        if missing:
            raise ValidationError(
                "Task missing required fields: " + str(sorted(missing))
            )

        # Validate inputs
        inputs = obj.get("inputs", [])
        if not isinstance(inputs, list):
            raise ValidationError("'inputs' must be a list")
        for i, inp in enumerate(inputs):
            if not isinstance(inp, dict):
                raise ValidationError(
                    "Task input " + str(i) + " must be an object, got: " + str(type(inp))
                )
            if "name" not in inp:
                raise ValidationError("Task input " + str(i) + " missing 'name' field")
            if "ref" not in inp:
                raise ValidationError("Task input " + str(i) + " missing 'ref' field")
            ref = inp["ref"]
            if not isinstance(ref, str) or not ref.startswith("sha256:"):
                raise ValidationError(
                    "Task input " + str(i) + " has invalid ref: " + str(ref) +
                    ". Expected format: sha256:<64-hex-chars>"
                )

        # Validate environment
        env = obj.get("environment", {})
        if not isinstance(env, dict):
            raise ValidationError("'environment' must be an object")
        env_type = env.get("type")
        if env_type not in cls.VALID_ENV_TYPES:
            raise ValidationError(
                "Invalid environment type: '" + str(env_type) + "'. " +
                "Must be one of: " + str(sorted(cls.VALID_ENV_TYPES))
            )
        if env_type == "container":
            image = env.get("image", "")
            if not isinstance(image, str) or not image.startswith("sha256:"):
                raise ValidationError(
                    "Container environment must use content-addressed image " +
                    "(sha256:...), got: " + str(image)
                )

        # Validate command
        command = obj.get("command", [])
        if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
            raise ValidationError("'command' must be a list of strings")

        # Validate outputs
        outputs = obj.get("outputs", [])
        if not isinstance(outputs, list):
            raise ValidationError("'outputs' must be a list")
        for i, out in enumerate(outputs):
            if not isinstance(out, dict):
                raise ValidationError(
                    "Task output " + str(i) + " must be an object, got: " + str(type(out))
                )
            if "path" not in out:
                raise ValidationError("Task output " + str(i) + " missing 'path' field")

    @classmethod
    def _validate_artifact(cls, obj: Dict[str, Any]) -> None:
        """Validate an artifact object per spec Section 3.2.

        Checks:
            - Required fields: type, size
            - Type is one of: blob, tree, exec
            - size is a non-negative integer
        """
        if "type" not in obj:
            raise ValidationError("Artifact missing 'type' field")
        if obj["type"] not in cls.VALID_ARTIFACT_TYPES:
            raise ValidationError(
                "Invalid artifact type: '" + str(obj["type"]) + "'. " +
                "Must be one of: " + str(sorted(cls.VALID_ARTIFACT_TYPES))
            )
        if "size" not in obj:
            raise ValidationError("Artifact missing 'size' field")
        if not isinstance(obj["size"], int) or obj["size"] < 0:
            raise ValidationError(
                "Artifact size must be a non-negative integer, got: " + str(obj["size"])
            )

    @classmethod
    def _validate_environment(cls, obj: Dict[str, Any]) -> None:
        """Validate an environment object per spec Section 3.3.

        Checks:
            - Required field: type
            - Container environments have 'layers' field with sha256 refs
        """
        if "type" not in obj:
            raise ValidationError("Environment missing 'type' field")
        env_type = obj["type"]
        if env_type not in cls.VALID_ENV_TYPES:
            raise ValidationError(
                "Invalid environment type: '" + str(env_type) + "'. " +
                "Must be one of: " + str(sorted(cls.VALID_ENV_TYPES))
            )
        if env_type == "container":
            if "layers" not in obj:
                raise ValidationError("Container environment missing 'layers' field")
            layers = obj["layers"]
            if not isinstance(layers, list):
                raise ValidationError("'layers' must be a list")
            for i, layer in enumerate(layers):
                if not isinstance(layer, str) or not layer.startswith("sha256:"):
                    raise ValidationError(
                        "Layer " + str(i) + " has invalid ref: " + str(layer) +
                        ". Expected format: sha256:<64-hex-chars>"
                    )

    @classmethod
    def _validate_graph(cls, obj: Dict[str, Any]) -> None:
        """Validate a graph object per spec Section 3.4.

        Checks:
            - Required fields: root, tasks
            - tasks is a non-empty list
            - Each task reference is a valid sha256:... content address
        """
        if "root" not in obj:
            raise ValidationError("Graph missing 'root' field")
        if "tasks" not in obj:
            raise ValidationError("Graph missing 'tasks' field")
        tasks = obj["tasks"]
        if not isinstance(tasks, list) or not tasks:
            raise ValidationError("Graph 'tasks' must be a non-empty list")
        for i, task_id in enumerate(tasks):
            if not isinstance(task_id, str) or not task_id.startswith("sha256:"):
                raise ValidationError(
                    "Graph task " + str(i) + " has invalid ref: " + str(task_id) +
                    ". Expected format: sha256:<64-hex-chars>"
                )

    @classmethod
    def validate_ref(cls, ref: str, context: str = "ref") -> None:
        """Validate a content-addressed reference string.

        Args:
            ref: The reference string to validate (e.g., "sha256:abc123...").
            context: Description of what this ref is for (used in error messages).

        Raises:
            ValidationError: If ref is not a valid sha256:... content address.
        """
        if not isinstance(ref, str) or not ref.startswith("sha256:"):
            raise ValidationError(
                "Invalid " + context + ": " + str(ref) +
                ". Expected format: sha256:<64-hex-chars>"
            )
