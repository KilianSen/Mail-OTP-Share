"""
User profile and credential management routes.
"""
import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.auth import get_current_user_id, is_authenticated
from app.crypto import encrypt, decrypt
from app.database import AsyncSessionLocal, User
from app.email_handler import test_imap_connection, test_smtp_connection

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _require_login(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/auth/login", status_code=302)
    return None


@router.get("/profile")
async def profile(request: Request):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=302)
    return templates.TemplateResponse(request, "profile.html", {
        "user": user,
        "smtp_password_set": bool(user.smtp_password),
        "imap_password_set": bool(user.imap_password),
    })


@router.post("/profile/smtp")
async def update_smtp(
    request: Request,
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    smtp_user: str = Form(...),
    smtp_password: str = Form(""),
):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)
    form = await request.form()
    smtp_tls = "smtp_tls" in form
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return RedirectResponse(url="/auth/login", status_code=302)

        user.smtp_host = smtp_host
        user.smtp_port = smtp_port
        user.smtp_user = smtp_user
        user.smtp_tls = smtp_tls
        if smtp_password:
            user.smtp_password = encrypt(smtp_password)
        await db.commit()

    return RedirectResponse(url="/users/profile?updated=smtp", status_code=302)


@router.post("/profile/imap")
async def update_imap(
    request: Request,
    imap_host: str = Form(...),
    imap_port: int = Form(993),
    imap_user: str = Form(...),
    imap_password: str = Form(""),
):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)
    form = await request.form()
    imap_tls = "imap_tls" in form
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return RedirectResponse(url="/auth/login", status_code=302)

        user.imap_host = imap_host
        user.imap_port = imap_port
        user.imap_user = imap_user
        user.imap_tls = imap_tls
        if imap_password:
            user.imap_password = encrypt(imap_password)
        await db.commit()

    return RedirectResponse(url="/users/profile?updated=imap", status_code=302)


@router.post("/profile/test-smtp")
async def test_smtp(request: Request):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if not user or not user.smtp_host:
        return {"success": False, "message": "SMTP not configured"}
    password = decrypt(user.smtp_password or "")
    ok, msg = test_smtp_connection(user.smtp_host, user.smtp_port or 587, user.smtp_user or "", password, user.smtp_tls)
    return {"success": ok, "message": msg}


@router.post("/profile/test-imap")
async def test_imap(request: Request):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if not user or not user.imap_host:
        return {"success": False, "message": "IMAP not configured"}
    password = decrypt(user.imap_password or "")
    ok, msg = test_imap_connection(user.imap_host, user.imap_port or 993, user.imap_user or "", password, user.imap_tls)
    return {"success": ok, "message": msg}
