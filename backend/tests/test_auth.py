"""auth.py 단위 테스트 — 비밀번호 해시/검증, JWT 발급/디코드."""
import pytest

from backend.app.services.auth import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-do-not-use-in-prod-0123456789")


def test_hash_password_round_trip():
    hashed = hash_password("내비밀번호123")
    assert hashed != "내비밀번호123"
    assert verify_password("내비밀번호123", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("내비밀번호123")
    assert verify_password("다른비밀번호", hashed) is False


def test_create_and_decode_token_round_trip():
    token = create_token(42)
    assert decode_token(token) == 42


def test_decode_token_rejects_garbage_token():
    with pytest.raises(Exception):
        decode_token("not-a-valid-jwt")


def test_decode_token_rejects_wrong_secret(monkeypatch):
    token = create_token(42)
    monkeypatch.setenv("JWT_SECRET", "a-completely-different-secret-value")
    with pytest.raises(Exception):
        decode_token(token)
