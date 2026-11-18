import base64
import io

import httpx
import pytest
from PIL import Image

from src.api.main import create_app
from src.settings import Settings

ORIGIN = {"Origin": "http://localhost:8000"}


@pytest.fixture
def config(tmp_path):
    return Settings(_env_file=None, database_path=tmp_path / "sessions.sqlite3")


@pytest.fixture
async def app(config):
    application = create_app(config)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000", headers=ORIGIN
    ) as client:
        await client.get("/api/session")
        yield client


@pytest.fixture
def image():
    file = io.BytesIO()
    Image.new("RGB", (20, 20), "blue").save(file, format="PNG")
    return "data:image/png;base64," + base64.b64encode(file.getvalue()).decode()
