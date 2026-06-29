"""
Task routes: ingest raw input, extract structured tasks.

YOUR WORK:
  - POST /tasks/extract     -> body: { "raw_text": "..." }
                              calls app.services.extraction.extract_tasks()
                              saves resulting tasks to Firestore, returns them
  - GET  /tasks/             -> list current user's tasks
  - PATCH /tasks/{task_id}   -> update status (not_started/in_progress/done/blocked)
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.utils.firestore_client import db
from app.services.extraction import extract_tasks


router = APIRouter()


class ExtractRequest(BaseModel):
    raw_text: str
    user_id: str = "demo_user"  # In production, get from auth session


@router.post("/extract")
def extract(req: ExtractRequest):
    """
    Extract tasks from raw text (syllabus, email, notes) using Gemini.
    Saves extracted tasks to Firestore and returns them.
    """
    # Call the extraction service
    extracted = extract_tasks(req.raw_text)

    # Save each task to Firestore
    saved_tasks = []
    for task_data in extracted:
        task_id = str(uuid.uuid4())
        task_doc = {
            "id": task_id,
            "user_id": req.user_id,
            "title": task_data["title"],
            "deadline": task_data["deadline"],
            "effort_minutes": task_data["effort_minutes"],
            "type": task_data["type"],
            "status": "not_started",
        }
        db.collection("tasks").document(task_id).set(task_doc)

        # If it's a fixed event, also save to fixed_events collection
        if task_data.get("is_fixed", False):
            fixed_event_doc = {
                "id": task_id,
                "user_id": req.user_id,
                "title": task_data["title"],
                "start": task_data["deadline"],  # Use deadline as the event time
                "end": task_data["deadline"],     # For fixed events extracted from text
            }
            db.collection("fixed_events").document(task_id).set(fixed_event_doc)

        saved_tasks.append(task_doc)

    return {"tasks": saved_tasks, "count": len(saved_tasks)}


@router.get("/")
def list_tasks(user_id: str = Query(default="demo_user")):
    """Query Firestore for current user's tasks."""
    try:
        tasks_query = db.collection("tasks").where("user_id", "==", user_id)
        tasks = []
        for doc in tasks_query.stream():
            task = doc.to_dict()
            tasks.append(task)

        # Sort by deadline
        tasks.sort(key=lambda t: t.get("deadline", ""))

        return {"tasks": tasks}
    except Exception as e:
        print(f"Error listing tasks: {e}")
        return {"tasks": []}


@router.patch("/{task_id}")
def update_task(task_id: str, status: str = Query(...)):
    """
    Update task status in Firestore.
    Valid statuses: not_started, in_progress, done, blocked
    """
    valid_statuses = {"not_started", "in_progress", "done", "blocked"}
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}",
        )

    task_ref = db.collection("tasks").document(task_id)
    task_doc = task_ref.get()
    if not task_doc.exists:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task_ref.update({"status": status})

    updated = task_ref.get().to_dict()
    return {"task": updated, "message": f"Status updated to '{status}'"}
