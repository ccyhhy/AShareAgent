import pytest

from backend.models.auth_models import UserAuthService


def _service() -> UserAuthService:
    # Hash/verify helpers do not hit database.
    return UserAuthService(db_manager=None)  # type: ignore[arg-type]


def test_bcrypt_hash_and_verify_roundtrip():
    svc = _service()
    password = "Abcd1234"

    password_hash = svc.get_password_hash(password)

    assert password_hash.startswith("$2")
    assert svc.verify_password(password, password_hash) is True
    assert svc.verify_password("WrongPass123", password_hash) is False


def test_bcrypt_rejects_password_longer_than_72_bytes():
    svc = _service()
    too_long_password = "a" * 73

    with pytest.raises(ValueError, match="72"):
        svc.get_password_hash(too_long_password)
