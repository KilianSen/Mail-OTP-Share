"""
Admin panel routes: user management and application configuration.
"""
import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.auth import get_current_user_id, is_authenticated, is_admin_session
from app.config import settings
from app.database import AsyncSessionLocal, User, OTPShareRequest, AppConfig

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_KEYS = {
    "otp_share_duration": ("3600", "Duration (seconds) for which an OTP share remains active"),
    "approval_mode": ("auto", "Approval mode: 'auto' = auto-approve after timeout, 'strict' = explicit approval required"),
    "auto_approve_timeout": ("600", "Seconds before auto-approve triggers (only for 'auto' mode)"),
}


def _require_admin(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/auth/login", status_code=302)
    if not is_admin_session(request):
        return RedirectResponse(url="/dashboard?error=forbidden", status_code=302)
    return None


@router.get("/")
async def admin_dashboard(request: Request):
    redir = _require_admin(request)
    if redir:
        return redir

    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        shares = (await db.execute(select(OTPShareRequest).order_by(OTPShareRequest.created_at.desc()))).scalars().all()
        config_rows = (await db.execute(select(AppConfig))).scalars().all()
        config_map = {r.key: r.value for r in config_rows}

        # Ensure defaults exist
        for key, (default, desc) in DEFAULT_CONFIG_KEYS.items():
            if key not in config_map:
                config_map[key] = default

        # Build user lookup
        user_map = {u.id: u for u in users}

    return templates.TemplateResponse(request, "admin.html", {
        "users": users,
        "shares": shares,
        "config": config_map,
        "user_map": user_map,
        "config_keys": DEFAULT_CONFIG_KEYS,
    })


@router.post("/config")
async def update_config(
    request: Request,
    otp_share_duration: int = Form(3600),
    approval_mode: str = Form("auto"),
    auto_approve_timeout: int = Form(600),
):
    redir = _require_admin(request)
    if redir:
        return redir

    if approval_mode not in ("auto", "strict"):
        approval_mode = "auto"

    values = {
        "otp_share_duration": str(otp_share_duration),
        "approval_mode": approval_mode,
        "auto_approve_timeout": str(auto_approve_timeout),
    }

    async with AsyncSessionLocal() as db:
        for key, value in values.items():
            result = await db.execute(select(AppConfig).where(AppConfig.key == key))
            row = result.scalar_one_or_none()
            desc = DEFAULT_CONFIG_KEYS.get(key, ("", ""))[1]
            if row:
                row.value = value
            else:
                db.add(AppConfig(key=key, value=value, description=desc))
        await db.commit()

    return RedirectResponse(url="/admin/?updated=1", status_code=302)


@router.post("/users/{user_id}/toggle-admin")
async def toggle_admin(request: Request, user_id: int):
    redir = _require_admin(request)
    if redir:
        return redir

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_admin = not user.is_admin
            await db.commit()

    return RedirectResponse(url="/admin/", status_code=302)


@router.post("/users/{user_id}/toggle-active")
async def toggle_active(request: Request, user_id: int):
    redir = _require_admin(request)
    if redir:
        return redir

    current_user_id = get_current_user_id(request)
    if user_id == current_user_id:
        return RedirectResponse(url="/admin/?error=cant_deactivate_self", status_code=302)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_active = not user.is_active
            await db.commit()

    return RedirectResponse(url="/admin/", status_code=302)


@router.post("/shares/{req_id}/cancel")
async def cancel_share(request: Request, req_id: int):
    redir = _require_admin(request)
    if redir:
        return redir

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(OTPShareRequest).where(OTPShareRequest.id == req_id))
        req = result.scalar_one_or_none()
        if req and req.status in ("pending", "active"):
            req.status = "cancelled"
            await db.commit()

    return RedirectResponse(url="/admin/", status_code=302)
