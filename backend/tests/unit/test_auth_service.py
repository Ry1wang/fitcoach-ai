"""Unit tests for auth service — JWT and password hashing."""
import uuid
from unittest.mock import patch

import pytest

from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_password_returns_bcrypt_hash():
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert hashed.startswith("$2b$")


def test_verify_password_correct():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("secret123")
    assert verify_password("wrongpassword", hashed) is False


def test_hash_password_different_salts():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # bcrypt uses random salt each time


# ---------------------------------------------------------------------------
# JWT creation / decoding
# ---------------------------------------------------------------------------

def test_create_and_decode_token():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id)
    decoded = decode_access_token(token)
    assert decoded == user_id


def test_decode_invalid_token():
    result = decode_access_token("not.a.valid.token")
    assert result is None


def test_decode_empty_string():
    result = decode_access_token("")
    assert result is None


def test_expired_token():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id, expires_minutes=-1)
    result = decode_access_token(token)
    assert result is None


def test_token_with_wrong_secret():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id)
    with patch("app.services.auth_service.settings") as mock_settings:
        mock_settings.JWT_SECRET = "different-secret"
        mock_settings.JWT_ALGORITHM = "HS256"
        result = decode_access_token(token)
    assert result is None


def test_custom_expiry():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id, expires_minutes=60)
    decoded = decode_access_token(token)
    assert decoded == user_id
