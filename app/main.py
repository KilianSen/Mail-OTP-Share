"""
Main FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from app.auth import is_authenticated, get_current_user_id
from app.config import settings
from app.database import init_db, AsyncSessionLocal, User
from app.routers import auth, users, shares, admin
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Mail-OTP-Share", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=settings.APP_SECRET_KEY, max_age=86400)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(shares.router)
app.include_router(admin.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "index.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/auth/login")
    user_id = get_current_user_id(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login")
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})
