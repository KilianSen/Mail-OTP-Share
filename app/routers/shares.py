"""
OTP share request management routes.
"""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, and_, or_

from app.auth import get_current_user_id, is_authenticated
from app.config import settings
from app.database import AsyncSessionLocal, OTPShareRequest, User, AppConfig
from app.email_handler import send_app_email

router = APIRouter(prefix="/shares", tags=["shares"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _require_login(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/auth/login", status_code=302)
    return None


async def _get_config(db, key, default):
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    return row.value if row and row.value is not None else default


@router.get("/")
async def list_shares(request: Request):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(OTPShareRequest).where(
                or_(
                    OTPShareRequest.requester_id == user_id,
                    OTPShareRequest.target_id == user_id,
                )
            ).order_by(OTPShareRequest.created_at.desc())
        )
        shares = result.scalars().all()

        # Load related users
        user_ids = set()
        for s in shares:
            user_ids.add(s.requester_id)
            user_ids.add(s.target_id)
        result2 = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_map = {u.id: u for u in result2.scalars().all()}

    return templates.TemplateResponse(request, "shares.html", {
        "shares": shares,
        "users_map": users_map,
        "user_id": user_id,
        "now": datetime.now(timezone.utc),
    })


@router.get("/new")
async def new_share_form(request: Request):
    redir = _require_login(request)
    if redir:
        return redir
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_active == True))
        all_users = result.scalars().all()
    return templates.TemplateResponse(request, "new_share.html", {
        "users": all_users,
        "user_id": get_current_user_id(request),
    })


@router.post("/new")
async def create_share(
    request: Request,
    target_email: str = Form(...),
    note: str = Form(""),
):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        requester = result.scalar_one_or_none()
        if not requester:
            return RedirectResponse(url="/auth/login", status_code=302)

        result = await db.execute(
            select(User).where(User.email == target_email.lower(), User.is_active == True)
        )
        target = result.scalar_one_or_none()
        if not target:
            return templates.TemplateResponse(request, "new_share.html", {
                "error": f"User {target_email} not found.",
                "users": (await db.execute(select(User).where(User.is_active == True))).scalars().all(),
                "user_id": user_id,
            })

        if target.id == requester.id:
            return templates.TemplateResponse(request, "new_share.html", {
                "error": "You cannot request sharing from yourself.",
                "users": (await db.execute(select(User).where(User.is_active == True))).scalars().all(),
                "user_id": user_id,
            })

        # Check existing
        result = await db.execute(
            select(OTPShareRequest).where(
                and_(
                    OTPShareRequest.requester_id == requester.id,
                    OTPShareRequest.target_id == target.id,
                    OTPShareRequest.status.in_(["pending", "active"]),
                )
            )
        )
        if result.scalar_one_or_none():
            return RedirectResponse(url="/shares/?error=already_exists", status_code=302)

        share_duration = int(await _get_config(db, "otp_share_duration", str(settings.DEFAULT_OTP_SHARE_DURATION)))
        approval_mode = await _get_config(db, "approval_mode", settings.DEFAULT_APPROVAL_MODE)
        auto_approve_timeout = int(await _get_config(db, "auto_approve_timeout", str(settings.DEFAULT_AUTO_APPROVE_TIMEOUT)))

        now = datetime.now(timezone.utc)
        auto_approve_at = None
        if approval_mode == "auto":
            auto_approve_at = now + timedelta(seconds=auto_approve_timeout)

        req = OTPShareRequest(
            requester_id=requester.id,
            target_id=target.id,
            status="pending",
            auto_approve_at=auto_approve_at,
            share_duration=share_duration,
            note=note or None,
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)

        # Send notifications
        send_app_email(
            target.email,
            f"OTP Share Request from {requester.email}",
            f"{requester.email} wants to receive OTPs from your inbox.\n\n"
            f"Request ID: {req.id}\n"
            + (f"Note: {note}\n\n" if note else "\n")
            + f"Reply with subject 'APPROVE {req.id}' to approve.\n"
            f"Reply with subject 'DECLINE {req.id}' to decline.\n\n"
            + (f"Auto-approved in {auto_approve_timeout // 60} min if no action.\n"
               if approval_mode == "auto" else "Explicit approval required.\n")
        )
        send_app_email(
            requester.email,
            "OTP Share Request Sent",
            f"Your request (ID: {req.id}) to receive OTPs from {target.email} has been sent."
        )

    return RedirectResponse(url="/shares/", status_code=302)


@router.post("/{req_id}/approve")
async def approve_share(request: Request, req_id: int):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(OTPShareRequest).where(OTPShareRequest.id == req_id))
        req = result.scalar_one_or_none()
        if not req or req.target_id != user_id or req.status != "pending":
            return RedirectResponse(url="/shares/?error=invalid", status_code=302)

        now = datetime.now(timezone.utc)
        req.status = "active"
        req.approved_at = now
        req.expires_at = now + timedelta(seconds=req.share_duration)
        await db.commit()

        result2 = await db.execute(select(User).where(User.id == req.requester_id))
        requester = result2.scalar_one_or_none()
        result3 = await db.execute(select(User).where(User.id == user_id))
        target = result3.scalar_one_or_none()
        if requester and target:
            send_app_email(
                requester.email, "OTP Share: Approved",
                f"Your OTP share request (ID: {req.id}) has been approved!\n"
                f"OTPs from {target.email} will be forwarded until "
                f"{req.expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
            )

    return RedirectResponse(url="/shares/", status_code=302)


@router.post("/{req_id}/decline")
async def decline_share(request: Request, req_id: int):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(OTPShareRequest).where(OTPShareRequest.id == req_id))
        req = result.scalar_one_or_none()
        if not req or req.target_id != user_id or req.status != "pending":
            return RedirectResponse(url="/shares/?error=invalid", status_code=302)

        req.status = "declined"
        await db.commit()

        result2 = await db.execute(select(User).where(User.id == req.requester_id))
        requester = result2.scalar_one_or_none()
        result3 = await db.execute(select(User).where(User.id == user_id))
        target = result3.scalar_one_or_none()
        if requester and target:
            send_app_email(
                requester.email, "OTP Share: Declined",
                f"Your OTP share request (ID: {req.id}) has been declined by {target.email}."
            )

    return RedirectResponse(url="/shares/", status_code=302)


@router.post("/{req_id}/stop")
async def stop_share(request: Request, req_id: int):
    redir = _require_login(request)
    if redir:
        return redir
    user_id = get_current_user_id(request)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(OTPShareRequest).where(OTPShareRequest.id == req_id))
        req = result.scalar_one_or_none()
        if not req or (req.target_id != user_id and req.requester_id != user_id):
            return RedirectResponse(url="/shares/?error=invalid", status_code=302)
        if req.status not in ("pending", "active"):
            return RedirectResponse(url="/shares/?error=invalid", status_code=302)

        req.status = "cancelled"
        await db.commit()

    return RedirectResponse(url="/shares/", status_code=302)
