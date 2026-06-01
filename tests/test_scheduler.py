#!/usr/bin/env python3
"""
tests/test_scheduler.py -- Tests for DAG Execution Engine

Validates:
    - Linear graph execution (A -> B -> C)
    - Parallel graph execution (A -> [B, C] -> D)
    - Cache hit behavior
    - Cycle detection
    - Hash mismatch detection
    - Empty graph handling
    - Missing input handling
"""

import pytest
from tgp.cas import CAS
from tgp.scheduler import Scheduler
from tgp.core import ExecutionError, compute_id


class TestSchedulerLinearGraph:
    """Test linear dependency chains: A -> B -> C."""

    def test_single_task(self, tmp_path):
        """Graph with one task executes correctly."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "hello" > result.txt'],
            "outputs": [{"path": "result.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler = Scheduler(cas)
        results = scheduler.execute_graph(graph)

        assert task_id in results
        assert len(results[task_id]) == 1
        assert cas.exists(results[task_id][0])

    def test_two_task_linear(self, tmp_path):
        """A -> B where B depends on A's output."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        # Task A: produce a file
        task_a = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "step_a" > data.txt'],
            "outputs": [{"path": "data.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_a_id = cas.put_json(task_a)

        # Execute to get output hash
        scheduler = Scheduler(cas)
        result_a = scheduler.execute_graph({
            "tgp_version": "1.0.0", "kind": "graph",
            "root": task_a_id, "tasks": [task_a_id],
        })
        output_a_id = result_a[task_a_id][0]

        # Task B: consumes A's output
        task_b = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "data.txt", "ref": output_a_id, "required": True}],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'cat data.txt && echo "step_b" > result.txt'],
            "outputs": [{"path": "result.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_b_id = cas.put_json(task_b)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_a_id,
            "tasks": [task_a_id, task_b_id],
        }

        scheduler2 = Scheduler(cas)
        results = scheduler2.execute_graph(graph)

        assert task_a_id in results
        assert task_b_id in results
        assert len(results[task_b_id]) == 1

    def test_three_task_chain(self, tmp_path):
        """A -> B -> C linear chain."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        task_a = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "A" > a.txt'],
            "outputs": [{"path": "a.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_a_id = cas.put_json(task_a)

        scheduler = Scheduler(cas)
        result_a = scheduler.execute_graph({
            "tgp_version": "1.0.0", "kind": "graph",
            "root": task_a_id, "tasks": [task_a_id],
        })
        output_a_id = result_a[task_a_id][0]

        task_b = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "a.txt", "ref": output_a_id, "required": True}],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'cat a.txt && echo "B" > b.txt'],
            "outputs": [{"path": "b.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_b_id = cas.put_json(task_b)

        result_b = scheduler.execute_graph({
            "tgp_version": "1.0.0", "kind": "graph",
            "root": task_b_id, "tasks": [task_b_id],
        })
        output_b_id = result_b[task_b_id][0]

        task_c = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "b.txt", "ref": output_b_id, "required": True}],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'cat b.txt && echo "C" > c.txt'],
            "outputs": [{"path": "c.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_c_id = cas.put_json(task_c)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_a_id,
            "tasks": [task_a_id, task_b_id, task_c_id],
        }

        scheduler2 = Scheduler(cas)
        results = scheduler2.execute_graph(graph)

        assert all(tid in results for tid in [task_a_id, task_b_id, task_c_id])


class TestSchedulerCache:
    """Test content-addressed caching behavior."""

    def test_cache_hit(self, tmp_path):
        """Re-running a graph with expected_hash skips execution."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        # First execution to get the output hash
        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "cached" > data.txt'],
            "outputs": [{"path": "data.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler1 = Scheduler(cas)
        results1 = scheduler1.execute_graph(graph)
        actual_output_id = results1[task_id][0]
        assert scheduler1.stats()["executed"] == 1
        assert scheduler1.stats()["cache_hits"] == 0

        # Second execution with expected_hash set - should be cache hit
        task_cached = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "cached" > data.txt'],
            "outputs": [{"path": "data.txt", "expected_hash": actual_output_id}],
            "resources": {"timeout": "10s"},
        }
        task_cached_id = cas.put_json(task_cached)

        graph_cached = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_cached_id,
            "tasks": [task_cached_id],
        }

        scheduler2 = Scheduler(cas)
        results2 = scheduler2.execute_graph(graph_cached)
        assert scheduler2.stats()["cache_hits"] == 1
        assert scheduler2.stats()["executed"] == 0
        assert results2[task_cached_id][0] == actual_output_id

    def test_cache_with_expected_hash(self, tmp_path):
        """Cache works when expected_hash is specified."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        # Execute to get actual output hash
        task_producer = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "deterministic" > data.txt'],
            "outputs": [{"path": "data.txt"}],
            "resources": {"timeout": "10s"},
        }
        producer_id = cas.put_json(task_producer)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": producer_id,
            "tasks": [producer_id],
        }
        scheduler = Scheduler(cas)
        results = scheduler.execute_graph(graph)
        actual_output_id = results[producer_id][0]

        # Create task with expected_hash
        task_consumer = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "deterministic" > data.txt'],
            "outputs": [{"path": "data.txt", "expected_hash": actual_output_id}],
            "resources": {"timeout": "10s"},
        }
        consumer_id = cas.put_json(task_consumer)

        consumer_graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": consumer_id,
            "tasks": [consumer_id],
        }

        scheduler2 = Scheduler(cas)
        results2 = scheduler2.execute_graph(consumer_graph)
        assert scheduler2.stats()["cache_hits"] == 1
        assert results2[consumer_id][0] == actual_output_id


class TestSchedulerErrors:
    """Test error handling in the scheduler."""

    def test_cycle_detection(self, tmp_path):
        """Cyclic graph raises ExecutionError."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        artifact_a = cas.put(b"artifact_a")
        artifact_b = cas.put(b"artifact_b")

        task_a = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "b", "ref": artifact_b, "required": True}],
            "environment": {"type": "native"},
            "command": ["echo", "A"],
            "outputs": [{"path": "a.txt", "expected_hash": artifact_a}],
            "resources": {"timeout": "10s"},
        }
        task_a_id = cas.put_json(task_a)

        task_b = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "a", "ref": artifact_a, "required": True}],
            "environment": {"type": "native"},
            "command": ["echo", "B"],
            "outputs": [{"path": "b.txt", "expected_hash": artifact_b}],
            "resources": {"timeout": "10s"},
        }
        task_b_id = cas.put_json(task_b)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_a_id,
            "tasks": [task_a_id, task_b_id],
        }

        scheduler = Scheduler(cas)
        with pytest.raises(ExecutionError, match="Cycle"):
            scheduler.execute_graph(graph)

    def test_command_failure(self, tmp_path):
        """Failing command raises ExecutionError."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", "exit 1"],
            "outputs": [],
            "resources": {"timeout": "10s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler = Scheduler(cas)
        with pytest.raises(ExecutionError):
            scheduler.execute_graph(graph)

    def test_missing_required_output(self, tmp_path):
        """Missing required output raises ExecutionError."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["echo", "no output file"],
            "outputs": [{"path": "missing.txt", "optional": False}],
            "resources": {"timeout": "10s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler = Scheduler(cas)
        with pytest.raises(ExecutionError, match="Required output not found"):
            scheduler.execute_graph(graph)

    def test_optional_output_missing(self, tmp_path):
        """Missing optional output is allowed."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["echo", "no output"],
            "outputs": [{"path": "missing.txt", "optional": True}],
            "resources": {"timeout": "10s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler = Scheduler(cas)
        results = scheduler.execute_graph(graph)
        assert task_id in results
        assert len(results[task_id]) == 0

    def test_timeout(self, tmp_path):
        """Long-running task times out."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sleep", "10"],
            "outputs": [],
            "resources": {"timeout": "1s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler = Scheduler(cas)
        with pytest.raises(ExecutionError, match="timed out"):
            scheduler.execute_graph(graph)


class TestSchedulerStats:
    """Test statistics tracking."""

    def test_stats_initial(self, tmp_path):
        """Stats are zero initially."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        scheduler = Scheduler(cas)
        stats = scheduler.stats()
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["executed"] == 0
        assert stats["failed"] == 0

    def test_stats_after_execution(self, tmp_path):
        """Stats reflect execution."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "test" > data.txt'],
            "outputs": [{"path": "data.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler = Scheduler(cas)
        scheduler.execute_graph(graph)

        stats = scheduler.stats()
        assert stats["executed"] == 1
        assert stats["cache_misses"] == 1
        assert stats["cache_hits"] == 0

    def test_stats_after_cache_hit(self, tmp_path):
        """Stats reflect cache hits."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        # First execution to get output hash
        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "cached" > data.txt'],
            "outputs": [{"path": "data.txt"}],
            "resources": {"timeout": "10s"},
        }
        task_id = cas.put_json(task)

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task_id,
            "tasks": [task_id],
        }

        scheduler1 = Scheduler(cas)
        results = scheduler1.execute_graph(graph)
        output_id = results[task_id][0]

        # Second execution with expected_hash
        task2 = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [],
            "environment": {"type": "native"},
            "command": ["sh", "-c", 'echo "cached" > data.txt'],
            "outputs": [{"path": "data.txt", "expected_hash": output_id}],
            "resources": {"timeout": "10s"},
        }
        task2_id = cas.put_json(task2)

        graph2 = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": task2_id,
            "tasks": [task2_id],
        }

        scheduler2 = Scheduler(cas)
        scheduler2.execute_graph(graph2)

        stats = scheduler2.stats()
        assert stats["cache_hits"] == 1
        assert stats["executed"] == 0


class TestSchedulerIntegration:
    """Integration tests for realistic scenarios."""

    def test_compile_and_run_pattern(self, tmp_path):
        """Simulate a compile-then-run pipeline."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        # Source code
        source_code = b'#include <stdio.h>\nint main() { printf("hello\\n"); return 0; }\n'
        source_id = cas.put(source_code)

        # First: compile to get the binary hash
        compile_task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "main.c", "ref": source_id, "required": True}],
            "environment": {"type": "native"},
            "command": ["gcc", "main.c", "-o", "main"],
            "outputs": [{"path": "main"}],
            "resources": {"timeout": "30s"},
        }
        compile_id = cas.put_json(compile_task)

        scheduler = Scheduler(cas)
        compile_result = scheduler.execute_graph({
            "tgp_version": "1.0.0", "kind": "graph",
            "root": compile_id, "tasks": [compile_id],
        })
        binary_id = compile_result[compile_id][0]

        # Second: create tasks with expected_hash for caching
        compile_task_cached = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "main.c", "ref": source_id, "required": True}],
            "environment": {"type": "native"},
            "command": ["gcc", "main.c", "-o", "main"],
            "outputs": [{"path": "main", "expected_hash": binary_id}],
            "resources": {"timeout": "30s"},
        }
        compile_cached_id = cas.put_json(compile_task_cached)

        # Run task
        run_task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "main", "ref": binary_id, "required": True}],
            "environment": {"type": "native"},
            "command": ["sh", "-c", "chmod +x main && ./main"],
            "outputs": [{"path": "output.txt", "optional": True}],
            "resources": {"timeout": "10s"},
        }
        run_id = cas.put_json(run_task)

        # Full pipeline graph
        pipeline_graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": compile_cached_id,
            "tasks": [compile_cached_id, run_id],
        }

        scheduler2 = Scheduler(cas)
        results = scheduler2.execute_graph(pipeline_graph)

        assert compile_cached_id in results
        assert run_id in results
        assert scheduler2.stats()["cache_hits"] == 1  # Compile cached
        assert scheduler2.stats()["executed"] == 1    # Run executed

    def test_multiple_independent_tasks(self, tmp_path):
        """Multiple tasks with no dependencies."""
        cas = CAS(root=str(tmp_path / ".tgp"))

        tasks = []
        for i in range(3):
            task = {
                "tgp_version": "1.0.0",
                "kind": "task",
                "inputs": [],
                "environment": {"type": "native"},
                "command": ["sh", "-c", f'echo "task{i}" > result.txt'],
                "outputs": [{"path": "result.txt"}],
                "resources": {"timeout": "10s"},
            }
            tasks.append(cas.put_json(task))

        graph = {
            "tgp_version": "1.0.0",
            "kind": "graph",
            "root": tasks[0],
            "tasks": tasks,
        }

        scheduler = Scheduler(cas)
        results = scheduler.execute_graph(graph)

        assert len(results) == 3
        assert scheduler.stats()["executed"] == 3
