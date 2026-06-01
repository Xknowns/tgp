"""
TGP -- Task Graph Protocol
Reference Implementation v1.0.0

An immutable execution layer designed to outlive frameworks.

This package provides:
    - core: Canonicalization and content-addressed identity
    - cas: Content-addressed store with filesystem backend
    - task: Task model and validation against TGP spec
    - scheduler: DAG execution engine with topological sort
    - executor: Native task execution in temporary directories
    - crypto: Ed25519 signing and verification
    - cli: Command-line interface

Usage:
    from tgp import CAS, TaskValidator, Scheduler
    from tgp.core import canonicalize, compute_id, verify_id

Example:
    >>> cas = CAS()
    >>> obj = {"kind": "task", "command": ["echo", "hello"]}
    >>> obj_id = cas.put_json(obj)
    >>> print(obj_id)
    sha256:...
"""

__version__ = "1.0.0"

# Core exports
from tgp.core import (
    canonicalize,
    compute_id,
    verify_id,
    TGP_VERSION,
    HASH_ALGO,
    SIGN_ALGO,
    TGPError,
    ValidationError,
    CASError,
    ExecutionError,
)

from tgp.cas import CAS
from tgp.task import (
    TaskInput,
    TaskOutput,
    TaskEnvironment,
    TaskResources,
    TaskValidator,
)
from tgp.scheduler import Scheduler
from tgp.executor import NativeExecutor
from tgp.crypto import CryptoManager

__all__ = [
    # Version
    "__version__",
    # Core
    "canonicalize",
    "compute_id",
    "verify_id",
    "TGP_VERSION",
    "HASH_ALGO",
    "SIGN_ALGO",
    # Exceptions
    "TGPError",
    "ValidationError",
    "CASError",
    "ExecutionError",
    # Components
    "CAS",
    "TaskValidator",
    "TaskInput",
    "TaskOutput",
    "TaskEnvironment",
    "TaskResources",
    "Scheduler",
    "NativeExecutor",
    "CryptoManager",
]
