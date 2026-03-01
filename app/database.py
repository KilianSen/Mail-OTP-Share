from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import async_sessionmaker
import os

from app.config import settings

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    openid_sub = Column(String(512), unique=True, nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # SMTP credentials for sending (used to forward OTPs)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True, default=587)
    smtp_user = Column(String(255), nullable=True)
    smtp_password = Column(Text, nullable=True)  # encrypted
    smtp_tls = Column(Boolean, default=True)

    # IMAP credentials for receiving (used to read target's emails)
    imap_host = Column(String(255), nullable=True)
    imap_port = Column(Integer, nullable=True, default=993)
    imap_user = Column(String(255), nullable=True)
    imap_password = Column(Text, nullable=True)  # encrypted
    imap_tls = Column(Boolean, default=True)

    share_requests_as_requester = relationship(
        "OTPShareRequest", foreign_keys="OTPShareRequest.requester_id", back_populates="requester"
    )
    share_requests_as_target = relationship(
        "OTPShareRequest", foreign_keys="OTPShareRequest.target_id", back_populates="target"
    )


class OTPShareRequest(Base):
    __tablename__ = "otp_share_requests"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Status: pending, approved, declined, active, expired, cancelled
    status = Column(String(32), default="pending", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    # When auto-approval should trigger (for "auto" mode)
    auto_approve_at = Column(DateTime(timezone=True), nullable=True)
    # When the share becomes active
    approved_at = Column(DateTime(timezone=True), nullable=True)
    # When the share expires
    expires_at = Column(DateTime(timezone=True), nullable=True)
    # Duration in seconds
    share_duration = Column(Integer, nullable=False, default=3600)
    # Notes / reason
    note = Column(Text, nullable=True)

    requester = relationship("User", foreign_keys=[requester_id], back_populates="share_requests_as_requester")
    target = relationship("User", foreign_keys=[target_id], back_populates="share_requests_as_target")


class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
