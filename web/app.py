"""FALXON web application and JSON API."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from falxon import pipeline, store
from falxon.claims import ClaimError
from falxon.config import ROOT, settings
from falxon.http import UnsafeURLError

HERE = Path(__file__).resolve().parent

app = FastAPI(
    title="FALXON API",
    version=pipeline.ENGINE_VERSION,
    description="Evidence-grounded claim verification using Wikipedia, Wikidata and open NLI models.",
    docs_url="/api/docs",
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

VERDICT_STYLE = {
    "SUPPORTED": {"word": "Supported", "tone": "true", "dek": "The evidence backs this claim."},
    "REFUTED": {"word": "False", "tone": "false", "dek": "The evidence contradicts this claim."},
    "NOT ENOUGH INFO": {"word": "Unverified", "tone": "unknown", "dek": "We could not find enough evidence either way."},
    "CONFLICTING EVIDENCE": {"word": "Disputed", "tone": "mixed", "dek": "Relevant sources disagree."},
}
templates.env.globals["VERDICT_STYLE"] = VERDICT_STYLE
templates.env.globals["ENGINE"] = pipeline.ENGINE_VERSION


def _fmt_date(value: str | None) -> str:
    if not value:
        return ""
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return dt.strftime("%B %-d, %Y")


templates.env.filters["date"] = _fmt_date
templates.env.filters["pct"] = lambda v: f"{(v or 0) * 100:.0f}%"


# --- simple per-IP rate limit: protects the free CPU host ------------------------------
_RATE = int(os.environ.get("FALXON_RATE_PER_MINUTE", "12"))
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limit(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    now = time.time()
    with _hits_lock:
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= _RATE:
            raise HTTPException(429, "Too many checks in a minute. Please wait a moment.")
        q.append(now)


def _benchmark() -> dict | None:
    path = ROOT / "reports" / "benchmark.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


async def _check_claim(claim: str) -> str:
    claim_key = claim.strip()
    from falxon.claims import validate_claim

    normalized = validate_claim(claim_key)
    cached = store.recent_claim(normalized)
    if cached:
        return cached
    report = await run_in_threadpool(pipeline.verify, normalized)
    v = report["verdict"]
    return store.save("claim", normalized, report, v["label"], v.get("confidence"))


# --- pages -------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {
        "recent": store.latest(9, "claim"), "benchmark": _benchmark(), "active": "home",
    })


@app.post("/check")
async def check_form(request: Request, claim: str = Form("")):
    _rate_limit(request)
    try:
        check_id = await _check_claim(claim)
    except ClaimError as exc:
        return templates.TemplateResponse(request, "home.html", {
            "recent": store.latest(9, "claim"), "benchmark": _benchmark(), "error": str(exc),
            "claim": claim, "active": "home",
        }, status_code=400)
    return RedirectResponse(f"/report/{check_id}", status_code=303)


@app.post("/check-article")
async def check_article_form(request: Request, text: str = Form(""), url: str = Form("")):
    _rate_limit(request)
    if not text.strip() and not url.strip():
        return templates.TemplateResponse(request, "home.html", {
            "recent": store.latest(9, "claim"), "benchmark": _benchmark(), "active": "home", "mode": "article",
            "error": "Paste an article or enter its web address.",
        }, status_code=400)
    try:
        result = await run_in_threadpool(pipeline.verify_article, text, url.strip())
    except (UnsafeURLError, ValueError) as exc:
        return templates.TemplateResponse(request, "home.html", {
            "recent": store.latest(9, "claim"), "benchmark": _benchmark(), "active": "home", "mode": "article",
            "error": str(exc), "article_url": url, "article_text": text,
        }, status_code=400)
    except Exception:
        return templates.TemplateResponse(request, "home.html", {
            "recent": store.latest(9, "claim"), "benchmark": _benchmark(), "active": "home", "mode": "article",
            "error": "That page could not be read. Try pasting the article text instead.", "article_url": url,
        }, status_code=400)
    if not result["claims"]:
        return templates.TemplateResponse(request, "home.html", {
            "recent": store.latest(9, "claim"), "benchmark": _benchmark(), "active": "home", "mode": "article",
            "error": "No checkable factual statements were found in that text.", "article_text": text, "article_url": url,
        }, status_code=400)
    for claim_report in result["claims"]:
        v = claim_report["verdict"]
        claim_report["id"] = store.save("claim", claim_report["claim"], claim_report, v["label"], v.get("confidence"))
    title = result["title"] or (result["claims"][0]["claim"] if result["claims"] else "Article")
    check_id = store.save("article", title, result)
    return RedirectResponse(f"/article/{check_id}", status_code=303)


@app.get("/report/{check_id}", response_class=HTMLResponse)
async def report_page(request: Request, check_id: str):
    row = store.get(check_id)
    if not row or row["kind"] != "claim":
        raise HTTPException(404, "Report not found")
    return templates.TemplateResponse(request, "report.html", {"row": row, "r": row["payload"], "active": ""})


@app.get("/article/{check_id}", response_class=HTMLResponse)
async def article_page(request: Request, check_id: str):
    row = store.get(check_id)
    if not row or row["kind"] != "article":
        raise HTTPException(404, "Report not found")
    return templates.TemplateResponse(request, "article.html", {"row": row, "a": row["payload"], "active": ""})


@app.get("/archive", response_class=HTMLResponse)
async def archive(request: Request):
    return templates.TemplateResponse(request, "archive.html", {
        "rows": store.latest(100), "stats": store.stats(), "active": "archive",
    })


@app.get("/methodology", response_class=HTMLResponse)
async def methodology(request: Request):
    return templates.TemplateResponse(request, "methodology.html", {
        "benchmark": _benchmark(), "settings": settings, "active": "methodology",
    })


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(request, "error.html", {"status": exc.status_code, "detail": exc.detail, "active": ""},
                                      status_code=exc.status_code)


# --- JSON API ----------------------------------------------------------------------------
class ClaimIn(BaseModel):
    claim: str = Field(..., examples=["Sydney is the capital of Australia."])


class ArticleIn(BaseModel):
    text: str = ""
    url: str = ""


@app.get("/health")
async def health():
    return {"status": "ok", "engine": pipeline.ENGINE_VERSION}


@app.post("/api/v1/verify")
async def api_verify(request: Request, body: ClaimIn):
    _rate_limit(request)
    try:
        check_id = await _check_claim(body.claim)
    except ClaimError as exc:
        raise HTTPException(400, str(exc))
    row = store.get(check_id)
    return {"id": check_id, "report_url": f"/report/{check_id}", **row["payload"]}


@app.post("/api/v1/verify-article")
async def api_verify_article(request: Request, body: ArticleIn):
    _rate_limit(request)
    if not body.text.strip() and not body.url.strip():
        raise HTTPException(400, "Provide text or url.")
    try:
        return await run_in_threadpool(pipeline.verify_article, body.text, body.url.strip())
    except (UnsafeURLError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/v1/reports/{check_id}")
async def api_report(check_id: str):
    row = store.get(check_id)
    if not row:
        raise HTTPException(404, "Report not found")
    return row["payload"]
