"""
Tool implementations for Gemini function calling.

Define each of these as a Gemini FunctionDeclaration AND implement the
matching Python function that actually executes it. Gemini decides
WHICH to call based on context you give it in drift.py - you just need
to make each tool trustworthy to call.

Tools to implement:
    - reprioritize(new_order: list[str]) -> updates Firestore plan + Calendar
    - move_event(task_id: str, new_start: str, new_end: str) -> Calendar API update
    - draft_email(to: str, subject: str, body: str) -> saves a DRAFT only,
          returns draft_id. Does NOT send - sending requires a separate
          explicit user confirmation call (send_draft(draft_id)).
    - notify(message: str) -> sends an FCM push notification to the user


Safety note: draft_email must never auto-send. This is a deliberate
human-in-the-loop boundary worth highlighting in your demo and report -
it's also a legitimate design decision a judge may ask about.
"""

import os
import base64
from email.mime.text import MIMEText
from datetime import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from firebase_admin import messaging
import google.generativeai as genai

from app.utils.firestore_client import db


# ---------------------------------------------------------------------------
# Helper: build Google API credentials from a user's stored tokens
# ---------------------------------------------------------------------------
def _get_user_credentials(user_id: str) -> Credentials:
    """Load OAuth tokens from Firestore and return google.oauth2 Credentials."""
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise ValueError(f"User {user_id} not found in Firestore")
    tokens = user_doc.to_dict().get("google_tokens", {})
    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    )
    return creds


# ---------------------------------------------------------------------------
# Context holder: set by drift.py before executing tool calls so tools
# know which user they're acting on behalf of.
# ---------------------------------------------------------------------------
_current_user_id: str | None = None


def set_current_user(user_id: str):
    """Must be called before dispatching any tool calls."""
    global _current_user_id
    _current_user_id = user_id


def _uid() -> str:
    if _current_user_id is None:
        raise RuntimeError("set_current_user() was not called before tool execution")
    return _current_user_id


# ---------------------------------------------------------------------------
# Gemini FunctionDeclarations — these are passed to Gemini so it can
# decide which tool(s) to invoke during the drift-detection loop.
# ---------------------------------------------------------------------------
reprioritize_declaration = genai.protos.FunctionDeclaration(
    name="reprioritize",
    description=(
        "Reorder the user's plan by providing a new ordered list of task IDs. "
        "Updates the Firestore plan document and reorders corresponding "
        "Google Calendar events to match the new priority sequence."
    ),
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "new_order": genai.protos.Schema(
                type=genai.protos.Type.ARRAY,
                items=genai.protos.Schema(type=genai.protos.Type.STRING),
                description="Ordered list of task IDs from highest to lowest priority.",
            ),
        },
        required=["new_order"],
    ),
)

move_event_declaration = genai.protos.FunctionDeclaration(
    name="move_event",
    description=(
        "Move a scheduled task to a different time slot. Updates the "
        "Google Calendar event and the Firestore plan slot for the given task."
    ),
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "task_id": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="The Firestore task ID to reschedule.",
            ),
            "new_start": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="New start time in ISO 8601 format.",
            ),
            "new_end": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="New end time in ISO 8601 format.",
            ),
        },
        required=["task_id", "new_start", "new_end"],
    ),
)

draft_email_declaration = genai.protos.FunctionDeclaration(
    name="draft_email",
    description=(
        "Create a Gmail DRAFT (never sends automatically). Use this to "
        "compose an email requesting a deadline extension or notifying "
        "someone about schedule changes. The draft will be staged for "
        "the user to review and explicitly send."
    ),
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "to": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="Recipient email address.",
            ),
            "subject": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="Email subject line.",
            ),
            "body": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="Plain-text email body.",
            ),
        },
        required=["to", "subject", "body"],
    ),
)

send_draft_declaration = genai.protos.FunctionDeclaration(
    name="send_draft",
    description=(
        "Send a previously created Gmail draft. This should ONLY be called "
        "after the user has explicitly confirmed they want to send the draft. "
        "Never call this automatically."
    ),
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "draft_id": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="The Gmail draft ID to send.",
            ),
        },
        required=["draft_id"],
    ),
)

notify_declaration = genai.protos.FunctionDeclaration(
    name="notify",
    description=(
        "Send a push notification to the user via Firebase Cloud Messaging "
        "with a summary message about schedule changes or drift alerts."
    ),
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "message": genai.protos.Schema(
                type=genai.protos.Type.STRING,
                description="Notification message text.",
            ),
        },
        required=["message"],
    ),
)

# Collect all declarations for easy import in drift.py
# NOTE: send_draft is intentionally excluded — Gemini should never
# autonomously decide to send an email. That's the human-in-loop boundary.
tool_declarations = genai.protos.Tool(
    function_declarations=[
        reprioritize_declaration,
        move_event_declaration,
        draft_email_declaration,
        notify_declaration,
    ]
)

# Map function names → implementations for dispatch
TOOL_DISPATCH = {
    "reprioritize": lambda args: reprioritize(args["new_order"]),
    "move_event": lambda args: move_event(args["task_id"], args["new_start"], args["new_end"]),
    "draft_email": lambda args: draft_email(args["to"], args["subject"], args["body"]),
    "send_draft": lambda args: send_draft(args["draft_id"]),
    "notify": lambda args: notify(args["message"]),
}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def reprioritize(new_order: list[str]) -> dict:
    """
    Reorder the user's plan slots according to new_order (list of task IDs).
    Updates Firestore plan document and reorders Google Calendar events
    so they appear sequentially in the new priority order.
    """
    user_id = _uid()
    creds = _get_user_credentials(user_id)
    cal_service = build("calendar", "v3", credentials=creds)

    # Fetch the latest plan
    # Simple query without order_by to avoid composite index requirement.
    plans_ref = db.collection("plans")
    plan_query = (
        plans_ref
        .where("user_id", "==", user_id)
    )
    plan_docs = list(plan_query.stream())
    # Sort by generated_at descending in Python, pick the latest
    plan_docs.sort(
        key=lambda d: d.to_dict().get("generated_at", ""),
        reverse=True,
    )
    if not plan_docs:
        return {"status": "no_plan", "message": "No plan found to reprioritize"}

    plan_doc = plan_docs[0]
    plan_data = plan_doc.to_dict()
    slots = plan_data.get("slots", [])

    # Build a map of task_id → slot
    slot_map = {s["task_id"]: s for s in slots}

    # Collect the existing time windows (sorted by start)
    time_windows = sorted(
        [(s["start"], s["end"]) for s in slots],
        key=lambda x: x[0],
    )

    # Reorder: assign tasks in new_order to time windows in sequence
    new_slots = []
    for i, task_id in enumerate(new_order):
        if task_id in slot_map and i < len(time_windows):
            start, end = time_windows[i]
            new_slots.append({"task_id": task_id, "start": start, "end": end})

            # Update Google Calendar event if one exists
            old_slot = slot_map[task_id]
            try:
                # Search for the event by summary containing the task_id
                events_result = cal_service.events().list(
                    calendarId="primary",
                    timeMin=old_slot["start"],
                    timeMax=old_slot["end"],
                    q=task_id,
                ).execute()
                events = events_result.get("items", [])
                if events:
                    event = events[0]
                    event["start"] = {"dateTime": start, "timeZone": "UTC"}
                    event["end"] = {"dateTime": end, "timeZone": "UTC"}
                    cal_service.events().update(
                        calendarId="primary",
                        eventId=event["id"],
                        body=event,
                    ).execute()
            except Exception:
                pass  # Calendar update is best-effort

    # Update Firestore plan
    plan_doc.reference.update({"slots": new_slots})

    return {
        "status": "reprioritized",
        "new_order": new_order,
        "slots_updated": len(new_slots),
    }


def move_event(task_id: str, new_start: str, new_end: str) -> dict:
    """
    Move a single task's calendar event and plan slot to a new time.
    Updates both Google Calendar and the Firestore plan document.
    """
    user_id = _uid()
    creds = _get_user_credentials(user_id)
    cal_service = build("calendar", "v3", credentials=creds)

    # Update Firestore plan slot
    # Simple query without order_by to avoid composite index requirement.
    plans_ref = db.collection("plans")
    plan_query = (
        plans_ref
        .where("user_id", "==", user_id)
    )
    plan_docs = list(plan_query.stream())
    # Sort by generated_at descending in Python, pick the latest
    plan_docs.sort(
        key=lambda d: d.to_dict().get("generated_at", ""),
        reverse=True,
    )
    if not plan_docs:
        return {"status": "no_plan", "message": "No plan found"}

    plan_doc = plan_docs[0]
    plan_data = plan_doc.to_dict()
    slots = plan_data.get("slots", [])

    old_start = None
    old_end = None
    for slot in slots:
        if slot["task_id"] == task_id:
            old_start = slot["start"]
            old_end = slot["end"]
            slot["start"] = new_start
            slot["end"] = new_end
            break

    plan_doc.reference.update({"slots": slots})

    # Update Google Calendar event
    cal_event_updated = False
    if old_start and old_end:
        try:
            events_result = cal_service.events().list(
                calendarId="primary",
                timeMin=old_start,
                timeMax=old_end,
                q=task_id,
            ).execute()
            events = events_result.get("items", [])
            if events:
                event = events[0]
                event["start"] = {"dateTime": new_start, "timeZone": "UTC"}
                event["end"] = {"dateTime": new_end, "timeZone": "UTC"}
                cal_service.events().update(
                    calendarId="primary",
                    eventId=event["id"],
                    body=event,
                ).execute()
                cal_event_updated = True
        except Exception:
            pass

    return {
        "status": "moved",
        "task_id": task_id,
        "new_start": new_start,
        "new_end": new_end,
        "calendar_updated": cal_event_updated,
    }


def draft_email(to: str, subject: str, body: str) -> dict:
    """
    Create a Gmail DRAFT only — NEVER auto-send.

    This is a deliberate human-in-the-loop boundary: the agent can compose
    emails (e.g. deadline extension requests) but the user must explicitly
    confirm sending via send_draft(). This prevents irreversible actions
    from happening without human oversight.
    """
    user_id = _uid()
    creds = _get_user_credentials(user_id)
    gmail_service = build("gmail", "v1", credentials=creds)

    # Build the MIME message
    mime_message = MIMEText(body)
    mime_message["to"] = to
    mime_message["subject"] = subject

    raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("utf-8")
    draft_body = {"message": {"raw": raw}}

    draft = gmail_service.users().drafts().create(
        userId="me", body=draft_body
    ).execute()

    return {
        "status": "draft_created",
        "draft_id": draft["id"],
        "to": to,
        "subject": subject,
        "message": "Draft created — user must explicitly confirm before sending.",
    }


def send_draft(draft_id: str) -> dict:
    """
    Send a previously created Gmail draft.

    SAFETY: This function should ONLY be called after the user has explicitly
    confirmed they want to send the draft via the frontend UI. It is never
    called autonomously by the drift detection loop.
    """
    user_id = _uid()
    creds = _get_user_credentials(user_id)
    gmail_service = build("gmail", "v1", credentials=creds)

    sent = gmail_service.users().drafts().send(
        userId="me", body={"id": draft_id}
    ).execute()

    return {
        "status": "sent",
        "message_id": sent.get("id"),
        "thread_id": sent.get("threadId"),
    }


def notify(message: str) -> dict:
    """
    Send a Firebase Cloud Messaging push notification to the user.
    Uses the topic 'user_{user_id}' — the frontend subscribes to this topic.
    """
    user_id = _uid()

    # Send to user-specific topic
    topic = f"user_{user_id}"
    fcm_message = messaging.Message(
        notification=messaging.Notification(
            title="Last-Minute Life Saver",
            body=message,
        ),
        topic=topic,
    )

    try:
        response = messaging.send(fcm_message)
        return {"status": "notified", "fcm_response": response, "message": message}
    except Exception as e:
        # FCM may not be set up in dev — log but don't fail
        return {"status": "notify_failed", "error": str(e), "message": message}
