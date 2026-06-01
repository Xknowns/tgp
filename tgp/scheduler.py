#!/usr/bin/env python3
"""
tgp/scheduler.py -- DAG Execution Engine (Layer 3: Orchestration)

Implements graph reduction: repeatedly replacing executable task nodes with
their output artifacts until only artifacts remain.

Key features:
    - Topological sort (Kahn's algorithm) for dependency ordering
    - Content-addressed caching (skip if output already exists)
    - Dependency graph building from input/output references
    - Cycle detection
    - Execution statistics tracking

The scheduler delegates actual task execution to executor backends,
maintaining clean separation between orchestration (when) and execution (how).

Specification reference: Section 6 (Execution Semantics)
"""

from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

from tgp.core import ExecutionError
from tgp.task import TaskValidator
from tgp.executor import NativeExecutor, ContainerExecutor, WasmExecutor


class Scheduler:
    """DAG execution engine for TGP task graphs.

    Implements graph reduction as specified in Section 6.1:
    "Execution is graph reduction: repeatedly replace executable task nodes
    with their output artifacts until only artifacts remain."

    The scheduler handles:
        - Loading tasks from CAS
        - Building dependency graphs
        - Topological ordering
        - Cache checking
        - Delegating execution to appropriate executor

    Usage:
        >>> from tgp import CAS, Scheduler
        >>> cas = CAS()
        >>> scheduler = Scheduler(cas, max_workers=4)
        >>> results = scheduler.execute_graph(graph_dict)
        >>> print(scheduler.stats())
    """

    def __init__(self, cas: Any, max_workers: int = 4) -> None:
        """Initialize the scheduler.

        Args:
            cas: A CAS instance for storing/fetching artifacts.
            max_workers: Maximum parallel execution slots (reserved for future use;
                         current implementation executes sequentially but in
                         topologically-correct order).
        """
        self.cas = cas
        self.max_workers = max_workers
        self.cache_hits = 0
        self.cache_misses = 0
        self.executed = 0
        self.failed = 0

        # Executor registry by environment type
        self._executors = {
            "native": NativeExecutor(cas),
            "container": ContainerExecutor(cas),
            "wasm": WasmExecutor(cas),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_graph(self, graph: Dict[str, Any]) -> Dict[str, List[str]]:
        """Execute a task graph and return output artifact IDs.

        This is the main entry point for graph execution. It:
        1. Validates the graph object
        2. Loads all tasks from the CAS
        3. Builds a dependency graph from input/output references
        4. Topologically sorts the tasks
        5. Executes each task in order, checking cache first

        Args:
            graph: A TGP graph dict with 'kind': 'graph' and 'tasks' list.

        Returns:
            Dict mapping task_id -> list of output artifact IDs.

        Raises:
            ExecutionError: If a cycle is detected or a task fails.
            ValidationError: If the graph or any task is invalid.
        """
        TaskValidator.validate(graph)

        # Load all tasks referenced in the graph
        tasks: Dict[str, Dict[str, Any]] = {}
        for task_id in graph.get("tasks", []):
            task = self.cas.get_json(task_id)
            TaskValidator.validate(task)
            tasks[task_id] = task

        # Build dependency graph
        dep_graph = self._build_dependency_graph(tasks)

        # Topological sort for execution order
        execution_order = self._topological_sort(dep_graph)

        # Execute tasks in dependency order
        results: Dict[str, List[str]] = {}

        for task_id in execution_order:
            task = tasks[task_id]

            # Check cache before execution
            cached = self._check_cache(task)
            if cached:
                results[task_id] = cached
                self.cache_hits += 1
                print("  [CACHE] " + task_id[:24] + "...")
                continue

            self.cache_misses += 1

            # Execute the task via appropriate executor
            try:
                output_ids = self._execute_task(task, results)
                results[task_id] = output_ids
                self.executed += 1
                print("  [EXEC]  " + task_id[:24] + "... -> " + str(len(output_ids)) + " output(s)")
            except Exception as e:
                self.failed += 1
                raise ExecutionError(
                    "Task " + task_id + " failed: " + str(e)
                )

        return results

    def stats(self) -> Dict[str, int]:
        """Return execution statistics.

        Returns:
            Dict with keys:
                - cache_hits: Number of tasks skipped due to cache hit
                - cache_misses: Number of tasks not in cache
                - executed: Number of tasks actually executed
                - failed: Number of tasks that failed
        """
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "executed": self.executed,
            "failed": self.failed,
        }

    # ------------------------------------------------------------------
    # Dependency graph construction
    # ------------------------------------------------------------------

    def _build_dependency_graph(
        self, tasks: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Set[str]]:
        """Build a dependency graph from task input/output references.

        A task B depends on task A if any of B's input refs match any of
        A's expected output hashes. This creates the partial ordering that
        determines execution order.

        Args:
            tasks: Dict mapping task_id -> task dict.

        Returns:
            Adjacency list: task_id -> set of task_ids it depends on.
        """
        graph: Dict[str, Set[str]] = defaultdict(set)

        # Ensure all tasks appear in the graph (even with no dependencies)
        for task_id in tasks:
            graph[task_id] = set()

        # Map expected output hashes to their producing task IDs
        artifact_to_task: Dict[str, str] = {}
        for task_id, task in tasks.items():
            for out in task.get("outputs", []):
                expected = out.get("expected_hash")
                if expected:
                    artifact_to_task[expected] = task_id

        # Build dependency edges from input refs
        for task_id, task in tasks.items():
            for inp in task.get("inputs", []):
                ref = inp["ref"]
                if ref in artifact_to_task:
                    dep_task = artifact_to_task[ref]
                    if dep_task != task_id:  # No self-loops
                        graph[task_id].add(dep_task)

        return dict(graph)

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def _topological_sort(self, graph: Dict[str, Set[str]]) -> List[str]:
        """Kahn's algorithm for topological sort.

        Produces a linear ordering of tasks such that for every edge
        u -> v (u must execute before v), u appears before v in the ordering.

        Args:
            graph: Adjacency list: task_id -> set of dependencies.

        Returns:
            List of task IDs in execution order.

        Raises:
            ExecutionError: If the graph contains a cycle.
        """
        # Compute in-degree for each node
        in_degree: Dict[str, int] = defaultdict(int)
        all_nodes: Set[str] = set(graph.keys())
        for deps in graph.values():
            all_nodes.update(deps)

        # in_degree[node] = number of dependencies the node has
        for node in all_nodes:
            in_degree[node] = len(graph.get(node, set()))

        # Start with nodes that have no dependencies (in_degree == 0)
        queue = [n for n in all_nodes if in_degree[n] == 0]
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor, deps in graph.items():
                if node in deps:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if len(result) != len(all_nodes):
            raise ExecutionError(
                "Cycle detected in task graph. " +
                "The graph must be a DAG (no circular dependencies)."
            )

        return result

    # ------------------------------------------------------------------
    # Cache checking
    # ------------------------------------------------------------------

    def _check_cache(self, task: Dict[str, Any]) -> Optional[List[str]]:
        """Check if all expected outputs for a task already exist in CAS.

        Per Section 6.3 (Caching):
        Before executing any task:
        1. Compute task ID from canonical form
        2. Check CAS for existing output artifacts matching expected_hash
        3. If found, skip execution, use cached result

        Args:
            task: A task dict with 'outputs' list.

        Returns:
            List of output artifact IDs if all are cached, None otherwise.
        """
        outputs: List[str] = []
        for out in task.get("outputs", []):
            expected = out.get("expected_hash")
            if expected and self.cas.exists(expected):
                outputs.append(expected)
            else:
                return None
        return outputs if outputs else None

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def _execute_task(
        self, task: Dict[str, Any], completed_results: Dict[str, List[str]]
    ) -> List[str]:
        """Execute a single task using the appropriate executor.

        Looks up the executor based on the task's environment type and
        delegates execution.

        Args:
            task: The task dict to execute.
            completed_results: Results from already-executed tasks.

        Returns:
            List of output artifact IDs produced by this task.

        Raises:
            ExecutionError: If no executor is available for the environment type.
        """
        env_type = task.get("environment", {}).get("type", "native")

        executor = self._executors.get(env_type)
        if executor is None:
            raise ExecutionError(
                "No executor available for environment type: " + str(env_type)
            )

        return executor.execute(task, completed_results)
