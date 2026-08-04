import asyncio
from contextlib import asynccontextmanager, suppress
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import auth_status, get_auth_settings, is_authenticated
from app.config import STATIC_DIR, UPLOADS_DIR, create_required_directories
from app.routers import ai, auth, home, importer, manual_upload, planning, posts, publish, settings
from app.services.publication_runner import PublicationRunner


create_required_directories()
auth_settings = get_auth_settings()
publication_runner = PublicationRunner()


async def publication_scheduler() -> None:
    while True:
        try:
            await asyncio.to_thread(publication_runner.publish_due)
        except Exception as exc:
            print(f"Fehler im Veröffentlichungs-Scheduler: {exc}", flush=True)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler_task = asyncio.create_task(publication_scheduler())
    try:
        yield
    finally:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


app = FastAPI(
    title="Facebook Seitenassistent",
    version="2.0.1",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_login(request: Request, call_next):
    public_paths = {"/login", "/health", "/robots.txt"}
    public_prefixes = ("/static/", "/uploads/")

    if (
        request.url.path in public_paths
        or request.url.path.startswith(public_prefixes)
        or is_authenticated(request)
    ):
        return await call_next(request)

    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query

    return RedirectResponse(
        url="/login?next=" + quote(target, safe=""),
        status_code=303,
    )


app.add_middleware(
    SessionMiddleware,
    secret_key=auth_settings.session_secret,
    session_cookie="facebook_seitenassistent_session",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
    https_only=auth_settings.secure_cookie,
)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(home.router)
app.include_router(settings.router)
app.include_router(importer.router)
app.include_router(manual_upload.router)
app.include_router(ai.router)
app.include_router(publish.router)
app.include_router(posts.router)
app.include_router(planning.router)


@app.get("/health", include_in_schema=False)
def healthcheck() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "2.0.1", "auth": auth_status()})


@app.get("/robots.txt", include_in_schema=False)
def robots_txt() -> PlainTextResponse:
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /uploads/\n"
        "Disallow: /\n"
    )
