"""
Task extraction: turn messy pasted text into structured tasks.

THIS IS YOUR FIRST FILE TO WRITE.

Contract:
    extract_tasks(raw_text: str) -> list[dict]

    Each dict must look like:
    {
        "title": str,
        "deadline": str,       # ISO 8601, e.g. "2026-06-29T23:59:00"
        "effort_minutes": int, # rough estimate
        "type": str,           # "assignment" | "exam" | "chore" | "fixed_event" | "other"
        "is_fixed": bool       # True if this must NOT be moved (e.g. a birthday dinner)
    }

How to build it:
    - Use the Gemini API (google-generativeai) with a function-calling /
      structured-output schema so you get reliable JSON back, not free text.
    - Write a clear prompt: tell Gemini today's date, ask it to find every
      task/deadline/fixed-commitment in the input, and to estimate effort
      in minutes for each task it's not told.
    - Test against messy real input (a real syllabus, a forwarded email)
      before you trust it - generic test strings will lie to you about
      reliability.

Things to decide yourself:
    - How do you handle relative dates like "due Friday" when there's no
      year mentioned? (Anchor everything to today's date, which you pass
      into the prompt.)
    - What happens if Gemini returns malformed JSON? (Validate with a
      Pydantic model, retry once on failure.)
"""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.utils.gemini_client import model


# ---------------------------------------------------------------------------
# Pydantic schema for validating each extracted task
# ---------------------------------------------------------------------------
class ExtractedTask(BaseModel):
    title: str
    deadline: str  # ISO 8601
    effort_minutes: int
    type: Literal["assignment", "exam", "chore", "fixed_event", "other"]
    is_fixed: bool


# ---------------------------------------------------------------------------
# Gemini function declaration for structured extraction
# ---------------------------------------------------------------------------
# pyrefly: ignore [missing-import]
import google.generativeai as genai

extract_tasks_declaration = genai.protos.FunctionDeclaration(
    name="save_extracted_tasks",
    description="Save the list of tasks extracted from the user's raw text input.",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "tasks": genai.protos.Schema(
                type=genai.protos.Type.ARRAY,
                description="Array of extracted tasks.",
                items=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "title": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Short descriptive title for the task.",
                        ),
                        "deadline": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Deadline in ISO 8601 format (e.g. 2026-06-29T23:59:00).",
                        ),
                        "effort_minutes": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Estimated effort in minutes to complete this task.",
                        ),
                        "type": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description='One of: "assignment", "exam", "chore", "fixed_event", "other".',
                        ),
                        "is_fixed": genai.protos.Schema(
                            type=genai.protos.Type.BOOLEAN,
                            description="True if this event/task cannot be moved (e.g. birthday dinner, exam slot).",
                        ),
                    },
                    required=["title", "deadline", "effort_minutes", "type", "is_fixed"],
                ),
            ),
        },
        required=["tasks"],
    ),
)

extraction_tool = genai.protos.Tool(
    function_declarations=[extract_tasks_declaration]
)


def _build_extraction_prompt(raw_text: str) -> str:
    """Build the extraction prompt, anchoring relative dates to today."""
    today = datetime.now()
    today_str = today.strftime("%A, %B %d, %Y")
    today_iso = today.isoformat()

    return f"""You are a task extraction assistant. Today is {today_str} ({today_iso}).

Analyze the following text and extract EVERY task, deadline, exam, assignment,
chore, fixed commitment, or scheduled event mentioned.

CRITICAL RULES:
1. Resolve ALL relative dates against today's date ({today_str}):
   - "due Friday" → the nearest upcoming Friday from today
   - "next week" → the Monday of next week
   - "tomorrow" → the day after today
   - "in 3 days" → 3 days from today
   - If no time is specified, default to 23:59:00 for deadlines
2. For each task, estimate effort_minutes if not explicitly stated
3. type must be exactly one of: "assignment", "exam", "chore", "fixed_event", "other"
4. is_fixed = true for events that cannot be moved (exams, dinners, meetings with fixed times)
5. is_fixed = false for tasks that can be scheduled flexibly (assignments, study sessions)
6. Extract ALL items — do not skip any

Call the save_extracted_tasks function with the extracted tasks.

TEXT TO ANALYZE:
---
{raw_text}
---"""


def extract_tasks(raw_text: str) -> list[dict]:
    """
    Extract structured tasks from raw text using Gemini function calling.
    Validates output with Pydantic; retries once on malformed response.
    """
    prompt = _build_extraction_prompt(raw_text)

    for attempt in range(2):  # Try up to 2 times (retry once on failure)
        try:
            response = model.generate_content(
                prompt,
                tools=[extraction_tool],
                tool_config={"function_calling_config": {"mode": "ANY"}},
            )

            # Extract the function call arguments from Gemini's response
            fc = response.candidates[0].content.parts[0].function_call
            if fc.name != "save_extracted_tasks":
                raise ValueError(f"Unexpected function call: {fc.name}")

            # Convert proto Map to regular dict, then get the tasks list
            args = dict(fc.args)
            tasks_raw = list(args["tasks"])

            # Validate each task with Pydantic
            validated_tasks = []
            for task_data in tasks_raw:
                # Convert proto MapComposite to regular dict
                task_dict = {
                    "title": str(task_data.get("title", "")),
                    "deadline": str(task_data.get("deadline", "")),
                    "effort_minutes": int(task_data.get("effort_minutes", 30)),
                    "type": str(task_data.get("type", "other")),
                    "is_fixed": bool(task_data.get("is_fixed", False)),
                }
                validated = ExtractedTask(**task_dict)
                validated_tasks.append(validated.model_dump())

            return validated_tasks

        except (ValidationError, ValueError, KeyError, IndexError, TypeError) as e:
            if attempt == 0:
                # Retry once — add extra instruction for clarity
                prompt += (
                    "\n\nPREVIOUS ATTEMPT FAILED. Please be extra careful with "
                    "the JSON structure. Each task must have: title (str), "
                    "deadline (ISO 8601 str), effort_minutes (int), "
                    'type (one of "assignment","exam","chore","fixed_event","other"), '
                    "is_fixed (bool)."
                )
                continue
            else:
                raise ValueError(
                    f"Failed to extract tasks after 2 attempts: {str(e)}"
                )

    return []  # Should never reach here
