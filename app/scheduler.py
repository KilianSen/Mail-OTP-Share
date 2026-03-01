"""
Background scheduler for:
1. Polling app IMAP inbox for command emails
2. Polling users' IMAP inboxes for OTPs to forward
3. Auto-approving pending share requests after timeout
4. Expiring active share requests
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crypto import decrypt
from app.database import AsyncSessionLocal, OTPShareRequest, User, AppConfig
from app.email_handler import fetch_unseen_emails, send_app_email
from app.otp_extractor import extract_otp, looks_like_otp_email

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


# ── Config helpers ─────────────────────────────────────────────────────────────

async def get_config(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    return row.value if row and row.value is not None else default


# ── Parse email command from subject ──────────────────────────────────────────

COMMAND_RE = re.compile(
    r"^(SHARE\s+REQUEST|APPROVE|DECLINE|STOP|STATUS)\s*([^\s]+)?",
    re.IGNORECASE,
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+")


def parse_command(subject: str) -> Optional[dict]:
    """
    Parse email command from subject line.
    Returns dict with 'command' and optional 'arg'.
    """
    m = COMMAND_RE.match(subject.strip())
    if not m:
        return None
    cmd = m.group(1).upper().replace(" ", "_")
    arg = (m.group(2) or "").strip()
    return {"command": cmd, "arg": arg}


# ── Process command emails ─────────────────────────────────────────────────────

async def process_command_emails():
    """Poll app IMAP inbox and process command emails."""
    if not settings.APP_IMAP_HOST:
        return

    emails = fetch_unseen_emails(
        settings.APP_IMAP_HOST,
        settings.APP_IMAP_PORT,
        settings.APP_IMAP_USER,
        settings.APP_IMAP_PASSWORD,
        settings.APP_IMAP_TLS,
    )

    if not emails:
        return

    async with AsyncSessionLocal() as db:
        for mail in emails:
            sender = _extract_email_addr(mail["from"])
            if not sender:
                continue
            parsed = parse_command(mail["subject"])
            if not parsed:
                continue
            await _dispatch_command(db, sender, parsed["command"], parsed["arg"], mail)
        await db.commit()


def _extract_email_addr(addr: str) -> Optional[str]:
    m = EMAIL_RE.search(addr)
    return m.group(0).lower() if m else None


async def _dispatch_command(db: AsyncSession, sender: str, command: str, arg: str, mail: dict):
    result = await db.execute(select(User).where(User.email == sender, User.is_active == True))
    user = result.scalar_one_or_none()

    if command == "SHARE_REQUEST":
        target_email = _extract_email_addr(arg) or _extract_email_addr(mail["body"])
        if not user:
            send_app_email(sender, "OTP Share: Error", "You are not registered in the system.")
            return
        if not target_email:
            send_app_email(sender, "OTP Share: Error", "Please specify the target email address.")
            return
        await _create_share_request(db, user, target_email)

    elif command == "APPROVE":
        req_id = _parse_int(arg)
        if not req_id:
            return
        await _approve_request(db, user, req_id)

    elif command == "DECLINE":
        req_id = _parse_int(arg)
        if not req_id:
            return
        await _decline_request(db, user, req_id)

    elif command == "STOP":
        req_id = _parse_int(arg)
        if not req_id:
            return
        await _stop_request(db, user, req_id)


def _parse_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


async def _create_share_request(db: AsyncSession, requester: User, target_email: str):
    result = await db.execute(select(User).where(User.email == target_email, User.is_active == True))
    target = result.scalar_one_or_none()
    if not target:
        send_app_email(
            requester.email, "OTP Share: Error",
            f"User {target_email} is not registered in the system."
        )
        return

    # Check for existing active/pending request
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
        send_app_email(
            requester.email, "OTP Share: Already Exists",
            "A pending or active share request already exists."
        )
        return

    share_duration = int(await get_config(db, "otp_share_duration", str(settings.DEFAULT_OTP_SHARE_DURATION)))
    approval_mode = await get_config(db, "approval_mode", settings.DEFAULT_APPROVAL_MODE)
    auto_approve_timeout = int(await get_config(db, "auto_approve_timeout", str(settings.DEFAULT_AUTO_APPROVE_TIMEOUT)))

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
    )
    db.add(req)
    await db.flush()

    send_app_email(
        requester.email, "OTP Share: Request Sent",
        f"Your OTP share request (ID: {req.id}) has been sent to {target_email}.\n"
        f"They need to approve it before OTPs will be forwarded."
    )
    send_app_email(
        target_email, f"OTP Share: Request from {requester.email}",
        f"{requester.email} wants to share OTPs from your inbox.\n\n"
        f"To APPROVE: Reply with subject: APPROVE {req.id}\n"
        f"To DECLINE: Reply with subject: DECLINE {req.id}\n\n"
        + (f"If you take no action within {auto_approve_timeout // 60} minutes, the request will be auto-approved.\n"
           if approval_mode == "auto" else "Explicit approval required.\n")
    )


async def _approve_request(db: AsyncSession, user: Optional[User], req_id: int):
    result = await db.execute(select(OTPShareRequest).where(OTPShareRequest.id == req_id))
    req = result.scalar_one_or_none()
    if not req:
        return
    if not user or req.target_id != user.id:
        return
    if req.status != "pending":
        return

    now = datetime.now(timezone.utc)
    req.status = "active"
    req.approved_at = now
    req.expires_at = now + timedelta(seconds=req.share_duration)

    # Notify requester
    result2 = await db.execute(select(User).where(User.id == req.requester_id))
    requester = result2.scalar_one_or_none()
    if requester:
        send_app_email(
            requester.email, "OTP Share: Approved",
            f"Your OTP share request (ID: {req.id}) has been approved!\n"
            f"OTPs from {user.email} will be forwarded to you until {req.expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
        )


async def _decline_request(db: AsyncSession, user: Optional[User], req_id: int):
    result = await db.execute(select(OTPShareRequest).where(OTPShareRequest.id == req_id))
    req = result.scalar_one_or_none()
    if not req or req.status != "pending":
        return
    if not user or req.target_id != user.id:
        return

    req.status = "declined"
    result2 = await db.execute(select(User).where(User.id == req.requester_id))
    requester = result2.scalar_one_or_none()
    if requester:
        send_app_email(
            requester.email, "OTP Share: Declined",
            f"Your OTP share request (ID: {req.id}) has been declined."
        )


async def _stop_request(db: AsyncSession, user: Optional[User], req_id: int):
    result = await db.execute(select(OTPShareRequest).where(OTPShareRequest.id == req_id))
    req = result.scalar_one_or_none()
    if not req or req.status not in ("pending", "active"):
        return
    # Either requester or target can stop
    if not user or (req.target_id != user.id and req.requester_id != user.id):
        return
    req.status = "cancelled"


# ── Auto-approve pending requests ─────────────────────────────────────────────

async def auto_approve_pending():
    """Auto-approve requests whose auto_approve_at has passed."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(OTPShareRequest).where(
                and_(
                    OTPShareRequest.status == "pending",
                    OTPShareRequest.auto_approve_at.isnot(None),
                    OTPShareRequest.auto_approve_at <= now,
                )
            )
        )
        reqs = result.scalars().all()
        for req in reqs:
            req.status = "active"
            req.approved_at = now
            req.expires_at = now + timedelta(seconds=req.share_duration)
            logger.info("Auto-approved share request %d", req.id)

            result2 = await db.execute(select(User).where(User.id == req.requester_id))
            requester = result2.scalar_one_or_none()
            result3 = await db.execute(select(User).where(User.id == req.target_id))
            target = result3.scalar_one_or_none()
            if requester and target:
                send_app_email(
                    requester.email, "OTP Share: Auto-Approved",
                    f"Your OTP share request (ID: {req.id}) was auto-approved.\n"
                    f"OTPs from {target.email} will be forwarded to you until "
                    f"{req.expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
                )
        await db.commit()


# ── Expire active requests ─────────────────────────────────────────────────────

async def expire_active_requests():
    """Mark expired active requests."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(OTPShareRequest).where(
                and_(
                    OTPShareRequest.status == "active",
                    OTPShareRequest.expires_at.isnot(None),
                    OTPShareRequest.expires_at <= now,
                )
            )
        )
        reqs = result.scalars().all()
        for req in reqs:
            req.status = "expired"
            logger.info("Expired share request %d", req.id)
        await db.commit()


# ── Forward OTPs ───────────────────────────────────────────────────────────────

async def forward_otps():
    """
    For each target user with active share requests:
    1. Check their IMAP inbox for new OTP emails
    2. Forward those OTPs to the requester(s)
    """
    from app.email_handler import send_email

    async with AsyncSessionLocal() as db:
        # Get all active requests
        result = await db.execute(
            select(OTPShareRequest).where(OTPShareRequest.status == "active")
        )
        active = result.scalars().all()
        if not active:
            return

        # Group by target_id to avoid duplicate IMAP logins
        by_target: dict[int, list[OTPShareRequest]] = {}
        for req in active:
            by_target.setdefault(req.target_id, []).append(req)

        for target_id, reqs in by_target.items():
            result2 = await db.execute(select(User).where(User.id == target_id))
            target = result2.scalar_one_or_none()
            if not target or not target.imap_host:
                continue

            imap_password = decrypt(target.imap_password or "")
            if not imap_password:
                continue

            emails = fetch_unseen_emails(
                target.imap_host,
                target.imap_port or 993,
                target.imap_user or target.email,
                imap_password,
                target.imap_tls if target.imap_tls is not None else True,
            )

            for mail in emails:
                subject = mail["subject"]
                body = mail["body"]
                if not looks_like_otp_email(subject, body):
                    continue

                otp = extract_otp(subject + " " + body)
                if not otp:
                    continue

                for req in reqs:
                    result3 = await db.execute(select(User).where(User.id == req.requester_id))
                    requester = result3.scalar_one_or_none()
                    if not requester or not requester.smtp_host:
                        # Fall back to app SMTP
                        send_app_email(
                            requester.email if requester else "",
                            f"OTP from {target.email}: {otp}",
                            f"Original subject: {subject}\n\nOTP: {otp}\n\nForwarded by Mail-OTP-Share",
                        )
                    else:
                        smtp_password = decrypt(requester.smtp_password or "")
                        from_addr = requester.smtp_user or requester.email
                        send_email(
                            requester.smtp_host,
                            requester.smtp_port or 587,
                            requester.smtp_user or "",
                            smtp_password,
                            requester.smtp_tls if requester.smtp_tls is not None else True,
                            from_addr,
                            requester.email,
                            f"OTP from {target.email}: {otp}",
                            f"Original subject: {subject}\n\nOTP: {otp}\n\nForwarded by Mail-OTP-Share",
                        )
                    logger.info("Forwarded OTP from %s to %s (request %d)", target.email, requester.email if requester else "?", req.id)


# ── Start / Stop ───────────────────────────────────────────────────────────────

def start_scheduler():
    scheduler.add_job(process_command_emails, "interval", seconds=60, id="cmd_emails", replace_existing=True)
    scheduler.add_job(forward_otps, "interval", seconds=30, id="forward_otps", replace_existing=True)
    scheduler.add_job(auto_approve_pending, "interval", seconds=30, id="auto_approve", replace_existing=True)
    scheduler.add_job(expire_active_requests, "interval", seconds=60, id="expire_requests", replace_existing=True)
    scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    scheduler.shutdown(wait=False)
