# Mail-OTP-Share

A self-hosted, Docker-deployable application that lets users securely share incoming one-time passwords (OTPs) from their email inbox with trusted family members or colleagues — via both a **web interface** and **email commands**.

---

## Features

- 🔐 **OpenID Connect** login (works with Google, Keycloak, Auth0, and any OIDC provider)
- 📧 **Email-based commands** — request, approve, decline, or stop shares by just sending an email
- ⏰ **Time-limited shares** — active shares expire automatically (default: 1 hour, configurable)
- 🔄 **Configurable approval modes**:
  - `auto` — auto-approve after a timeout (default: 10 min) unless explicitly declined
  - `strict` — requires explicit approval before any OTPs are forwarded
- 🔒 **Encrypted credentials** — IMAP/SMTP passwords are encrypted at rest using Fernet symmetric encryption
- 🛡️ **Admin panel** — manage users and configure application settings
- 🐳 **Docker-ready** — single `docker-compose up` deployment
- 📬 **Per-user SMTP/IMAP** — every user configures their own email credentials

---

## Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/KilianSen/Mail-OTP-Share.git
cd Mail-OTP-Share
cp .env.example .env
# Edit .env with your settings
```

### 2. Launch with Docker Compose

```bash
docker-compose up -d
```

The web interface will be available at `http://localhost:8000`.

---

## Configuration

All settings are in `.env`. Copy `.env.example` to get started:

| Variable | Default | Description |
|---|---|---|
| `APP_SECRET_KEY` | *(required)* | Random secret for session signing |
| `APP_BASE_URL` | `http://localhost:8000` | Public URL of your deployment |
| `OIDC_CLIENT_ID` | — | OpenID Connect client ID |
| `OIDC_CLIENT_SECRET` | — | OpenID Connect client secret |
| `OIDC_DISCOVERY_URL` | — | OIDC discovery document URL |
| `APP_IMAP_HOST` | — | IMAP host for receiving command emails |
| `APP_IMAP_PORT` | `993` | IMAP port |
| `APP_IMAP_USER` | — | IMAP username |
| `APP_IMAP_PASSWORD` | — | IMAP password |
| `APP_SMTP_HOST` | — | SMTP host for sending notifications |
| `APP_SMTP_PORT` | `587` | SMTP port |
| `APP_SMTP_USER` | — | SMTP username |
| `APP_SMTP_PASSWORD` | — | SMTP password |
| `APP_SMTP_FROM` | — | Sender address (e.g. `OTP Share <otpshare@example.com>`) |
| `DEFAULT_OTP_SHARE_DURATION` | `3600` | Share duration in seconds (1 hour) |
| `DEFAULT_APPROVAL_MODE` | `auto` | `auto` or `strict` |
| `DEFAULT_AUTO_APPROVE_TIMEOUT` | `600` | Auto-approve timeout in seconds (10 min) |
| `ADMIN_EMAIL` | — | Email of the first admin user |

### OpenID Connect Setup

Register your application with an OIDC provider and set:
- Redirect URI: `https://your-domain/auth/callback`

Example providers:
- **Google**: Discovery URL = `https://accounts.google.com/.well-known/openid-configuration`
- **Keycloak**: `https://keycloak.example.com/realms/myrealm/.well-known/openid-configuration`
- **Auth0**: `https://your-tenant.auth0.com/.well-known/openid-configuration`

---

## Email Commands

Send an email to the application's mailbox (`APP_IMAP_USER`) with the following **subject lines**:

| Subject | Action |
|---|---|
| `SHARE REQUEST user@example.com` | Request OTP sharing from that user |
| `APPROVE <request-id>` | Approve an incoming share request |
| `DECLINE <request-id>` | Decline an incoming share request |
| `STOP <request-id>` | Cancel an active or pending share |

---

## Web Interface

After signing in with OpenID Connect:

1. **Dashboard** — Overview and quick links
2. **Profile** — Configure your personal SMTP and IMAP credentials (required)
3. **Shares** — View, create, approve, decline, and stop share requests
4. **Admin** *(admins only)* — Manage users and configure global settings

---

## Architecture

```
app/
├── main.py          # FastAPI app entry point
├── config.py        # Environment-based configuration
├── database.py      # SQLAlchemy models (User, OTPShareRequest, AppConfig)
├── auth.py          # OpenID Connect (Authlib)
├── crypto.py        # Fernet encryption for stored credentials
├── email_handler.py # IMAP/SMTP utilities
├── otp_extractor.py # OTP detection via regex
├── scheduler.py     # Background tasks (poll IMAP, forward OTPs, auto-approve)
├── routers/
│   ├── auth.py      # OIDC login/callback/logout
│   ├── users.py     # Profile & credential management
│   ├── shares.py    # Share request CRUD
│   └── admin.py     # Admin panel
└── templates/       # Jinja2 HTML templates (Bootstrap 5)
static/              # CSS and JS assets
tests/               # pytest test suite
```

**Database**: SQLite (file stored in `/app/data/otpshare.db`, persisted via Docker volume)

**Background scheduler** (APScheduler) runs every 30–60 seconds to:
- Poll the app's IMAP inbox for command emails
- Scan target users' inboxes for OTP emails and forward them
- Auto-approve pending requests after timeout
- Expire active shares when the duration has passed

---

## Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set minimum required env vars
export APP_SECRET_KEY=dev-secret

# Run the app
uvicorn app.main:app --reload

# Run tests
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## Security Notes

- IMAP/SMTP passwords are encrypted using AES-256 (Fernet) keyed from `APP_SECRET_KEY`
- Sessions are signed with `APP_SECRET_KEY` — use a long, random value in production
- OTP codes are forwarded immediately and never stored
- All routes except the home page require authentication
- Admin routes additionally require the `is_admin` session flag
