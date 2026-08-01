from pydantic import BaseModel, Field
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.ai_service import (
    AiConfigurationError,
    AiGenerationError,
    AiService,
)


router = APIRouter(prefix="/ai", tags=["KI"])
ai_service = AiService()


class AiRewriteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    instructions: str = Field(default="", max_length=1000)


@router.post("/rewrite", include_in_schema=False)
def textvarianten_erstellen(payload: AiRewriteRequest):
    try:
        variants = ai_service.create_variants(payload.text, payload.instructions)
        return {"variants": [variant.to_dict() for variant in variants]}
    except AiConfigurationError as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    except AiGenerationError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"Unerwarteter KI-Fehler: {exc}"},
        )
