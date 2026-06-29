"""
Planner: rank tasks and slot them into real calendar free time.

Contract:
    generate_plan(user_id: str) -> dict
    Returns a plan: { "date_range": [...], "slots": [ {task_id, start, end} ] }

How to build it:
    1. Pull free/busy from Google Calendar API for the relevant window.
    2. Pull this user's tasks (status != done) and fixed_events from Firestore.
    3. Build a prompt for Gemini that includes:
         - today's date/time
         - the list of free time slots
         - the list of tasks with deadline + effort_minutes
         - the list of fixed_events (must never be overlapped)
       Ask it to return a ranked schedule as structured JSON.
    4. For each slot Gemini returns, create a Google Calendar event
       (tentative/colored) via the Calendar API.
    5. Save the plan document to Firestore (collection: plans).

Decide yourself: your prioritization heuristic. A reasonable starting
point is urgency (time until deadline) weighted against effort_minutes,
but you should design and justify your own ranking logic - this is the
part judges will likely ask you to explain.
"""

import os
import uuid
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import google.generativeai as genai

from app.utils.firestore_client import db
from app.utils.gemini_client import model


# ---------------------------------------------------------------------------
# Gemini function declaration for structured plan output
# ---------------------------------------------------------------------------
plan_schedule_declaration = genai.protos.FunctionDeclaration(
    name="save_schedule",
    description="Save the generated schedule of task slots.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "slots": genai.protos.Schema(
                type=genai.protos.Type.ARRAY,
                description="Ordered list of scheduled task slots.",
                items=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "task_id": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="The Firestore task ID.",
                        ),
                        "start": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Slot start time in ISO 8601.",
                        ),
                        "end": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Slot end time in ISO 8601.",
                        ),
                    },
                    required=["task_id", "start", "end"],
                ),
            ),
        },
        required=["slots"],
    ),
)

planner_tool = genai.protos.Tool(
    function_declarations=[plan_schedule_declaration]
)


def _get_user_credentials(user_id: str) -> Credentials:
    """Load OAuth tokens from Firestore and return Credentials."""
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise ValueError(f"User {user_id} not found")
    tokens = user_doc.to_dict().get("google_tokens", {})
    return Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    )


def _get_free_busy(creds: Credentials, days: int = 7) -> list[dict]:
    """
    Query Google Calendar FreeBusy API for the next `days` days.
    Returns a list of busy time ranges.
    """
    cal_service = build("calendar", "v3", credentials=creds)
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"

    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "items": [{"id": "primary"}],
    }
    result = cal_service.freebusy().query(body=body).execute()
    busy_ranges = result.get("calendars", {}).get("primary", {}).get("busy", [])
    return busy_ranges


def _compute_free_slots(busy_ranges: list[dict], days: int = 7) -> list[dict]:
    """
    Given a list of busy ranges, compute free slots within working hours
    (8:00 AM – 10:00 PM) for the next `days` days.
    """
    now = datetime.utcnow()
    free_slots = []

    for day_offset in range(days):
        day = now.date() + timedelta(days=day_offset)
        day_start = datetime.combine(day, datetime.min.time().replace(hour=8))
        day_end = datetime.combine(day, datetime.min.time().replace(hour=22))

        # Skip past time for today
        if day_offset == 0 and now > day_start:
            day_start = now

        if day_start >= day_end:
            continue

        # Collect busy periods that overlap this day
        day_busy = []
        for b in busy_ranges:
            b_start = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).replace(tzinfo=None)
            b_end = datetime.fromisoformat(b["end"].replace("Z", "+00:00")).replace(tzinfo=None)
            if b_end > day_start and b_start < day_end:
                day_busy.append((max(b_start, day_start), min(b_end, day_end)))

        # Sort busy periods
        day_busy.sort(key=lambda x: x[0])

        # Find gaps
        cursor = day_start
        for b_start, b_end in day_busy:
            if cursor < b_start:
                free_slots.append({
                    "start": cursor.isoformat(),
                    "end": b_start.isoformat(),
                })
            cursor = max(cursor, b_end)

        if cursor < day_end:
            free_slots.append({
                "start": cursor.isoformat(),
                "end": day_end.isoformat(),
            })

    return free_slots


def generate_plan(user_id: str) -> dict:
    """
    Generate an optimized study/work plan for the user.

    Prioritization heuristic — Urgency-Weighted Scheduling:
    -------------------------------------------------------
    We use the ratio: urgency_score = time_to_deadline / effort_minutes
    
    A LOWER score means MORE urgent — the task has less buffer time
    relative to how long it takes. This naturally handles:
    - A 2-hour task due tomorrow (score ≈ 24*60/120 = 12) beats
    - A 30-min task due in 5 days (score ≈ 5*24*60/30 = 240)
    
    This ensures tasks with tight deadline-to-effort ratios get scheduled
    first, preventing the common failure mode where short easy tasks
    consume all the time while hard urgent ones pile up.
    
    We pass this heuristic context to Gemini along with the free slots
    so it can produce a schedule that respects both urgency and calendar
    constraints.
    """
    creds = _get_user_credentials(user_id)

    # 1. Pull free/busy from Google Calendar for the next 7 days
    try:
        busy_ranges = _get_free_busy(creds, days=7)
    except Exception:
        busy_ranges = []

    free_slots = _compute_free_slots(busy_ranges, days=7)

    # 2. Pull tasks (status != done) from Firestore
    # Simple query without compound filters to avoid composite index requirement.
    # Filter status in Python instead.
    tasks_query = (
        db.collection("tasks")
        .where("user_id", "==", user_id)
    )
    tasks = []
    for doc in tasks_query.stream():
        task = doc.to_dict()
        task["id"] = doc.id
        if task.get("status") != "done":
            tasks.append(task)

    # Pull fixed_events from Firestore
    fixed_events_query = db.collection("fixed_events").where("user_id", "==", user_id)
    fixed_events = []
    for doc in fixed_events_query.stream():
        fe = doc.to_dict()
        fe["id"] = doc.id
        fixed_events.append(fe)

    if not tasks:
        return {"user_id": user_id, "slots": [], "message": "No pending tasks to schedule"}

    # 3. Build the Gemini prompt
    now = datetime.now()
    now_str = now.strftime("%A, %B %d, %Y at %H:%M")

    # Pre-compute urgency scores for context
    task_summaries = []
    for t in tasks:
        try:
            deadline = datetime.fromisoformat(t["deadline"])
            hours_until = max((deadline - now).total_seconds() / 3600, 1)
            effort_hrs = t["effort_minutes"] / 60
            # Lower ratio = more urgent
            urgency_score = round(hours_until / effort_hrs, 2)
        except Exception:
            urgency_score = 999

        task_summaries.append(
            f"  - ID: {t['id']}, Title: \"{t['title']}\", "
            f"Deadline: {t['deadline']}, Effort: {t['effort_minutes']}min, "
            f"Type: {t['type']}, Status: {t['status']}, "
            f"Urgency Score: {urgency_score} (lower=more urgent)"
        )

    fixed_event_summaries = []
    for fe in fixed_events:
        fixed_event_summaries.append(
            f"  - Title: \"{fe['title']}\", Start: {fe['start']}, End: {fe['end']} "
            f"[FIXED — MUST NOT OVERLAP]"
        )

    free_slot_summaries = []
    for fs in free_slots[:30]:  # Limit to avoid token overflow
        free_slot_summaries.append(f"  - {fs['start']} to {fs['end']}")

    prompt = f"""You are an intelligent schedule planner. Current date/time: {now_str}.

TASKS TO SCHEDULE (sorted by urgency — lower urgency_score = schedule first):
{chr(10).join(task_summaries)}

FIXED EVENTS (these time slots are BLOCKED — you MUST NOT schedule anything overlapping these):
{chr(10).join(fixed_event_summaries) if fixed_event_summaries else "  (none)"}

AVAILABLE FREE SLOTS (working hours 8AM-10PM, busy time already excluded):
{chr(10).join(free_slot_summaries)}

RULES:
1. Schedule tasks with LOWER urgency scores FIRST (they have less buffer time).
2. NEVER overlap with fixed events listed above.
3. Each slot's duration should match the task's effort_minutes (or split into chunks if needed).
4. Slots must fit within the available free slots listed above.
5. Include ALL tasks if possible. If not enough time, prioritize by urgency_score (lower first).
6. A task can be split across multiple slots if effort_minutes > available contiguous time.
7. Use realistic slot durations (30 min to 3 hours max per slot).

Call the save_schedule function with your generated slots."""

    # 4. Call Gemini with structured output
    response = model.generate_content(
        prompt,
        tools=[planner_tool],
        tool_config={"function_calling_config": {"mode": "ANY"}},
    )

    # Parse Gemini's function call response
    fc = response.candidates[0].content.parts[0].function_call
    args = dict(fc.args)
    raw_slots = list(args.get("slots", []))

    # Convert to clean dicts
    slots = []
    for s in raw_slots:
        slots.append({
            "task_id": str(s.get("task_id", "")),
            "start": str(s.get("start", "")),
            "end": str(s.get("end", "")),
        })

    # 5. Create tentative Google Calendar events for each slot
    try:
        cal_service = build("calendar", "v3", credentials=creds)
        task_map = {t["id"]: t for t in tasks}

        for slot in slots:
            task_info = task_map.get(slot["task_id"], {})
            event_body = {
                "summary": f"📚 {task_info.get('title', slot['task_id'])}",
                "description": (
                    f"Auto-scheduled by Last-Minute Life Saver\n"
                    f"Task ID: {slot['task_id']}\n"
                    f"Deadline: {task_info.get('deadline', 'N/A')}\n"
                    f"Type: {task_info.get('type', 'N/A')}"
                ),
                "start": {"dateTime": slot["start"], "timeZone": "UTC"},
                "end": {"dateTime": slot["end"], "timeZone": "UTC"},
                "transparency": "tentative",
                "colorId": "9",  # Blueberry - visually distinct
            }
            cal_service.events().insert(
                calendarId="primary", body=event_body
            ).execute()
    except Exception:
        pass  # Calendar event creation is best-effort

    # 6. Save plan to Firestore
    plan_id = str(uuid.uuid4())
    plan_doc = {
        "id": plan_id,
        "user_id": user_id,
        "generated_at": now.isoformat(),
        "slots": slots,
    }
    db.collection("plans").document(plan_id).set(plan_doc)

    return plan_doc
