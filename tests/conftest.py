#!/usr/bin/env python3
"""
tests/conftest.py -- Pytest configuration and shared fixtures.
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def tmp_cas(tmp_path):
    """Create a temporary CAS for testing.

    Yields a CAS instance backed by a temporary directory that is
    automatically cleaned up after the test.
    """
    from tgp.cas import CAS
    cas = CAS(root=str(tmp_path / ".tgp"))
    yield cas
