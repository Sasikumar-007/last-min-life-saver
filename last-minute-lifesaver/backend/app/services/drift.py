"""
Drift detection: the heart of "agentic depth".

Contract:
    check_and_act(user_id: str) -> dict
    Returns a summary of what was detected and what action (if any) was taken.

How to build it:
    1. Load the latest plan for this user + current task statuses.
    2. For each slot that has already passed: was the linked task marked
       done? If not -> drift detected for that task.
    3. If drift exists, build a Gemini call WITH the function-calling tools
       defined in services/tools.py (reprioritize, draft_email, move_event,
       notify). Give Gemini the drift context and let IT decide which
       tool(s) to call and in what order - don't hardcode the response,
       that's the whole point of doing this agentically.
    4. Execute whichever tool calls Gemini returns. Some should
       auto-execute (move_event, reprioritize); irreversible ones like
       send_email should be staged for user confirmation, not auto-sent.
    5. Write every decision + reasoning to Firestore action_log, so you
       can show judges an explainable trail.

This is the file most worth getting right - it's what makes this an
agent rather than a scheduler. Take the extra time here.
"""

import uuid
from datetime import datetime

from app.utils.firestore_client import db
from app.utils.gemini_client import model
from app.services.tools import (
    tool_declarations,
    TOOL_DISPATCH,
    set_current_user,
)


def check_and_act(user_id: str) -> dict:
    """
    Core agentic drift-detection loop.

    This is NOT a hardcoded if/else decision tree. Instead:
    1. We detect drift by comparing plan slots vs task completion status
    2. We present the drift context to Gemini WITH the available tools
    3. Gemini autonomously decides which tool(s) to invoke
    4. We execute Gemini's chosen tool calls
    5. We log every decision with Gemini's reasoning for explainability

    The human-in-loop boundary: draft_email only creates drafts;
    send_draft requires explicit user confirmation and is NOT passed
    to Gemini as an available tool.
    """
    # Set the current user context so tools know who they're acting for
    set_current_user(user_id)
    now = datetime.now()

    # 1. Load latest plan for this user
    plan_query = (
        db.collection("plans")
        .where("user_id", "==", user_id)
        .order_by("generated_at", direction="DESCENDING")
        .limit(1)
    )
    plan_docs = list(plan_query.stream())
    if not plan_docs:
        return {
            "status": "no_plan",
            "drift_detected": False,
            "message": "No plan found for user. Generate a plan first.",
            "actions_taken": [],
        }

    plan_data = plan_docs[0].to_dict()
    slots = plan_data.get("slots", [])

    # 2. Check each past slot for drift — was the task completed?
    drifted_tasks = []
    on_track_tasks = []

    for slot in slots:
        slot_end_str = slot.get("end", "")
        try:
            slot_end = datetime.fromisoformat(slot_end_str)
        except (ValueError, TypeError):
            continue

        # Only check slots whose time has passed
        if slot_end > now:
            continue

        task_id = slot.get("task_id", "")
        if not task_id:
            continue

        # Look up current task status in Firestore
        task_doc = db.collection("tasks").document(task_id).get()
        if not task_doc.exists:
            continue

        task_data = task_doc.to_dict()
        status = task_data.get("status", "not_started")

        if status != "done":
            drifted_tasks.append({
                "task_id": task_id,
                "title": task_data.get("title", "Unknown"),
                "status": status,
                "scheduled_start": slot.get("start", ""),
                "scheduled_end": slot_end_str,
                "deadline": task_data.get("deadline", ""),
                "effort_minutes": task_data.get("effort_minutes", 0),
                "type": task_data.get("type", "other"),
            })
        else:
            on_track_tasks.append({
                "task_id": task_id,
                "title": task_data.get("title", "Unknown"),
            })

    # If no drift, log and return
    if not drifted_tasks:
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": now.isoformat(),
            "trigger": "drift_check",
            "reasoning": "All past scheduled slots have been completed on time. No drift detected.",
            "action_taken": "none",
            "details": {
                "on_track_count": len(on_track_tasks),
                "slots_checked": len(slots),
            },
        }
        db.collection("action_log").document(log_entry["id"]).set(log_entry)

        return {
            "status": "on_track",
            "drift_detected": False,
            "message": f"All {len(on_track_tasks)} checked tasks are on track.",
            "actions_taken": [],
        }

    # 3. Drift detected — let Gemini decide what to do.
    # Build context for Gemini with drift details.
    drift_summary_lines = []
    for dt in drifted_tasks:
        hours_until_deadline = "N/A"
        try:
            dl = datetime.fromisoformat(dt["deadline"])
            hours_left = (dl - now).total_seconds() / 3600
            hours_until_deadline = f"{hours_left:.1f} hours"
        except Exception:
            pass

        drift_summary_lines.append(
            f"- Task: \"{dt['title']}\" (ID: {dt['task_id']})\n"
            f"  Status: {dt['status']} (should be done)\n"
            f"  Was scheduled: {dt['scheduled_start']} to {dt['scheduled_end']}\n"
            f"  Deadline: {dt['deadline']} ({hours_until_deadline} remaining)\n"
            f"  Effort needed: {dt['effort_minutes']} minutes\n"
            f"  Type: {dt['type']}"
        )

    # Upcoming slots (not yet past) that could potentially be rearranged
    upcoming_slots = []
    for slot in slots:
        try:
            if datetime.fromisoformat(slot.get("end", "")) > now:
                upcoming_slots.append(slot)
        except Exception:
            pass

    upcoming_summary = ""
    if upcoming_slots:
        upcoming_lines = []
        for s in upcoming_slots[:10]:
            task_doc = db.collection("tasks").document(s["task_id"]).get()
            title = task_doc.to_dict().get("title", s["task_id"]) if task_doc.exists else s["task_id"]
            upcoming_lines.append(f"  - \"{title}\" (ID: {s['task_id']}): {s['start']} to {s['end']}")
        upcoming_summary = "UPCOMING SCHEDULED SLOTS (can be rearranged):\n" + "\n".join(upcoming_lines)

    prompt = f"""You are an intelligent schedule management agent. Current time: {now.strftime("%A, %B %d, %Y at %H:%M")}.

DRIFT DETECTED — the following tasks were scheduled but NOT completed:
{chr(10).join(drift_summary_lines)}

COMPLETED TASKS:
{chr(10).join(f'  - "{t["title"]}" ✓' for t in on_track_tasks) if on_track_tasks else "  (none yet)"}

{upcoming_summary}

You have the following tools available:
1. reprioritize(new_order) — reorder remaining tasks by priority
2. move_event(task_id, new_start, new_end) — reschedule a task to a new time
3. draft_email(to, subject, body) — create an email DRAFT (e.g. to request a deadline extension). NEVER sends — only drafts.
4. notify(message) — send a push notification to alert the user

INSTRUCTIONS:
- Analyze the drift situation and decide which tool(s) to call.
- You may call MULTIPLE tools if appropriate.
- For tasks close to their deadline with significant remaining effort, consider drafting an extension request email.
- Always notify the user about what's happening.
- Explain your reasoning clearly — your reasoning will be logged and shown to judges.
- Prioritize: rescheduling > drafting emails > notifications
- If a task is blocked, consider moving it and reprioritizing.

Act now — call the appropriate tool(s)."""

    # 4. Call Gemini with tools and let it decide
    response = model.generate_content(
        prompt,
        tools=[tool_declarations],
        tool_config={"function_calling_config": {"mode": "ANY"}},
    )

    # Extract reasoning text and function calls from response
    actions_taken = []
    reasoning_parts = []

    for part in response.candidates[0].content.parts:
        # Capture any text reasoning Gemini provides
        if hasattr(part, "text") and part.text:
            reasoning_parts.append(part.text)

        # Execute function calls Gemini decided on
        if hasattr(part, "function_call") and part.function_call.name:
            fc = part.function_call
            func_name = fc.name
            func_args = dict(fc.args)

            # Convert proto types to native Python types
            clean_args = {}
            for k, v in func_args.items():
                if hasattr(v, "__iter__") and not isinstance(v, str):
                    clean_args[k] = [str(item) for item in v]
                else:
                    clean_args[k] = str(v) if not isinstance(v, (int, float, bool)) else v
            
            # Dispatch the tool call
            if func_name in TOOL_DISPATCH:
                try:
                    result = TOOL_DISPATCH[func_name](clean_args)
                    actions_taken.append({
                        "tool": func_name,
                        "args": clean_args,
                        "result": result,
                        "status": "executed",
                    })
                except Exception as e:
                    actions_taken.append({
                        "tool": func_name,
                        "args": clean_args,
                        "error": str(e),
                        "status": "failed",
                    })
            else:
                actions_taken.append({
                    "tool": func_name,
                    "args": clean_args,
                    "status": "unknown_tool",
                })

    # Combine reasoning
    full_reasoning = " ".join(reasoning_parts) if reasoning_parts else (
        f"Drift detected for {len(drifted_tasks)} task(s). "
        f"Gemini autonomously selected {len(actions_taken)} action(s) to remediate."
    )

    # 5. Log every decision to Firestore action_log — judges will inspect this
    for action in actions_taken:
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": now.isoformat(),
            "trigger": "drift_check",
            "reasoning": full_reasoning,
            "action_taken": action.get("tool", "unknown"),
            "details": {
                "args": action.get("args", {}),
                "result": action.get("result", {}),
                "status": action.get("status", "unknown"),
                "drifted_tasks": [dt["task_id"] for dt in drifted_tasks],
            },
        }
        db.collection("action_log").document(log_entry["id"]).set(log_entry)

    # If no tool calls were made but drift was detected, log that too
    if not actions_taken:
        log_entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": now.isoformat(),
            "trigger": "drift_check",
            "reasoning": full_reasoning or "Drift detected but Gemini made no tool calls.",
            "action_taken": "none",
            "details": {
                "drifted_tasks": [dt["task_id"] for dt in drifted_tasks],
            },
        }
        db.collection("action_log").document(log_entry["id"]).set(log_entry)

    return {
        "status": "drift_handled",
        "drift_detected": True,
        "drifted_tasks": drifted_tasks,
        "reasoning": full_reasoning,
        "actions_taken": actions_taken,
        "message": f"Drift detected for {len(drifted_tasks)} task(s). {len(actions_taken)} action(s) taken.",
    }
