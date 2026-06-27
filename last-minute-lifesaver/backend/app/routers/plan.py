"""
Plan routes: generate and fetch the agent's current schedule.

YOUR WORK:
  - POST /plan/generate   -> calls services/planner.py:
                              1. pull Calendar free/busy
                              2. pull current tasks + fixed_events from Firestore
                              3. ask Gemini to rank + slot tasks into free time
                              4. write resulting events to Google Calendar
                              5. save the plan snapshot to Firestore
  - GET  /plan/today       -> return today's plan from Firestore
"""

from datetime import datetime
from fastapi import APIRouter, Query

from app.utils.firestore_client import db
from app.services.planner import generate_plan as _generate_plan


router = APIRouter()


@router.post("/generate")
def generate_plan(user_id: str = Query(default="demo_user")):
    """
    Generate a new plan for the user by calling the planner service.
    This pulls Calendar free/busy, Firestore tasks, prompts Gemini,
    creates Calendar events, and saves the plan to Firestore.
    """
    plan = _generate_plan(user_id)
    return plan


@router.get("/today")
def get_today_plan(user_id: str = Query(default="demo_user")):
    """
    Fetch the latest plan document from Firestore.
    Returns the most recently generated plan, augmented with task details
    for each slot so the frontend can render a rich timeline.
    """
    plan_query = (
        db.collection("plans")
        .where("user_id", "==", user_id)
        .order_by("generated_at", direction="DESCENDING")
        .limit(1)
    )
    plan_docs = list(plan_query.stream())

    if not plan_docs:
        return {"plan": None, "message": "No plan found. Generate one first."}

    plan_data = plan_docs[0].to_dict()

    # Enrich slots with task details for the frontend
    enriched_slots = []
    for slot in plan_data.get("slots", []):
        task_id = slot.get("task_id", "")
        task_doc = db.collection("tasks").document(task_id).get()

        slot_info = {
            "task_id": task_id,
            "start": slot.get("start", ""),
            "end": slot.get("end", ""),
        }

        if task_doc.exists:
            task_data = task_doc.to_dict()
            slot_info["title"] = task_data.get("title", "Unknown Task")
            slot_info["status"] = task_data.get("status", "not_started")
            slot_info["deadline"] = task_data.get("deadline", "")
            slot_info["type"] = task_data.get("type", "other")
            slot_info["effort_minutes"] = task_data.get("effort_minutes", 0)
        else:
            slot_info["title"] = "Unknown Task"
            slot_info["status"] = "not_started"

        enriched_slots.append(slot_info)

    plan_data["slots"] = enriched_slots
    return {"plan": plan_data}
