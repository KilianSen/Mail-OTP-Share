"""
Email sending and IMAP monitoring utilities.
"""
import asyncio
import email
import imaplib
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header, make_header
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _decode_str(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value) if value else ""


def _get_email_header(msg, header: str) -> str:
    raw = msg.get(header, "")
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return _decode_str(raw)


def _extract_body(msg) -> str:
    """Extract plain text body from an email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body += payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body


def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_tls: bool,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
) -> bool:
    """Send an email. Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        context = ssl.create_default_context()
        if smtp_tls and smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, to_addr, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                if smtp_tls:
                    server.starttls(context=context)
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, to_addr, msg.as_string())
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_addr, exc)
        return False


def send_app_email(to_addr: str, subject: str, body: str, html_body: Optional[str] = None) -> bool:
    """Send an email using the application's own SMTP credentials."""
    if not settings.APP_SMTP_HOST:
        logger.warning("APP_SMTP_HOST not configured; cannot send email")
        return False
    from_addr = settings.APP_SMTP_FROM or settings.APP_SMTP_USER
    return send_email(
        settings.APP_SMTP_HOST,
        settings.APP_SMTP_PORT,
        settings.APP_SMTP_USER,
        settings.APP_SMTP_PASSWORD,
        settings.APP_SMTP_TLS,
        from_addr,
        to_addr,
        subject,
        body,
        html_body,
    )


def fetch_unseen_emails(
    imap_host: str,
    imap_port: int,
    imap_user: str,
    imap_password: str,
    imap_tls: bool,
    mailbox: str = "INBOX",
) -> list[dict]:
    """
    Connect to IMAP and fetch unseen emails.
    Returns list of dicts with keys: uid, subject, from, body, date, raw_msg
    """
    results = []
    try:
        if imap_tls:
            context = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=context)
        else:
            conn = imaplib.IMAP4(imap_host, imap_port)
        conn.login(imap_user, imap_password)
        conn.select(mailbox)

        status, data = conn.search(None, "UNSEEN")
        if status != "OK":
            conn.logout()
            return results

        uids = data[0].split()
        for uid in uids:
            status, msg_data = conn.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            subject = _get_email_header(msg, "Subject")
            from_addr = _get_email_header(msg, "From")
            date_str = _get_email_header(msg, "Date")
            body = _extract_body(msg)
            results.append({
                "uid": uid.decode(),
                "subject": subject,
                "from": from_addr,
                "body": body,
                "date": date_str,
                "raw_msg": msg,
            })
            # Mark as seen
            conn.store(uid, "+FLAGS", "\\Seen")

        conn.logout()
    except Exception as exc:
        logger.error("IMAP fetch error for %s@%s: %s", imap_user, imap_host, exc)
    return results


def test_imap_connection(host: str, port: int, user: str, password: str, tls: bool) -> tuple[bool, str]:
    """Test IMAP connection. Returns (success, message)."""
    try:
        if tls:
            context = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(host, port, ssl_context=context)
        else:
            conn = imaplib.IMAP4(host, port)
        conn.login(user, password)
        conn.logout()
        return True, "Connection successful"
    except Exception as exc:
        return False, str(exc)


def test_smtp_connection(host: str, port: int, user: str, password: str, tls: bool) -> tuple[bool, str]:
    """Test SMTP connection. Returns (success, message)."""
    try:
        context = ssl.create_default_context()
        if tls and port == 465:
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                server.login(user, password)
        else:
            with smtplib.SMTP(host, port) as server:
                server.ehlo()
                if tls:
                    server.starttls(context=context)
                server.login(user, password)
        return True, "Connection successful"
    except Exception as exc:
        return False, str(exc)
