"""FastAPI application: chat UI + ROI dashboard + JSON API.

Single-container web app. The agent and ROI report are built once at startup. Routes:

    GET  /              chat interface (htmx)
    POST /chat          handle a customer message, returns an HTML fragment (htmx) or
                        JSON (when Accept: application/json)
    GET  /dashboard     ROI dashboard
    GET  /api/roi       ROI report as JSON
    GET  /healthz       liveness probe
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .agent import SupportAgent
from .config import get_settings
from .metrics import compute_roi

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SupportCopilot", version="0.1.0")

    static_dir = _HERE / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Build the agent once; reuse across requests (it is stateless per call).
    agent = SupportAgent(settings=settings)
    app.state.agent = agent
    app.state.provider_name = agent.provider.name
    app.state.backend_name = agent.retriever.backend_name
    # Precompute the ROI summary once for the homepage proof strip (cheap: it just
    # replays the seeded tickets through the agent we already built).
    app.state.roi_summary = compute_roi(agent=agent).as_summary()

    @app.get("/healthz")
    def healthz() -> dict:
        return {
            "status": "ok",
            "provider": app.state.provider_name,
            "retrieval": app.state.backend_name,
        }

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "active": "chat",
                "provider": app.state.provider_name,
                "backend": app.state.backend_name,
                "roi": app.state.roi_summary,
            },
        )

    @app.post("/chat")
    def chat(
        request: Request,
        message: str = Form(...),
        order_id: str = Form(""),
        email: str = Form(""),
    ):
        resp = agent.handle(
            message,
            order_id=order_id.strip() or None,
            email=email.strip() or None,
        )
        wants_json = "application/json" in request.headers.get("accept", "")
        if wants_json:
            return JSONResponse(resp.to_dict())
        return templates.TemplateResponse(
            request,
            "_message.html",
            {"message": message, "resp": resp},
        )

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        report = compute_roi(agent=agent)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "active": "dashboard",
                "provider": app.state.provider_name,
                "backend": app.state.backend_name,
                "report": report,
            },
        )

    @app.get("/api/roi")
    def api_roi() -> JSONResponse:
        report = compute_roi(agent=agent)
        payload = report.as_summary()
        payload["outcomes"] = [o.__dict__ for o in report.outcomes]
        return JSONResponse(payload)

    return app


# Module-level ASGI app for `uvicorn supportcopilot.app:app`.
app = create_app()
