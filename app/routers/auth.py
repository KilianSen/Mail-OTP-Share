"""
Authentication router: OIDC login/logout and session management.
"""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy import select

from app.auth import oauth
from app.config import settings
from app.database import AsyncSessionLocal, User

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/login")
async def login(request: Request):
    if not settings.OIDC_CLIENT_ID:
        return HTMLResponse(
            "<h2>OpenID Connect not configured.</h2>"
            "<p>Set OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, and OIDC_DISCOVERY_URL in your environment.</p>"
        )
    redirect_uri = settings.APP_BASE_URL.rstrip("/") + "/auth/callback"
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request):
    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception as exc:
        logger.error("OIDC callback error: %s", exc)
        return RedirectResponse(url="/?error=auth_failed")

    userinfo = token.get("userinfo") or {}
    sub = userinfo.get("sub", "")
    email = (userinfo.get("email") or "").lower()
    name = userinfo.get("name") or userinfo.get("preferred_username") or email

    if not sub or not email:
        return RedirectResponse(url="/?error=missing_userinfo")

    async with AsyncSessionLocal() as db:
        # Find or create user
        result = await db.execute(select(User).where(User.openid_sub == sub))
        user = result.scalar_one_or_none()

        if not user:
            # Try matching by email
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

        if user:
            user.openid_sub = sub
            user.display_name = name
        else:
            # Create new user
            is_admin = email == settings.ADMIN_EMAIL
            user = User(
                email=email,
                display_name=name,
                openid_sub=sub,
                is_admin=is_admin,
            )
            db.add(user)

        await db.commit()
        await db.refresh(user)

        request.session["user_id"] = user.id
        request.session["user_email"] = user.email
        request.session["is_admin"] = user.is_admin

    return RedirectResponse(url="/dashboard")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")
