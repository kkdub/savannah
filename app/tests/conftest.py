import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Ensure tests always use SQLite to avoid requiring Postgres drivers
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_savannah.db")

from app.database import Base, get_db
from app.main import app
from app.config import settings


@pytest.fixture(scope="session")
def test_db_url():
    # Use a temporary SQLite file to persist across tests within a session
    db_fd, db_path = tempfile.mkstemp(prefix="test_savannah_", suffix=".db")
    os.close(db_fd)
    url = f"sqlite:///{db_path}"
    yield url
    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture()
def db_session(test_db_url):
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    # Create all tables
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
    # Ensure file handles are released on Windows
    engine.dispose()


@pytest.fixture()
def client(db_session):
    # Override the dependency to use the test session
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
