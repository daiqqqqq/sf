from app.core.security import hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    password = "S3cure-Pa55word!"
    password_hash = hash_password(password)
    assert verify_password(password, password_hash)
    assert not verify_password("wrong-password", password_hash)

