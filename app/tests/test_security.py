import re
from app.security import hash_password, verify_password


def test_hash_password_and_verify_success():
    plain = "s3cret-P@ss!"
    hashed = hash_password(plain)

    assert isinstance(hashed, str)
    assert hashed != plain
    # bcrypt hashes usually start with $2b$ (or $2a$/$2y$)
    assert re.match(r"^\$2[aby]?\$\d{2}\$", hashed)

    assert verify_password(plain, hashed) is True


def test_verify_password_failure_with_wrong_plain():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False
