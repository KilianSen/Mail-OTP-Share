"""
Authentication helpers using Authlib for OpenID Connect and session management.
"""
import logging
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from starlette.config import Config as StarletteConfig

from app.config import settings

logger = logging.getLogger(__name__)

oauth = OAuth()

if settings.OIDC_CLIENT_ID and settings.OIDC_DISCOVERY_URL:
    oauth.register(
        name="oidc",
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        server_metadata_url=settings.OIDC_DISCOVERY_URL,
        client_kwargs={"scope": settings.OIDC_SCOPE},
    )


def get_current_user_id(request: Request) -> Optional[int]:
    """Get authenticated user ID from session."""
    return request.session.get("user_id")


def get_current_user_email(request: Request) -> Optional[str]:
    """Get authenticated user email from session."""
    return request.session.get("user_email")


def is_authenticated(request: Request) -> bool:
    return get_current_user_id(request) is not None


def is_admin_session(request: Request) -> bool:
    return request.session.get("is_admin", False)


def require_auth(request: Request):
    """Raise redirect to login if not authenticated."""
    from fastapi.responses import RedirectResponse
    if not is_authenticated(request):
        return RedirectResponse(url="/auth/login")
    return None
