from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, UPLOADS_DIR, create_required_directories
from app.routers import ai, home, importer, posts, publish, settings


create_required_directories()

app = FastAPI(
    title="Facebook Seitenassistent",
    version="1.0.0",
)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(home.router)
app.include_router(settings.router)
app.include_router(importer.router)
app.include_router(ai.router)
app.include_router(publish.router)
app.include_router(posts.router)


@app.get("/health", include_in_schema=False)
def healthcheck() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "1.0.0"})
