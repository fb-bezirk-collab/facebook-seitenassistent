from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import (
    STATIC_DIR,
    UPLOADS_DIR,
    create_required_directories,
)
from app.routers import (
    ai,
    home,
    importer,
    publish,
    settings,
    posts,
)


create_required_directories()


app = FastAPI(
    title="Facebook Seitenassistent",
)


app.mount(
    "/uploads",
    StaticFiles(
        directory=str(UPLOADS_DIR)
    ),
    name="uploads",
)


app.mount(
    "/static",
    StaticFiles(
        directory=str(STATIC_DIR)
    ),
    name="static",
)


app.include_router(home.router)
app.include_router(settings.router)
app.include_router(importer.router)
app.include_router(ai.router)
app.include_router(publish.router)
app.include_router(posts.router)