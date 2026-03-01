"""
Integration tests for the FastAPI web application.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Use a temporary DB for tests
import os
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-tests")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test_otpshare.db")

from app.main import app
from app.database import init_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    os.makedirs("data", exist_ok=True)
    await init_db()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_home_page(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Mail-OTP-Share" in response.text


@pytest.mark.asyncio
async def test_login_redirect_when_not_authenticated(client):
    """Unauthenticated access to /dashboard should redirect to login."""
    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/auth/login" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_shares_redirect_when_not_authenticated(client):
    response = await client.get("/shares/", follow_redirects=False)
    assert response.status_code in (302, 307)


@pytest.mark.asyncio
async def test_profile_redirect_when_not_authenticated(client):
    response = await client.get("/users/profile", follow_redirects=False)
    assert response.status_code in (302, 307)


@pytest.mark.asyncio
async def test_admin_redirect_when_not_authenticated(client):
    response = await client.get("/admin/", follow_redirects=False)
    assert response.status_code in (302, 307)
