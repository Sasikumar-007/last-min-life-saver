"""
Pydantic models mirroring your Firestore collections.

These are data shape definitions only - no logic. Adjust fields if your
own schema design (from the planning step) differs from this starting
point.

Firestore collections this maps to:
    users         -> User
    tasks         -> Task
    fixed_events  -> FixedEvent
    plans         -> Plan
    action_log    -> ActionLogEntry
"""

from pydantic import BaseModel
from typing import Optional, Literal


class User(BaseModel):
    uid: str
    email: str
    display_name: Optional[str] = None
    # google_tokens stored separately / not exposed to frontend


class Task(BaseModel):
    id: str
    user_id: str
    title: str
    deadline: str  # ISO 8601
    effort_minutes: int
    type: Literal["assignment", "exam", "chore", "other"]
    status: Literal["not_started", "in_progress", "done", "blocked"] = "not_started"


class FixedEvent(BaseModel):
    id: str
    user_id: str
    title: str
    start: str  # ISO 8601
    end: str    # ISO 8601


class PlanSlot(BaseModel):
    task_id: str
    start: str
    end: str


class Plan(BaseModel):
    id: str
    user_id: str
    generated_at: str
    slots: list[PlanSlot]


class ActionLogEntry(BaseModel):
    id: str
    user_id: str
    timestamp: str
    trigger: str          # e.g. "drift_check"
    reasoning: str         # Gemini's explanation for the decision
    action_taken: str      # e.g. "move_event", "draft_email", "reprioritize"
    details: dict
