"""
Password hashing and verification utilities.

Uses passlib's bcrypt for secure password storage.
"""
from __future__ import annotations

from passlib.context import CryptContext

# Configure passlib context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash for the given plain password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hashed form."""
    return pwd_context.verify(plain_password, hashed_password)
