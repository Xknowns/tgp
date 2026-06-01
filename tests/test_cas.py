#!/usr/bin/env python3
"""
tests/test_cas.py -- Tests for Content-Addressed Store

Validates:
    - Put/get roundtrip
    - Content addressing (same content = same ID)
    - Idempotency (put same content twice = same ID, no duplicate file)
    - Existence checking
    - Corruption detection
    - JSON object storage with automatic ID computation
    - Reference management
"""

import json
import pytest
import tempfile
from pathlib import Path

from tgp.cas import CAS
from tgp.core import CASError


class TestCASPutGet:
    """Test basic put/get operations."""

    def test_put_returns_id(self, tmp_path):
        """put() returns a sha256:... ID."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        data = b"hello world"
        obj_id = cas.put(data)
        assert obj_id.startswith("sha256:")
        assert len(obj_id) == 71  # "sha256:" + 64 hex chars

    def test_get_roundtrip(self, tmp_path):
        """get(put(data)) == data."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        data = b"hello world"
        obj_id = cas.put(data)
        retrieved = cas.get(obj_id)
        assert retrieved == data

    def test_put_different_data_different_ids(self, tmp_path):
        """Different content produces different IDs."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        id1 = cas.put(b"hello")
        id2 = cas.put(b"world")
        assert id1 != id2

    def test_get_nonexistent_raises(self, tmp_path):
        """Getting a non-existent object raises CASError."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        with pytest.raises(CASError):
            cas.get("sha256:" + "0" * 64)

    def test_get_invalid_id_format_raises(self, tmp_path):
        """Getting with invalid ID format raises CASError."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        with pytest.raises(CASError):
            cas.get("invalid:id")


class TestCASContentAddressing:
    """Test content-addressed properties."""

    def test_same_content_same_id(self, tmp_path):
        """Same content = same ID (content addressing)."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        id1 = cas.put(b"identical content")
        id2 = cas.put(b"identical content")
        assert id1 == id2

    def test_id_is_sha256(self, tmp_path):
        """ID is sha256:hexdigest of content."""
        import hashlib
        cas = CAS(root=str(tmp_path / ".tgp"))
        data = b"test data"
        expected_id = "sha256:" + hashlib.sha256(data).hexdigest()
        obj_id = cas.put(data)
        assert obj_id == expected_id


class TestCASIdempotency:
    """Test that CAS operations are idempotent."""

    def test_put_idempotent_no_duplicate_file(self, tmp_path):
        """Put same content twice doesn't create duplicate files."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        data = b"same content"
        cas.put(data)
        cas.put(data)  # Second put should be no-op

        # Count objects
        stats = cas.stats()
        assert stats["objects"] == 1

    def test_put_idempotent_same_id(self, tmp_path):
        """Put same content twice returns same ID."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        data = b"test"
        id1 = cas.put(data)
        id2 = cas.put(data)
        assert id1 == id2


class TestCASVerify:
    """Test integrity verification."""

    def test_verify_valid(self, tmp_path):
        """verify() returns True for valid objects."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj_id = cas.put(b"valid data")
        assert cas.verify(obj_id) is True

    def test_verify_nonexistent(self, tmp_path):
        """verify() returns False for non-existent objects."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        assert cas.verify("sha256:" + "0" * 64) is False

    def test_verify_detects_corruption(self, tmp_path):
        """verify() detects corrupted data."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        data = b"original data"
        obj_id = cas.put(data)

        # Corrupt the stored file
        path = cas._object_path(obj_id)
        path.write_bytes(b"corrupted!")

        assert cas.verify(obj_id) is False


class TestCASExists:
    """Test existence checking."""

    def test_exists_true(self, tmp_path):
        """exists() returns True for stored objects."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj_id = cas.put(b"test")
        assert cas.exists(obj_id) is True

    def test_exists_false(self, tmp_path):
        """exists() returns False for non-existent objects."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        assert cas.exists("sha256:" + "0" * 64) is False

    def test_exists_invalid_format(self, tmp_path):
        """exists() returns False for invalid ID format."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        assert cas.exists("invalid") is False


class TestCASJson:
    """Test JSON object storage helpers."""

    def test_put_json_computes_id(self, tmp_path):
        """put_json computes and stores the ID."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj = {"kind": "task", "command": ["echo", "hi"]}
        obj_id = cas.put_json(obj)

        # Retrieve and check ID is present
        retrieved = cas.get_json(obj_id)
        assert "id" in retrieved
        assert retrieved["id"] == obj_id

    def test_put_json_adds_tgp_version(self, tmp_path):
        """put_json adds tgp_version if missing."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj = {"kind": "task"}
        obj_id = cas.put_json(obj)
        retrieved = cas.get_json(obj_id)
        assert retrieved["tgp_version"] == "1.0.0"

    def test_put_json_preserves_existing_version(self, tmp_path):
        """put_json preserves existing tgp_version."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj = {"kind": "task", "tgp_version": "1.0.0"}
        obj_id = cas.put_json(obj)
        retrieved = cas.get_json(obj_id)
        assert retrieved["tgp_version"] == "1.0.0"

    def test_put_json_doesnt_mutate_original(self, tmp_path):
        """put_json doesn't modify the original object."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj = {"kind": "task"}
        original_keys = set(obj.keys())
        cas.put_json(obj)
        assert set(obj.keys()) == original_keys  # Original unchanged

    def test_get_json_parses_correctly(self, tmp_path):
        """get_json returns the correct parsed object."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj = {"kind": "task", "command": ["echo"], "labels": {"env": "test"}}
        obj_id = cas.put_json(obj)
        retrieved = cas.get_json(obj_id)
        assert retrieved["kind"] == "task"
        assert retrieved["command"] == ["echo"]
        assert retrieved["labels"] == {"env": "test"}

    def test_get_json_invalid_json_raises(self, tmp_path):
        """get_json raises CASError for non-JSON data."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj_id = cas.put(b"not json")
        with pytest.raises(CASError):
            cas.get_json(obj_id)


class TestCASRefs:
    """Test named reference management."""

    def test_update_and_get_ref(self, tmp_path):
        """Can update and retrieve a ref."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        cas.update_ref("main", "sha256:abc123")
        assert cas.get_ref("main") == "sha256:abc123"

    def test_get_nonexistent_ref(self, tmp_path):
        """Getting a non-existent ref returns None."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        assert cas.get_ref("nonexistent") is None

    def test_update_ref_overwrites(self, tmp_path):
        """Updating a ref overwrites the previous value."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        cas.update_ref("main", "sha256:abc")
        cas.update_ref("main", "sha256:def")
        assert cas.get_ref("main") == "sha256:def"

    def test_tag_ref(self, tmp_path):
        """Can create tag refs."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        cas.update_ref("v1.0.0", "sha256:release", ref_type="tags")
        assert cas.get_ref("v1.0.0", ref_type="tags") == "sha256:release"


class TestCASStats:
    """Test statistics reporting."""

    def test_empty_stats(self, tmp_path):
        """Stats for empty CAS."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        stats = cas.stats()
        assert stats["objects"] == 0
        assert stats["total_bytes"] == 0

    def test_stats_after_put(self, tmp_path):
        """Stats reflect stored objects."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        data = b"x" * 100
        cas.put(data)
        stats = cas.stats()
        assert stats["objects"] == 1
        assert stats["total_bytes"] == 100

    def test_stats_multiple_objects(self, tmp_path):
        """Stats with multiple objects."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        cas.put(b"a")
        cas.put(b"b")
        cas.put(b"c")
        stats = cas.stats()
        assert stats["objects"] == 3

    def test_stats_ignores_temp_files(self, tmp_path):
        """Stats don't count .tmp files."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        # Manually create a .tmp file
        prefix_dir = cas.objects_dir / "ab"
        prefix_dir.mkdir(parents=True, exist_ok=True)
        (prefix_dir / "cd1234.tmp").write_bytes(b"temp")
        stats = cas.stats()
        assert stats["objects"] == 0


class TestCASDirectoryStructure:
    """Test the prefix-based directory layout."""

    def test_prefix_directory(self, tmp_path):
        """Objects are stored in prefix directories."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        obj_id = cas.put(b"test")
        hash_part = obj_id[7:]  # Remove "sha256:"
        prefix = hash_part[:2]
        expected_path = cas.objects_dir / prefix / hash_part
        assert expected_path.exists()

    def test_objects_dir_exists(self, tmp_path):
        """CAS creates objects directory."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        assert cas.objects_dir.exists()

    def test_refs_dirs_exist(self, tmp_path):
        """CAS creates refs directories."""
        cas = CAS(root=str(tmp_path / ".tgp"))
        assert (cas.refs_dir / "heads").exists()
        assert (cas.refs_dir / "tags").exists()
