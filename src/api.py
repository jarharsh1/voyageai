"""
FastAPI backend for VoyageAI.

Endpoints:
  POST /plan          — Run full planning pipeline, return ranked options
  POST /book          — Execute booking after user approval
  GET  /health        — Health check
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os

app = FastAPI(title="VoyageAI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response models ────────────────────────────────────────────────

class PlanRequest(BaseModel):
    user_request: str


class BookRequest(BaseModel):
    state: dict          # The full planning state returned by /plan
    selected_option_id: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "VoyageAI"}


@app.post("/plan")
def plan_trip(req: PlanRequest):
    """
    Run the planning pipeline.
    Returns ranked route options for human review. Does NOT book anything.
    """
    if not req.user_request.strip():
        raise HTTPException(status_code=400, detail="user_request cannot be empty")

    try:
        from src.graph import run_planning_pipeline
        result = run_planning_pipeline(req.user_request)
        return {"success": True, "state": result}
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning failed: {e}")


@app.post("/book")
def book_trip(req: BookRequest):
    """
    Execute booking after explicit user approval.
    Requires the full state from /plan plus the selected_option_id.
    """
    if not req.selected_option_id.strip():
        raise HTTPException(status_code=400, detail="selected_option_id cannot be empty")
    if not req.state:
        raise HTTPException(status_code=400, detail="state cannot be empty")

    try:
        from src.graph import run_booking_pipeline
        result = run_booking_pipeline(req.state, req.selected_option_id)
        return {"success": True, "state": result}
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Booking failed: {e}")


# ─── Serve dashboard UI ───────────────────────────────────────────────────────

_UI_DIR = os.path.join(os.path.dirname(__file__), "ui")

@app.get("/")
def serve_dashboard():
    index = os.path.join(_UI_DIR, "dashboard.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "VoyageAI API is running. Dashboard not found."}
