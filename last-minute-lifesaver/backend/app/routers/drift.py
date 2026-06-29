"""
Drift routes: this is the proactive loop's entry point.

YOUR WORK:
  - POST /drift/check       -> called by Cloud Scheduler every N hours.
                              calls services/drift.py:
                                1. compare plan vs actual task status
                                2. if drifted: call Gemini with function-calling
                                   tools (services/tools.py) to decide action
                                3. log every decision to Firestore action_log
                                4. send FCM push notification with summary

This endpoint takes no user input - it runs autonomously against
whichever user(s) Cloud Scheduler is configured to check.
For the hackathon demo, you can also expose a manual trigger button
in the frontend that hits this same endpoint, to make the loop
demoable on command instead of waiting for the real schedule.
"""

from fastapi import APIRouter, Query

from app.utils.firestore_client import db
from app.services.drift import check_and_act


router = APIRouter()


@router.post("/check")
def check_drift(user_id: str = Query(default="demo_user")):
    """
    Trigger the drift detection loop.

    Called by:
    - Cloud Scheduler every 4 hours (POST /drift/check?user_id=...)
    - Manual "Check in now" button in the frontend dashboard

    This endpoint:
    1. Compares the plan schedule vs actual task completion status
    2. If drift is detected, calls Gemini with function-calling tools
       and lets the AI decide which corrective actions to take
    3. Logs every decision with Gemini's reasoning to Firestore action_log
    """
    result = check_and_act(user_id)
    return result


@router.get("/action-log")
def get_action_log(user_id: str = Query(default="demo_user")):
    """
    Fetch the action log for explainability.
    Returns all logged actions sorted by timestamp (newest first).
    Judges inspect this to understand WHY the agent did what it did.
    """
    try:
        # Simple query without order_by to avoid composite index requirement.
        # Sort in Python instead.
        log_query = (
            db.collection("action_log")
            .where("user_id", "==", user_id)
        )
        entries = []
        for doc in log_query.stream():
            entry = doc.to_dict()
            entries.append(entry)

        # Sort by timestamp descending in Python
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        # Limit to 50 entries
        entries = entries[:50]

        return {"action_log": entries}
    except Exception as e:
        print(f"Error fetching action log: {e}")
        return {"action_log": []}
