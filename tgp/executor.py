#!/usr/bin/env python3
"""
tgp/executor.py -- Task Execution Backends (Layer 3: Orchestration)

Provides pluggable task execution backends:
    - NativeExecutor: Run commands directly on the host
    - ContainerExecutor: Run commands in Docker containers (stub for v1.0.0)
    - WasmExecutor: Run WASM modules (stub for v1.0.0)

The executor interface abstracts how a task is run, while the scheduler
decides *when* to run it. This separation allows swapping execution
strategies without changing the orchestration logic.

Specification reference: Section 6 (Execution Semantics)
"""

import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from tgp.core import ExecutionError


class BaseExecutor(ABC):
    """Abstract base class for task executors.

    All executors must implement execute() which takes a task definition
    and returns a list of output artifact IDs.
    """

    def __init__(self, cas: Any) -> None:
        """Initialize the executor with a CAS for artifact storage/retrieval.

        Args:
            cas: A CAS instance for fetching inputs and storing outputs.
        """
        self.cas = cas

    @abstractmethod
    def execute(
        self, task: Dict[str, Any], completed_results: Dict[str, List[str]]
    ) -> List[str]:
        """Execute a task and return output artifact IDs.

        Args:
            task: The task dict to execute.
            completed_results: Results from already-executed tasks.

        Returns:
            List of output artifact IDs produced by this task.

        Raises:
            ExecutionError: If the task fails to execute.
        """
        pass


class NativeExecutor(BaseExecutor):
    """Execute tasks natively on the host system.

    Commands run in temporary directories with input artifacts resolved
    from the CAS and output artifacts captured, hashed, and stored.

    This is the reference implementation executor and the fallback for
    other execution strategies.
    """

    def execute(
        self, task: Dict[str, Any], completed_results: Dict[str, List[str]]
    ) -> List[str]:
        """Execute a task natively in a temporary directory.

        Steps:
            1. Create a temporary working directory
            2. Fetch input artifacts from CAS and write to temp dir
            3. Pre-create output directories
            4. Execute the command with configurable timeout
            5. Read output files, hash them, store in CAS
            6. Verify expected hashes if specified

        Args:
            task: Task dict with inputs, command, outputs, resources.
            completed_results: Results from prior tasks (for ref resolution).

        Returns:
            List of output artifact IDs.

        Raises:
            ExecutionError: On command failure, timeout, or hash mismatch.
        """
        cmd = task.get("command", [])
        if not cmd:
            raise ExecutionError("Task has no command to execute")

        # Parse timeout from resources
        timeout = self._parse_timeout(task.get("resources", {}))

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Resolve inputs from CAS
            self._resolve_inputs(task.get("inputs", []), tmpdir)

            # Step 2: Pre-create output directories
            self._prepare_outputs(task.get("outputs", []), tmpdir)

            # Step 3: Execute command
            self._run_command(cmd, tmpdir, timeout)

            # Step 4: Capture and store outputs
            return self._capture_outputs(task.get("outputs", []), tmpdir)

    def _parse_timeout(self, resources: Dict[str, Any]) -> int:
        """Extract timeout in seconds from resources dict.

        Args:
            resources: Task resources dict, may contain 'timeout' key.

        Returns:
            Timeout in seconds (default: 300).
        """
        if "timeout" not in resources:
            return 300
        timeout_val = resources["timeout"]
        if isinstance(timeout_val, str):
            if timeout_val.endswith("s"):
                return int(timeout_val[:-1])
            try:
                return int(timeout_val)
            except ValueError:
                return 300
        elif isinstance(timeout_val, (int, float)):
            return int(timeout_val)
        return 300

    def _resolve_inputs(self, inputs: List[Dict[str, Any]], tmpdir: str) -> None:
        """Fetch input artifacts from CAS and write to working directory.

        Args:
            inputs: List of input dicts with 'name' and 'ref' keys.
            tmpdir: Path to temporary working directory.

        Raises:
            ExecutionError: If an input artifact cannot be fetched.
        """
        for inp in inputs:
            ref = inp["ref"]
            name = inp["name"]
            try:
                data = self.cas.get(ref)
            except Exception as e:
                raise ExecutionError(
                    "Failed to resolve input '" + name + "' (" + ref + "): " + str(e)
                )
            input_path = Path(tmpdir) / name
            input_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_bytes(data)

    def _prepare_outputs(self, outputs: List[Dict[str, Any]], tmpdir: str) -> None:
        """Pre-create output directories so commands have somewhere to write.

        Args:
            outputs: List of output dicts with 'path' keys.
            tmpdir: Path to temporary working directory.
        """
        for out in outputs:
            out_path = Path(tmpdir) / out["path"].lstrip("/")
            out_path.parent.mkdir(parents=True, exist_ok=True)

    def _run_command(self, cmd, cwd, timeout):
        """Execute a command in a working directory.

        Args:
            cmd: Command list to execute.
            cwd: Working directory path.
            timeout: Timeout in seconds.

        Returns:
            subprocess.CompletedProcess result.

        Raises:
            ExecutionError: On command failure or timeout.
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=True
            )
            if result.returncode != 0:
                raise ExecutionError(
                    "Command failed with exit code " + str(result.returncode) +
                    ": " + result.stderr
                )
            return result
        except subprocess.TimeoutExpired:
            raise ExecutionError("Task timed out")

    def _capture_outputs(
        self, outputs: List[Dict[str, Any]], tmpdir: str
    ) -> List[str]:
        """Read output files, hash them, store in CAS, verify expected hashes.

        Args:
            outputs: List of output dicts with 'path', 'expected_hash', 'optional'.
            tmpdir: Working directory path.

        Returns:
            List of output artifact IDs.

        Raises:
            ExecutionError: If a required output is missing or hash mismatch.
        """
        output_ids: List[str] = []
        for out in outputs:
            out_path = Path(tmpdir) / out["path"].lstrip("/")
            if not out_path.exists():
                if out.get("optional"):
                    continue
                raise ExecutionError("Required output not found: " + out["path"])

            data = out_path.read_bytes()
            obj_id = self.cas.put(data)

            # Verify expected hash if specified
            expected = out.get("expected_hash")
            if expected and obj_id != expected:
                raise ExecutionError(
                    "Output hash mismatch for " + out["path"] +
                    ": expected " + expected + ", got " + obj_id
                )

            output_ids.append(obj_id)

        return output_ids


class ContainerExecutor(BaseExecutor):
    """Execute tasks in Docker containers.

    This is a STUB for v1.0.0. The reference implementation uses native
    execution. A full container executor would:
        - Pull content-addressed images
        - Mount input artifacts as volumes
        - Capture output files from the container
        - Handle platform constraints

    Future implementations should subclass this and override execute().
    """

    def execute(
        self, task: Dict[str, Any], completed_results: Dict[str, List[str]]
    ) -> List[str]:
        """Stub: falls back to native execution with a warning.

        Args:
            task: Task dict to execute.
            completed_results: Results from prior tasks.

        Returns:
            List of output artifact IDs from native fallback execution.
        """
        print("    [WARN] Container execution not implemented in reference v1.0.0")
        print("    [WARN] Falling back to native execution")
        native = NativeExecutor(self.cas)
        return native.execute(task, completed_results)


class WasmExecutor(BaseExecutor):
    """Execute tasks as WASM modules.

    This is a STUB for v1.0.0. A full WASM executor would:
        - Load WASM modules
        - Provide WASI interface for file I/O
        - Sandboxed execution

    Future implementations should subclass this and override execute().
    """

    def execute(
        self, task: Dict[str, Any], completed_results: Dict[str, List[str]]
    ) -> List[str]:
        """Stub: raises ExecutionError indicating unimplemented.

        Args:
            task: Task dict to execute.
            completed_results: Results from prior tasks.

        Raises:
            ExecutionError: Always, as WASM is not implemented.
        """
        raise ExecutionError(
            "WASM execution is not implemented in TGP v1.0.0 reference. "
            "Use a WASM-capable executor extension."
        )
