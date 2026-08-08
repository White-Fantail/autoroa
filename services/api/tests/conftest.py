import os, uuid
os.environ.update(DATABASE_URL="sqlite://",AUTH_MODE="development")
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
Testing=sessionmaker(engine,expire_on_commit=False)
@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
@pytest.fixture
def db():
    with Testing() as session:yield session
@pytest.fixture
def client():
    def override():
        with Testing() as session:yield session
    app.dependency_overrides[get_db]=override
    with TestClient(app,raise_server_exceptions=True) as c:yield c
    app.dependency_overrides.clear()
@pytest.fixture
def user_headers():return {"Authorization":f"Bearer dev:{uuid.uuid4()}"}
