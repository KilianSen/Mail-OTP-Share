import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Application
    APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "change-me-in-production")
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8000")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/otpshare.db")

    # OpenID Connect
    OIDC_CLIENT_ID: str = os.getenv("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET: str = os.getenv("OIDC_CLIENT_SECRET", "")
    OIDC_DISCOVERY_URL: str = os.getenv("OIDC_DISCOVERY_URL", "")
    OIDC_SCOPE: str = os.getenv("OIDC_SCOPE", "openid email profile")

    # App IMAP (for receiving command emails)
    APP_IMAP_HOST: str = os.getenv("APP_IMAP_HOST", "")
    APP_IMAP_PORT: int = int(os.getenv("APP_IMAP_PORT", "993"))
    APP_IMAP_USER: str = os.getenv("APP_IMAP_USER", "")
    APP_IMAP_PASSWORD: str = os.getenv("APP_IMAP_PASSWORD", "")
    APP_IMAP_TLS: bool = os.getenv("APP_IMAP_TLS", "true").lower() == "true"

    # App SMTP (for sending notification emails)
    APP_SMTP_HOST: str = os.getenv("APP_SMTP_HOST", "")
    APP_SMTP_PORT: int = int(os.getenv("APP_SMTP_PORT", "587"))
    APP_SMTP_USER: str = os.getenv("APP_SMTP_USER", "")
    APP_SMTP_PASSWORD: str = os.getenv("APP_SMTP_PASSWORD", "")
    APP_SMTP_TLS: bool = os.getenv("APP_SMTP_TLS", "true").lower() == "true"
    APP_SMTP_FROM: str = os.getenv("APP_SMTP_FROM", "")

    # OTP Share defaults (can be overridden per-request via DB config)
    DEFAULT_OTP_SHARE_DURATION: int = int(os.getenv("DEFAULT_OTP_SHARE_DURATION", "3600"))
    DEFAULT_AUTO_APPROVE_TIMEOUT: int = int(os.getenv("DEFAULT_AUTO_APPROVE_TIMEOUT", "600"))
    # Approval mode: "auto" = approve after timeout if no decline, "strict" = require explicit approval
    DEFAULT_APPROVAL_MODE: str = os.getenv("DEFAULT_APPROVAL_MODE", "auto")

    # Admin bootstrap
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")


settings = Settings()
