from app.config import settings


def register_user(client, email="user@example.com", password="password123"):
    resp = client.post("/register", json={"email": email, "password": password})
    return resp


def login_user(client, email="user@example.com", password="password123"):
    # FastAPI's OAuth2PasswordRequestForm expects form fields
    resp = client.post(
        "/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return resp


def test_register_then_login_and_me(client):
    # Register
    r = register_user(client)
    assert r.status_code == 201, r.text
    user = r.json()
    assert user["email"] == "user@example.com"

    # Duplicate register should 409
    r2 = register_user(client)
    assert r2.status_code == 409

    # Login
    r3 = login_user(client)
    assert r3.status_code == 200, r3.text
    token = r3.json()["access_token"]
    assert token

    # Access /me
    r4 = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r4.status_code == 200, r4.text
    me = r4.json()
    assert me["email"] == "user@example.com"
