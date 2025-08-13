import jwt
from app.token import create_access_token
from app.config import settings


def test_create_access_token_roundtrip_subject():
    tok = create_access_token("user@example.com")
    decoded = jwt.decode(tok, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert decoded["sub"] == "user@example.com"
    assert "exp" in decoded
    assert "iat" in decoded
