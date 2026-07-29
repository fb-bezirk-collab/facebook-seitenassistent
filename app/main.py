from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import auth_status, get_auth_settings, is_authenticated
from app.config import STATIC_DIR, UPLOADS_DIR, create_required_directories
from app.routers import ai, auth, home, importer, planning, posts, publish, settings


create_required_directories()
auth_settings = get_auth_settings()

app = FastAPI(
    title="Facebook Seitenassistent",
    version="1.2.0",
)

@app.middleware("http")
async def require_login(request: Request, call_next):
    public_paths = {"/login", "/health"}
    public_prefixes = ("/static/",)

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


# SessionMiddleware muss außerhalb der Login-Prüfung liegen, damit
# request.session bereits in require_login verfügbar ist.
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
app.include_router(ai.router)
app.include_router(publish.router)
app.include_router(posts.router)
app.include_router(planning.router)


@app.get("/health", include_in_schema=False)
def healthcheck() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "1.2.0", "auth": auth_status()})
