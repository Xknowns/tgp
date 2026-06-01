#!/usr/bin/env python3
"""
tests/test_task.py -- Tests for Task Model and Validation

Validates:
    - Task validation (required fields, input refs, environment, outputs)
    - Artifact validation (type, size)
    - Environment validation (type, layers for containers)
    - Graph validation (root, tasks, task refs)
    - ID verification during validation
    - Invalid objects are rejected with clear errors
"""

import pytest
from tgp.task import TaskValidator, Task, TaskInput, TaskOutput, TaskEnvironment, TaskResources
from tgp.core import ValidationError, compute_id


class TestTaskValidation:
    """Test task object validation per spec Section 3.1."""

    def test_valid_task(self):
        """A well-formed task passes validation."""
        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "src", "ref": "sha256:" + "a" * 64, "required": True}],
            "environment": {"type": "native"},
            "command": ["gcc", "main.c"],
            "outputs": [{"path": "/out/main", "expected_hash": "sha256:" + "b" * 64}],
            "id": "PLACEHOLDER",
        }
        task["id"] = compute_id(task)
        TaskValidator.validate(task)

    def test_valid_task_with_resources_and_labels(self):
        """Task with all optional fields passes."""
        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native", "platform": "linux/amd64"},
            "command": ["echo", "hello"],
            "outputs": [{"path": "/out/log", "optional": True}],
            "resources": {"cpu": "2", "memory": "4Gi", "timeout": "300s"},
            "labels": {"project": "myapp", "stage": "build"},
            "id": "PLACEHOLDER",
        }
        task["id"] = compute_id(task)
        TaskValidator.validate(task)

    def test_missing_kind(self):
        """Task without 'kind' field fails."""
        task = {"command": ["echo"], "inputs": [], "environment": {"type": "native"}, "outputs": []}
        with pytest.raises(ValidationError, match="kind"):
            TaskValidator.validate(task)

    def test_missing_required_fields(self):
        """Task missing required fields fails."""
        task = {"kind": "task"}
        with pytest.raises(ValidationError, match="required fields"):
            TaskValidator.validate(task)

    def test_invalid_kind(self):
        """Task with invalid kind fails."""
        task = {
            "kind": "invalid_kind",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["echo"],
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="Invalid kind"):
            TaskValidator.validate(task)

    def test_input_missing_name(self):
        """Input without 'name' field fails."""
        task = {
            "kind": "task",
            "inputs": [{"ref": "sha256:abc"}],
            "environment": {"type": "native"},
            "command": ["echo"],
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="name"):
            TaskValidator.validate(task)

    def test_input_missing_ref(self):
        """Input without 'ref' field fails."""
        task = {
            "kind": "task",
            "inputs": [{"name": "src"}],
            "environment": {"type": "native"},
            "command": ["echo"],
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="ref"):
            TaskValidator.validate(task)

    def test_input_invalid_ref_format(self):
        """Input with non-sha256 ref fails."""
        task = {
            "kind": "task",
            "inputs": [{"name": "src", "ref": "not-sha256"}],
            "environment": {"type": "native"},
            "command": ["echo"],
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="(?i)invalid ref"):
            TaskValidator.validate(task)

    def test_input_valid_sha256_ref(self):
        """Input with valid sha256 ref passes."""
        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "src", "ref": "sha256:" + "a" * 64}],
            "environment": {"type": "native"},
            "command": ["echo"],
            "outputs": [],
            "id": "PLACEHOLDER",
        }
        task["id"] = compute_id(task)
        TaskValidator.validate(task)

    def test_environment_invalid_type(self):
        """Environment with invalid type fails."""
        task = {
            "kind": "task",
            "inputs": [],
            "environment": {"type": "invalid"},
            "command": ["echo"],
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="Invalid environment type"):
            TaskValidator.validate(task)

    def test_container_missing_image(self):
        """Container environment without content-addressed image fails."""
        task = {
            "kind": "task",
            "inputs": [],
            "environment": {"type": "container"},
            "command": ["echo"],
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="content-addressed image"):
            TaskValidator.validate(task)

    def test_container_with_valid_image(self):
        """Container environment with sha256 image passes."""
        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "container", "image": "sha256:" + "a" * 64},
            "command": ["echo"],
            "outputs": [],
            "id": "PLACEHOLDER",
        }
        task["id"] = compute_id(task)
        TaskValidator.validate(task)

    def test_command_must_be_list(self):
        """Command must be a list."""
        task = {
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": "echo",
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="list of strings"):
            TaskValidator.validate(task)

    def test_command_must_be_strings(self):
        """Command must be a list of strings."""
        task = {
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["echo", 123],
            "outputs": [],
        }
        with pytest.raises(ValidationError, match="list of strings"):
            TaskValidator.validate(task)

    def test_output_missing_path(self):
        """Output without 'path' field fails."""
        task = {
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["echo"],
            "outputs": [{"expected_hash": "sha256:abc"}],
        }
        with pytest.raises(ValidationError, match="path"):
            TaskValidator.validate(task)

    def test_invalid_id_fails(self):
        """Task with incorrect ID fails validation."""
        task = {
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["echo"],
            "outputs": [],
            "id": "sha256:" + "0" * 64,  # Wrong hash
        }
        with pytest.raises(ValidationError, match="ID verification failed"):
            TaskValidator.validate(task)

    def test_non_dict_input(self):
        """Non-dict object fails validation."""
        with pytest.raises(ValidationError, match="must be a JSON object"):
            TaskValidator.validate("not a dict")

    def test_all_environment_types(self):
        """All valid environment types pass."""
        for env_type in ["native", "wasm"]:
            task = {
                "tgp_version": "1.0.0",
                "kind": "task",
                "inputs": [],
                "environment": {"type": env_type},
                "command": ["echo"],
                "outputs": [],
                "id": "PLACEHOLDER",
            }
            task["id"] = compute_id(task)
            TaskValidator.validate(task)


class TestArtifactValidation:
    """Test artifact object validation per spec Section 3.2."""

    def test_valid_blob_artifact(self):
        """Well-formed blob artifact passes."""
        artifact = {
            "tgp_version": "1.0.0",
            "kind": "artifact",
            "type": "blob",
            "size": 1024,
            "id": "PLACEHOLDER",
        }
        artifact["id"] = compute_id(artifact)
        TaskValidator.validate(artifact)

    def test_valid_tree_artifact(self):
        """Well-formed tree artifact passes."""
        artifact = {
            "tgp_version": "1.0.0",
            "kind": "artifact",
            "type": "tree",
            "size": 0,
            "refs": ["sha256:" + "a" * 64],
            "id": "PLACEHOLDER",
        }
        artifact["id"] = compute_id(artifact)
        TaskValidator.validate(artifact)

    def test_missing_type(self):
        """Artifact without 'type' fails."""
        artifact = {"kind": "artifact", "size": 100}
        with pytest.raises(ValidationError, match="type"):
            TaskValidator.validate(artifact)

    def test_invalid_type(self):
        """Artifact with invalid type fails."""
        artifact = {"kind": "artifact", "type": "invalid", "size": 100}
        with pytest.raises(ValidationError, match="Invalid artifact type"):
            TaskValidator.validate(artifact)

    def test_missing_size(self):
        """Artifact without 'size' fails."""
        artifact = {"kind": "artifact", "type": "blob"}
        with pytest.raises(ValidationError, match="size"):
            TaskValidator.validate(artifact)

    def test_negative_size(self):
        """Artifact with negative size fails."""
        artifact = {"kind": "artifact", "type": "blob", "size": -1}
        with pytest.raises(ValidationError, match="non-negative"):
            TaskValidator.validate(artifact)


class TestEnvironmentValidation:
    """Test environment object validation per spec Section 3.3."""

    def test_valid_native_environment(self):
        """Well-formed native environment passes."""
        env = {
            "tgp_version": "1.0.0",
            "kind": "environment",
            "type": "native",
            "id": "PLACEHOLDER",
        }
        env["id"] = compute_id(env)
        TaskValidator.validate(env)

    def test_valid_container_environment(self):
        """Well-formed container environment passes."""
        env = {
            "tgp_version": "1.0.0",
            "kind": "environment",
            "type": "container",
            "layers": ["sha256:" + "a" * 64],
            "config": {"entrypoint": [], "env": {"KEY": "VALUE"}, "working_dir": "/workspace"},
            "id": "PLACEHOLDER",
        }
        env["id"] = compute_id(env)
        TaskValidator.validate(env)

    def test_container_missing_layers(self):
        """Container environment without layers fails."""
        env = {"kind": "environment", "type": "container"}
        with pytest.raises(ValidationError, match="layers"):
            TaskValidator.validate(env)

    def test_container_invalid_layer_ref(self):
        """Container with invalid layer ref fails."""
        env = {
            "kind": "environment",
            "type": "container",
            "layers": ["not-sha256"],
        }
        with pytest.raises(ValidationError, match="(?i)invalid ref"):
            TaskValidator.validate(env)


class TestGraphValidation:
    """Test graph object validation per spec Section 3.4."""

    def test_valid_graph(self):
        """Well-formed graph passes."""
        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": "sha256:" + "a" * 64,
            "tasks": ["sha256:" + "b" * 64, "sha256:" + "c" * 64],
            "metadata": {"name": "build", "description": "Build pipeline"},
            "id": "PLACEHOLDER",
        }
        graph["id"] = compute_id(graph)
        TaskValidator.validate(graph)

    def test_missing_root(self):
        """Graph without 'root' fails."""
        graph = {"kind": "graph", "tasks": ["sha256:abc"]}
        with pytest.raises(ValidationError, match="root"):
            TaskValidator.validate(graph)

    def test_missing_tasks(self):
        """Graph without 'tasks' fails."""
        graph = {"kind": "graph", "root": "sha256:abc"}
        with pytest.raises(ValidationError, match="tasks"):
            TaskValidator.validate(graph)

    def test_empty_tasks(self):
        """Graph with empty tasks list fails."""
        graph = {"kind": "graph", "root": "sha256:abc", "tasks": []}
        with pytest.raises(ValidationError, match="empty"):
            TaskValidator.validate(graph)

    def test_invalid_task_ref(self):
        """Graph with invalid task ref fails."""
        graph = {
            "kind": "graph",
            "root": "sha256:" + "a" * 64,
            "tasks": ["not-sha256"],
        }
        with pytest.raises(ValidationError, match="(?i)invalid ref"):
            TaskValidator.validate(graph)


class TestDataclasses:
    """Test the dataclass helpers."""

    def test_task_to_dict(self):
        """Task dataclass converts to dict."""
        task = Task(
            inputs=[TaskInput(name="src", ref="sha256:" + "a" * 64)],
            environment=TaskEnvironment(type="native"),
            command=["echo", "hi"],
            outputs=[TaskOutput(path="/out/result")],
        )
        d = task.to_dict()
        assert d["kind"] == "task"
        assert d["inputs"][0]["name"] == "src"
        assert d["command"] == ["echo", "hi"]

    def test_task_defaults(self):
        """Task has sensible defaults."""
        task = Task()
        assert task.kind == "task"
        assert task.inputs == []
        assert task.environment.type == "native"

    def test_resources_defaults(self):
        """TaskResources has correct defaults."""
        res = TaskResources()
        assert res.cpu == "1"
        assert res.memory == "1Gi"
        assert res.timeout == "300s"
