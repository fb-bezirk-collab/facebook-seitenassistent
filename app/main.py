from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Facebook Seitenassistent")

templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def startseite(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )