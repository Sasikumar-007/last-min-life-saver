"""
Entry point for the Last-Minute Life Saver backend.

This file is boilerplate: it creates the FastAPI app, sets up CORS,
and includes the routers below. It should NOT contain any agent logic.

YOUR WORK happens in:
  - app/services/extraction.py    (task extraction from raw text)
  - app/services/planner.py       (calendar-aware prioritization)
  - app/services/drift.py         (drift detection loop)
  - app/services/tools.py         (Gemini function-calling tool implementations)

Run locally with:
    uvicorn app.main:app --reload --port 8080

Deploy target: Google Cloud Run (containerized via Dockerfile in this folder).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import tasks, plan, drift, auth

app = FastAPI(title="Last-Minute Life Saver API")

# TODO: restrict allow_origins to your deployed frontend URL before submission
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(plan.router, prefix="/plan", tags=["plan"])
app.include_router(drift.router, prefix="/drift", tags=["drift"])


@app.get("/health")
def health_check():
    """Cloud Run uses this (or similar) to verify the container is alive."""
    return {"status": "ok"}
