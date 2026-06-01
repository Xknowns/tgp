#!/usr/bin/env python3
"""
tgp/crypto.py -- Cryptographic Signing and Verification (Layer 1: Security)

Implements Ed25519 signatures for TGP objects as specified in Section 7:

    signature = ed25519_sign(private_key, sha256(canonical_json(object)))

All objects (tasks, artifacts, environments, graphs) MUST be signed by their
creator's Ed25519 key. This provides:
    - Authorship verification: You know who created an object
    - Integrity: Tampering invalidates the signature
    - Non-repudiation: Creator cannot deny authorship

The reference implementation uses the 'cryptography' library for Ed25519.
If unavailable, it falls back to a stub implementation for development.

Specification reference: Section 7 (Security)
"""

import json
import hashlib
from typing import Any, Dict, Optional, Tuple

from tgp.core import TGP_VERSION, HASH_ALGO, SIGN_ALGO, canonicalize


class CryptoError(Exception):
    """Cryptographic operation failed."""
    pass


class CryptoManager:
    """Manages Ed25519 key pairs and object signing/verification.

    Usage:
        >>> crypto = CryptoManager()
        >>> sk, pk = crypto.generate_keypair()
        >>> obj = {"kind": "task", "command": ["echo", "hi"]}
        >>> signed = crypto.sign_object(obj, sk)
        >>> assert crypto.verify_object(signed, pk)

    The sign_object method adds a 'signature' field to the object.
    The verify_object method checks that signature against the public key.
    """

    def __init__(self) -> None:
        """Initialize the crypto manager.

        Checks for Ed25519 support and sets up the backend.
        """
        self._ed25519_available = False
        self._private_key_class = None
        self._public_key_class = None
        self._default_backend = None

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
                Ed25519PublicKey,
            )
            from cryptography.hazmat.primitives import serialization
            from cryptography.exceptions import InvalidSignature

            self._private_key_class = Ed25519PrivateKey
            self._public_key_class = Ed25519PublicKey
            self._serialization = serialization
            self._invalid_signature = InvalidSignature
            self._ed25519_available = True
        except ImportError:
            self._ed25519_available = False

    def is_available(self) -> bool:
        """Check if Ed25519 support is available.

        Returns:
            True if the cryptography library is installed and supports Ed25519.
        """
        return self._ed25519_available

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Generate a new Ed25519 key pair.

        Returns:
            Tuple of (private_key_bytes, public_key_bytes) in raw format.

        Raises:
            CryptoError: If Ed25519 is not available.
        """
        if not self._ed25519_available:
            raise CryptoError(
                "Ed25519 not available. Install cryptography: pip install cryptography"
            )

        private_key = self._private_key_class.generate()
        public_key = private_key.public_key()

        sk_bytes = private_key.private_bytes(
            encoding=self._serialization.Encoding.Raw,
            format=self._serialization.PrivateFormat.Raw,
            encryption_algorithm=self._serialization.NoEncryption(),
        )
        pk_bytes = public_key.public_bytes(
            encoding=self._serialization.Encoding.Raw,
            format=self._serialization.PublicFormat.Raw,
        )

        return sk_bytes, pk_bytes

    def load_private_key(self, sk_bytes: bytes) -> Any:
        """Load a private key from raw bytes.

        Args:
            sk_bytes: 32-byte raw private key.

        Returns:
            Private key object.
        """
        if not self._ed25519_available:
            raise CryptoError("Ed25519 not available")
        return self._private_key_class.from_private_bytes(sk_bytes)

    def load_public_key(self, pk_bytes: bytes) -> Any:
        """Load a public key from raw bytes.

        Args:
            pk_bytes: 32-byte raw public key.

        Returns:
            Public key object.
        """
        if not self._ed25519_available:
            raise CryptoError("Ed25519 not available")
        return self._public_key_class.from_public_bytes(pk_bytes)

    def sign(self, message: bytes, private_key: Any) -> bytes:
        """Sign a message with an Ed25519 private key.

        Args:
            message: The message to sign.
            private_key: A loaded Ed25519PrivateKey object or raw bytes.

        Returns:
            The 64-byte signature.
        """
        if isinstance(private_key, bytes):
            private_key = self.load_private_key(private_key)
        return private_key.sign(message)

    def verify(self, message: bytes, signature: bytes, public_key: Any) -> bool:
        """Verify a signature with an Ed25519 public key.

        Args:
            message: The original message.
            signature: The 64-byte signature to verify.
            public_key: A loaded Ed25519PublicKey object or raw bytes.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if isinstance(public_key, bytes):
            public_key = self.load_public_key(public_key)
        try:
            public_key.verify(signature, message)
            return True
        except Exception:
            return False

    def sign_object(
        self, obj: Dict[str, Any], private_key: Any
    ) -> Dict[str, Any]:
        """Sign a TGP object and add the signature field.

        Per the spec, the signature covers the canonical JSON of the object
        (without id and signature fields), signed with the creator's private key.

        The signature format is: "ed25519:<base64-encoded-signature>"

        Args:
            obj: The TGP object to sign (without 'signature' field).
            private_key: Ed25519 private key (object or raw bytes).

        Returns:
            A new dict with the 'signature' field added.
        """
        import base64

        # Create a copy without existing signature
        obj_copy = dict(obj)
        obj_copy.pop("signature", None)

        # Compute the hash of the canonical form
        canonical = canonicalize(obj_copy)
        message = hashlib.sha256(canonical.encode("utf-8")).digest()

        # Sign
        sig_bytes = self.sign(message, private_key)
        sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

        # Add signature
        obj_copy["signature"] = SIGN_ALGO + ":" + sig_b64
        return obj_copy

    def verify_object(
        self, obj: Dict[str, Any], public_key: Any
    ) -> bool:
        """Verify the signature on a TGP object.

        Args:
            obj: The signed TGP object with 'signature' field.
            public_key: Ed25519 public key (object or raw bytes).

        Returns:
            True if the signature is valid, False otherwise.
            Returns False if the object has no 'signature' field.
        """
        import base64

        if "signature" not in obj:
            return False

        sig_field = obj["signature"]
        if not sig_field.startswith("ed25519:"):
            return False

        sig_b64 = sig_field[8:]  # Remove "ed25519:" prefix
        try:
            sig_bytes = base64.b64decode(sig_b64)
        except Exception:
            return False

        # Create a copy without signature for verification
        obj_copy = dict(obj)
        obj_copy.pop("signature", None)

        # Compute the hash of the canonical form
        canonical = canonicalize(obj_copy)
        message = hashlib.sha256(canonical.encode("utf-8")).digest()

        return self.verify(message, sig_bytes, public_key)


# ============================================================================
# Stub implementation for environments without cryptography library
# ============================================================================

class StubCryptoManager(CryptoManager):
    """Stub crypto manager for development without the cryptography library.

    WARNING: This provides NO actual security. It should only be used for:
        - Development and testing
        - Demonstrations
        - Environments where Ed25519 cannot be installed

    NEVER use this in production. Install the cryptography library instead.
    """

    def __init__(self) -> None:
        """Initialize the stub crypto manager."""
        self._ed25519_available = False

    def is_available(self) -> bool:
        return False

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Generate a fake key pair (zeros).

        Returns:
            Tuple of (32 zero bytes, 32 zero bytes).
        """
        return b'\x00' * 32, b'\x00' * 32

    def sign(self, message: bytes, private_key: Any) -> bytes:
        """Return a fake signature (zeros).

        Returns:
            64 zero bytes.
        """
        return b'\x00' * 64

    def verify(self, message: bytes, signature: bytes, public_key: Any) -> bool:
        """Always returns True (insecure!).

        Returns:
            Always True.
        """
        return True

    def sign_object(
        self, obj: Dict[str, Any], private_key: Any
    ) -> Dict[str, Any]:
        """Add a fake signature.

        Returns:
            Object with 'signature': 'ed25519:stub'.
        """
        obj_copy = dict(obj)
        obj_copy["signature"] = SIGN_ALGO + ":stub"
        return obj_copy

    def verify_object(
        self, obj: Dict[str, Any], public_key: Any
    ) -> bool:
        """Always returns True for stub signatures.

        Returns:
            True if signature field exists and starts with 'ed25519:'.
        """
        if "signature" not in obj:
            return False
        return obj["signature"].startswith("ed25519:")
