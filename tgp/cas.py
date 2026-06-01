#!/usr/bin/env python3
"""
tgp/cas.py -- Content-Addressed Store (Layer 1)

Implements the immutable, append-only storage layer for TGP objects.

Design principles:
    - Content-addressed: Object ID is derived from its content, not metadata
    - Append-only: Objects are never deleted or modified
    - Atomic writes: Uses temp-file + rename to prevent corruption
    - Prefix-based: Objects sharded by first 2 hex chars for performance

Specification reference: Section 5 (Content-Addressed Store)

Storage layout:
    .tgp/
      objects/
        ab/
          cd1234...     # First 2 chars = directory prefix
        ef/
          567890...
      refs/
        heads/
          main -> sha256:graph_abc...
        tags/
          v1.0.0 -> sha256:graph_def...
"""

import json
import copy
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from tgp.core import HASH_ALGO, CASError, compute_id


class CAS:
    """Content-addressed store with local filesystem backend.

    This is the reference implementation of the TGP CAS interface.
    All objects stored are immutable and identified by the SHA-256 hash
    of their content.

    Usage:
        >>> cas = CAS()  # Uses .tgp in current directory
        >>> cas = CAS(root="/var/lib/tgp")  # Custom location
        >>> obj_id = cas.put(b"hello world")
        >>> data = cas.get(obj_id)
        >>> assert data == b"hello world"

        # JSON objects with automatic ID computation
        >>> task = {"kind": "task", "command": ["echo", "hi"]}
        >>> task_id = cas.put_json(task)
        >>> retrieved = cas.get_json(task_id)
        >>> assert retrieved["id"] == task_id  # ID was computed and stored
    """

    def __init__(self, root: str = ".tgp") -> None:
        """Initialize the CAS with the given root directory.

        Creates the standard TGP directory structure if it doesn't exist.

        Args:
            root: Path to the TGP root directory. Defaults to '.tgp'.
        """
        self.root = Path(root)
        self.objects_dir = self.root / "objects"
        self.refs_dir = self.root / "refs"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create the standard TGP directory structure."""
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        (self.refs_dir / "heads").mkdir(parents=True, exist_ok=True)
        (self.refs_dir / "tags").mkdir(parents=True, exist_ok=True)

    def _object_path(self, obj_id: str) -> Path:
        """Convert a content-addressed ID to a filesystem path.

        The mapping is: sha256:abcdef... -> objects_dir/ab/cdef...

        Args:
            obj_id: Content-addressed ID in format 'sha256:hexdigest'.

        Returns:
            Path object pointing to the object's storage location.

        Raises:
            CASError: If obj_id doesn't start with 'sha256:'.
        """
        if not obj_id.startswith("sha256:"):
            raise CASError(
                "Invalid ID format: " + obj_id +
                ". Expected format: sha256:<64-hex-chars>"
            )
        hash_part = obj_id[7:]  # Remove "sha256:" prefix
        if len(hash_part) != 64:
            raise CASError(
                "Invalid hash length: " + str(len(hash_part)) +
                ". Expected 64 hex characters."
            )
        prefix = hash_part[:2]
        return self.objects_dir / prefix / hash_part

    # ------------------------------------------------------------------
    # Core CAS interface (per spec Section 5.1)
    # ------------------------------------------------------------------

    def put(self, data: bytes) -> str:
        """Store raw bytes in the CAS, returning the content-addressed ID.

        This operation is idempotent: storing the same content multiple
        times returns the same ID without creating duplicate files.

        Args:
            data: Raw bytes to store.

        Returns:
            Content-addressed ID in format 'sha256:hexdigest'.

        Example:
            >>> cas = CAS()
            >>> obj_id = cas.put(b"hello")
            >>> obj_id
            'sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
        """
        obj_id = HASH_ALGO + ":" + hashlib.sha256(data).hexdigest()
        path = self._object_path(obj_id)

        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to temp file, then rename
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_bytes(data)
            tmp_path.rename(path)

        return obj_id

    def get(self, obj_id: str) -> bytes:
        """Retrieve raw bytes from the CAS by content-addressed ID.

        Args:
            obj_id: Content-addressed ID in format 'sha256:hexdigest'.

        Returns:
            The stored bytes.

        Raises:
            CASError: If the object doesn't exist in the store.
        """
        path = self._object_path(obj_id)
        if not path.exists():
            raise CASError("Object not found: " + obj_id)
        return path.read_bytes()

    def exists(self, obj_id: str) -> bool:
        """Check if an object exists in the CAS without fetching its content.

        Args:
            obj_id: Content-addressed ID in format 'sha256:hexdigest'.

        Returns:
            True if the object exists, False otherwise.
        """
        try:
            return self._object_path(obj_id).exists()
        except CASError:
            return False

    def verify(self, obj_id: str) -> bool:
        """Verify that stored data matches its content-addressed ID.

        Recomputes the hash of the stored data and compares it to the ID.
        This detects filesystem corruption or tampering.

        Args:
            obj_id: Content-addressed ID to verify.

        Returns:
            True if the stored data matches its ID, False otherwise.
        """
        try:
            data = self.get(obj_id)
            expected = HASH_ALGO + ":" + hashlib.sha256(data).hexdigest()
            return obj_id == expected
        except CASError:
            return False

    # ------------------------------------------------------------------
    # JSON object helpers
    # ------------------------------------------------------------------

    def put_json(self, obj: Dict[str, Any]) -> str:
        """Store a JSON object, computing its TGP content-addressed ID.

        The ID is computed from the canonical form (without id and signature
        fields), then the id field is added to the stored copy. This ensures
        that the stored object is self-describing (contains its own ID).

        Args:
            obj: A TGP object as a dict. Must not contain 'id' or 'signature'
                 fields (they will be ignored for hashing).

        Returns:
            The content-addressed ID computed from the object's canonical form.

        Example:
            >>> cas = CAS()
            >>> task = {"kind": "task", "command": ["echo", "hi"]}
            >>> task_id = cas.put_json(task)
            >>> retrieved = cas.get_json(task_id)
            >>> assert retrieved["kind"] == "task"
            >>> assert retrieved["id"] == task_id
        """
        # Deep copy to avoid mutating the caller's object
        obj_copy = copy.deepcopy(obj)

        # Ensure tgp_version is set
        if "tgp_version" not in obj_copy:
            obj_copy["tgp_version"] = "1.0.0"

        # Compute ID from canonical form (excludes id and signature)
        obj_id = compute_id(obj_copy)

        # Add id to the stored copy
        obj_copy["id"] = obj_id

        # Serialize with pretty printing for human readability
        data = json.dumps(obj_copy, indent=2, ensure_ascii=False).encode("utf-8")

        # Store using content-addressed path
        path = self._object_path(obj_id)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_bytes(data)
            tmp_path.rename(path)

        return obj_id

    def get_json(self, obj_id: str) -> Dict[str, Any]:
        """Retrieve and parse a JSON object from the CAS.

        Args:
            obj_id: Content-addressed ID of the JSON object.

        Returns:
            The parsed JSON object as a Python dict.

        Raises:
            CASError: If the object doesn't exist or isn't valid JSON.
        """
        data = self.get(obj_id)
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise CASError(
                "Object " + obj_id + " is not valid JSON: " + str(e)
            )

    # ------------------------------------------------------------------
    # Refs (named references to objects)
    # ------------------------------------------------------------------

    def update_ref(self, name: str, obj_id: str, ref_type: str = "heads") -> None:
        """Update a named reference to point to a TGP object.

        Used for branch heads and tags. The ref file contains just the
        object ID as text.

        Args:
            name: Name of the reference (e.g., 'main', 'v1.0.0').
            obj_id: Content-addressed ID to point to.
            ref_type: Either 'heads' (branches) or 'tags'.
        """
        ref_path = self.refs_dir / ref_type / name
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(obj_id)

    def get_ref(self, name: str, ref_type: str = "heads") -> Optional[str]:
        """Resolve a named reference to an object ID.

        Args:
            name: Name of the reference.
            ref_type: Either 'heads' or 'tags'.

        Returns:
            The object ID the reference points to, or None if not found.
        """
        ref_path = self.refs_dir / ref_type / name
        if ref_path.exists():
            return ref_path.read_text().strip()
        return None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the CAS contents.

        Returns:
            Dict with keys:
                - objects: Total number of objects stored
                - total_bytes: Total size of all objects in bytes
                - root: Absolute path to CAS root directory
        """
        total_objects = 0
        total_bytes = 0
        if self.objects_dir.exists():
            for prefix_dir in self.objects_dir.iterdir():
                if prefix_dir.is_dir():
                    for obj_file in prefix_dir.iterdir():
                        if obj_file.is_file() and not obj_file.suffix == ".tmp":
                            total_objects += 1
                            total_bytes += obj_file.stat().st_size
        return {
            "objects": total_objects,
            "total_bytes": total_bytes,
            "root": str(self.root.absolute()),
        }
