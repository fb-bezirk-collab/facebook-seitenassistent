from fastapi import APIRouter


router = APIRouter(
    prefix="/publish",
    tags=["Veröffentlichung"],
)