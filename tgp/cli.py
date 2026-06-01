#!/usr/bin/env python3
"""
tgp/cli.py -- Command-Line Interface (Layer 4: Developer Experience)

Provides the main command-line interface for TGP operations:
    tgp init                          Initialize .tgp directory
    tgp cas put <file>                Store file in CAS
    tgp cas get <id>                  Retrieve file from CAS
    tgp cas verify <id>               Verify CAS integrity
    tgp task create <file>            Validate and store a task
    tgp task validate <id>            Validate a stored task
    tgp run <graph_file>              Execute a task graph
    tgp verify <id>                   Verify object integrity
    tgp cache stats                   Show cache statistics
    tgp version                       Show version

Specification reference: Section 9 (Reference Implementation Requirements)
"""

import json
import sys
import time
from pathlib import Path
from typing import List

from tgp.core import TGP_VERSION, TGPError, ValidationError, CASError, ExecutionError
from tgp.cas import CAS
from tgp.task import TaskValidator
from tgp.scheduler import Scheduler


class CLI:
    """Command-line interface for TGP.

    Usage:
        >>> cli = CLI()
        >>> sys.exit(cli.run(sys.argv[1:]))

    Or as the main entry point:
        if __name__ == "__main__":
            cli = CLI()
            sys.exit(cli.run(sys.argv[1:]))
    """

    def __init__(self, cas_root: str = ".tgp") -> None:
        """Initialize the CLI.

        Args:
            cas_root: Root directory for the CAS (default: '.tgp').
        """
        self.cas = CAS(root=cas_root)

    def run(self, args: List[str]) -> int:
        """Run the CLI with the given arguments.

        Args:
            args: Command-line arguments (excluding program name).

        Returns:
            Exit code (0 for success, 1 for error).
        """
        if not args:
            self._print_help()
            return 1

        command = args[0]

        try:
            if command == "init":
                return self._cmd_init()
            elif command == "cas":
                return self._cmd_cas(args[1:])
            elif command == "task":
                return self._cmd_task(args[1:])
            elif command == "run":
                return self._cmd_run(args[1:])
            elif command == "verify":
                return self._cmd_verify(args[1:])
            elif command == "cache":
                return self._cmd_cache(args[1:])
            elif command == "version":
                print("TGP " + TGP_VERSION)
                return 0
            else:
                print("Unknown command: " + command)
                self._print_help()
                return 1
        except TGPError as e:
            print("Error: " + str(e), file=sys.stderr)
            return 1
        except Exception as e:
            print("Unexpected error: " + str(e), file=sys.stderr)
            return 1

    def _print_help(self) -> None:
        """Print the help message."""
        help_text = """
TGP -- Task Graph Protocol v""" + TGP_VERSION + """

Usage:
    tgp init                          Initialize .tgp directory
    tgp cas put <file>                Store file in CAS
    tgp cas get <id>                  Retrieve file from CAS
    tgp cas verify <id>               Verify CAS integrity
    tgp task create <file>            Validate and store a task
    tgp task validate <id>            Validate a stored task
    tgp run <graph_file>              Execute a task graph
    tgp verify <id>                   Verify object integrity
    tgp cache stats                   Show cache statistics
    tgp version                       Show version

Examples:
    tgp init
    tgp cas put README.md
    tgp cas get sha256:2cf24dba...
    tgp task create task.json
    tgp run graph.json
    tgp verify sha256:abc123...
    tgp cache stats
"""
        print(help_text)

    # ------------------------------------------------------------------
    # init
    # ------------------------------------------------------------------

    def _cmd_init(self) -> int:
        """Initialize a TGP repository.

        Creates the .tgp directory structure with objects/ and refs/ subdirs.
        """
        self.cas._ensure_dirs()
        print("Initialized TGP repository at " + str(self.cas.root.absolute()))
        return 0

    # ------------------------------------------------------------------
    # cas
    # ------------------------------------------------------------------

    def _cmd_cas(self, args: List[str]) -> int:
        """Handle CAS subcommands: put, get, verify."""
        if not args:
            print("Usage: tgp cas <put|get|verify> ...")
            return 1

        subcmd = args[0]

        if subcmd == "put" and len(args) >= 2:
            return self._cmd_cas_put(args[1])
        elif subcmd == "get" and len(args) >= 2:
            return self._cmd_cas_get(args[1])
        elif subcmd == "verify" and len(args) >= 2:
            return self._cmd_cas_verify(args[1])
        else:
            print("Usage: tgp cas <put|get|verify> ...")
            return 1

    def _cmd_cas_put(self, filepath: str) -> int:
        """Store a file in the CAS."""
        path = Path(filepath)
        if not path.exists():
            print("File not found: " + filepath, file=sys.stderr)
            return 1
        data = path.read_bytes()
        obj_id = self.cas.put(data)
        print(obj_id)
        return 0

    def _cmd_cas_get(self, obj_id: str) -> int:
        """Retrieve a file from the CAS and write to stdout."""
        try:
            data = self.cas.get(obj_id)
            sys.stdout.buffer.write(data)
            return 0
        except CASError as e:
            print(str(e), file=sys.stderr)
            return 1

    def _cmd_cas_verify(self, obj_id: str) -> int:
        """Verify CAS integrity for an object."""
        valid = self.cas.verify(obj_id)
        print("VALID" if valid else "CORRUPTED")
        return 0 if valid else 1

    # ------------------------------------------------------------------
    # task
    # ------------------------------------------------------------------

    def _cmd_task(self, args: List[str]) -> int:
        """Handle task subcommands: create, validate."""
        if not args:
            print("Usage: tgp task <create|validate> ...")
            return 1

        subcmd = args[0]

        if subcmd == "create" and len(args) >= 2:
            return self._cmd_task_create(args[1])
        elif subcmd == "validate" and len(args) >= 2:
            return self._cmd_task_validate(args[1])
        else:
            print("Usage: tgp task <create|validate> ...")
            return 1

    def _cmd_task_create(self, filepath: str) -> int:
        """Validate a task file and store it in the CAS."""
        path = Path(filepath)
        if not path.exists():
            print("File not found: " + filepath, file=sys.stderr)
            return 1

        obj = json.loads(path.read_text())
        TaskValidator.validate(obj)
        obj_id = self.cas.put_json(obj)
        print("Task created: " + obj_id)
        return 0

    def _cmd_task_validate(self, obj_id: str) -> int:
        """Validate a task stored in the CAS."""
        obj = self.cas.get_json(obj_id)
        TaskValidator.validate(obj)
        print("Task valid: " + obj_id)
        return 0

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------

    def _cmd_run(self, args: List[str]) -> int:
        """Execute a task graph from a file."""
        if not args:
            print("Usage: tgp run <graph_file>")
            return 1

        path = Path(args[0])
        if not path.exists():
            print("File not found: " + str(args[0]), file=sys.stderr)
            return 1

        graph = json.loads(path.read_text())

        # If tasks are file paths (not IDs), load and store them
        if "tasks" in graph and all(
            isinstance(t, str) and not t.startswith("sha256:")
            for t in graph["tasks"]
        ):
            task_ids = []
            for task_path in graph["tasks"]:
                task = json.loads(Path(task_path).read_text())
                TaskValidator.validate(task)
                obj_id = self.cas.put_json(task)
                task_ids.append(obj_id)
            graph["tasks"] = task_ids

        # Store the graph itself
        graph_id = self.cas.put_json(graph)
        print("Graph: " + graph_id)
        print("Executing...")

        scheduler = Scheduler(self.cas)
        start = time.time()

        try:
            results = scheduler.execute_graph(graph)
            elapsed = time.time() - start

            print("\nExecution complete in " + str(round(elapsed, 2)) + "s")
            print("  Cache hits:   " + str(scheduler.stats()["cache_hits"]))
            print("  Cache misses: " + str(scheduler.stats()["cache_misses"]))
            print("  Executed:     " + str(scheduler.stats()["executed"]))

            for task_id, outputs in results.items():
                print("  " + task_id[:30] + "... -> " + str(outputs))

            return 0
        except TGPError as e:
            print("\nExecution failed: " + str(e), file=sys.stderr)
            return 1

    # ------------------------------------------------------------------
    # verify
    # ------------------------------------------------------------------

    def _cmd_verify(self, args: List[str]) -> int:
        """Verify a TGP object's integrity."""
        if not args:
            print("Usage: tgp verify <id>")
            return 1

        obj_id = args[0]

        # First, verify CAS integrity
        valid = self.cas.verify(obj_id)
        if not valid:
            print("Object corrupted or missing: " + obj_id)
            return 1

        # Then validate the object structure
        try:
            obj = self.cas.get_json(obj_id)
            TaskValidator.validate(obj)
            print("Object valid: " + obj_id)
            print("  Kind:    " + obj.get("kind", "unknown"))
            print("  Version: " + obj.get("tgp_version", "unknown"))
            return 0
        except ValidationError as e:
            print("Object CAS-valid but structurally invalid: " + str(e))
            return 1

    # ------------------------------------------------------------------
    # cache
    # ------------------------------------------------------------------

    def _cmd_cache(self, args: List[str]) -> int:
        """Show cache statistics."""
        if not args or args[0] == "stats":
            stats = self.cas.stats()
            print("CAS Statistics:")
            print("  Objects:    " + str(stats["objects"]))
            mb = stats["total_bytes"] / 1024 / 1024
            print("  Total size: " + str(stats["total_bytes"]) + " bytes (" + str(round(mb, 2)) + " MB)")
            print("  Root:       " + str(stats["root"]))
            return 0

        print("Usage: tgp cache stats")
        return 1


def main() -> None:
    """Main entry point for the TGP CLI."""
    cli = CLI()
    sys.exit(cli.run(sys.argv[1:]))
