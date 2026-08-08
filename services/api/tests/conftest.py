import os, uuid
os.environ.update(DATABASE_URL="sqlite://",AUTH_MODE="development")
import pytest
import io
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
@event.listens_for(engine,"connect")
def enable_sqlite_foreign_keys(connection,record):
    cursor=connection.cursor();cursor.execute("PRAGMA foreign_keys=ON");cursor.close()
Testing=sessionmaker(engine,expire_on_commit=False)
@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
@pytest.fixture(autouse=True)
def mock_private_media(monkeypatch):
    output=io.BytesIO();Image.new("RGB",(4,4),"white").save(output,"JPEG")
    monkeypatch.setattr("app.routes.media_bytes",lambda media:output.getvalue())
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
