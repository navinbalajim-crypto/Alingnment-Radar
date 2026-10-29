"""Pre-send ambiguity detection service.

Identifies unclear drafts (missing tasks, vague deadlines, undefined referents)
before sending, while keeping casual and specific messages uninterrupted.
Runs locally by default and respects draft AI consent settings.
"""

import re
from typing import Any, Dict, List, Optional


CASUAL_PATTERNS = [
    r"^(?:hi|hello|hey|yo|hola|bro|buddy|dude|mate)(?:\s+[a-zA-Z0-9_-]+)*[!.?]*$",
    r"^(?:ok|okay|k|cool|sure|yep|yeah|yes|no|nope|nah|fine|alright|done|checked)[!.?]*$",
    r"^(?:thanks|thank you|thx|ty|great|nice|awesome|perfect|sounds good)[!.?]*$",
    r"^(?:okay|ok|sure|cool),\s*(?:i will|i'll)\s*(?:check|look|do it|see|review|handle it)[!.?]*$",
    r"^(?:good morning|good afternoon|good evening|good night|gm|gn)[!.?]*$",
    r"^(?:bye|see you|cya|take care|later)[!.?]*$",
]

SPECIFIC_TIME_PATTERNS = [
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    r"\b\d{1,2}\s*(?:o'clock|hrs?|hours?)\b",
    r"\b\d{1,2}:\d{2}\b",
    r"\b(?:noon|midnight|end of day|eod|cob)\b",
]

SPECIFIC_TASK_KEYWORDS = [
    "frontend", "backend", "api", "integration", "ui", "ux", "report",
    "assignment", "presentation", "slides", "documentation", "pr", "pull request",
    "database", "schema", "code review", "sprint", "feature", "bug", "issue",
    "deployment", "build", "pipeline", "proposal", "contract", "invoice", "paper",
    "exam", "test", "quiz", "homework", "deliverable", "milestone", "implementation"
]


def detect_draft_ambiguity(
    draft: str,
    conversation_context: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Analyzes draft text for actionable ambiguity prior to sending.
    Returns None if the draft is clear, casual, or sufficiently specific.
    """
    if not draft or len(draft.strip()) < 5:
        return None

    clean = draft.strip()
    clean_lower = clean.lower()

    # 1. Skip casual greetings, acknowledgments, and routine conversational remarks
    for pat in CASUAL_PATTERNS:
        if re.match(pat, clean_lower, re.I):
            return None

    # Context analysis: check if previous messages in conversation already established topic or time
    context_text = ""
    if conversation_context:
        context_text = " ".join(
            (msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", ""))
            for msg in conversation_context[-5:]
        ).lower()

    # 2. Check for deadline / submission mentions
    deadline_signals = [
        "deadline", "submission", "submit", "due date", "is due", "turn in", "hand in"
    ]
    has_deadline_signal = any(sig in clean_lower for sig in deadline_signals)

    if has_deadline_signal:
        # Check if specific time is present in draft
        has_time = any(re.search(tp, clean_lower) for tp in SPECIFIC_TIME_PATTERNS)
        # Check if specific task is present in draft
        has_task = any(re.search(r"\b" + re.escape(tk) + r"\b", clean_lower) for tk in SPECIFIC_TASK_KEYWORDS)

        # Also check if task is established in recent context
        task_in_context = any(re.search(r"\b" + re.escape(tk) + r"\b", context_text) for tk in SPECIFIC_TASK_KEYWORDS)

        # If both task and time (or timezone) are present, it is specific!
        # E.g. "Tomorrow at 10 AM IST, we need to submit the frontend implementation."
        if (has_task or task_in_context) and has_time:
            return None

        # Check for vague phrases like "Tomorrow is deadline", "tomorrow is the deadline", "deadline is tomorrow", "we have deadline"
        vague_deadline_patterns = [
            r"^(?:tomorrow|today|tonight|this week|friday|monday)\s+(?:is|has)?\s*(?:the\s+)?deadline[!.?]*$",
            r"^(?:the\s+)?deadline\s+is\s+(?:tomorrow|today|tonight|this week|friday|monday)[!.?]*$",
            r"^(?:we have|there is)\s+(?:a\s+)?deadline(?:\s+tomorrow|\s+today)?[!.?]*$",
            r"^(?:need to|we must|should|have to)\s+submit(?:\s+it|\s+this)?(?:\s+tomorrow|\s+today|\s+soon)?[!.?]*$",
            r"^tomorrow\s+(?:is\s+)?(?:submission|submitting)[!.?]*$",
        ]

        is_vague_deadline = any(re.match(vdp, clean_lower) for vdp in vague_deadline_patterns)

        if is_vague_deadline or (not has_task and not task_in_context) or (not has_time and ("tomorrow" in clean_lower or "today" in clean_lower)):
            missing_items = []
            suggested_actions = []

            if not has_task and not task_in_context:
                missing_items.append("which task or deliverable is due")
                suggested_actions.append("Add the specific task or deliverable name.")

            if not has_time:
                missing_items.append("the exact deadline time")
                suggested_actions.append("Add the deadline time if known (e.g. 10:00 AM).")

            suggested_actions.append("Clarify missing details before sending.")

            explanation = "This message may be unclear. "
            if missing_items:
                explanation += f"The recipient may not know {' or '.join(missing_items)}."
            else:
                explanation += "The recipient may need the exact time and requirements."

            # Construct template improved draft without inventing false facts
            improved = clean
            if "tomorrow is deadline" in clean_lower or "tomorrow is the deadline" in clean_lower:
                improved = "Tomorrow at [time], the [task name] is due."
            elif not has_task and has_time:
                improved = f"{clean} (for [task name])"
            elif has_task and not has_time:
                improved = f"{clean} by [time, e.g. 5:00 PM]"

            return {
                "ambiguity_detected": True,
                "ambiguity_details": explanation,
                "suggested_actions": suggested_actions,
                "clarification_prompt": "What task and time does this deadline refer to?",
                "improved_draft": improved,
            }

    # 3. Check for vague referents ("Check that thing", "Fix it now", "Review the document")
    vague_referent_patterns = [
        r"^(?:can you|please|kindly|pls)?\s*(?:check|fix|look at|review|update|test)\s+(?:that|it|that thing|this thing)[!.?]*$",
        r"^(?:did you|have you)\s+(?:finish|finished|do|done|check|checked)\s+(?:it|that)[!.?]*$",
    ]
    if any(re.match(vrp, clean_lower) for vrp in vague_referent_patterns):
        # If context doesn't clarify
        if not context_text or len(context_text.split()) < 4:
            return {
                "ambiguity_detected": True,
                "ambiguity_details": "The recipient may not know which specific item, task, or file you are referring to.",
                "suggested_actions": [
                    "Specify the exact deliverable, PR, or file name.",
                    "Include a link or identifier to give immediate context."
                ],
                "clarification_prompt": "Which specific item or task are you referring to?",
                "improved_draft": f"{clean} ([specify task or file name])",
            }

    # 4. Check for vague meeting requests ("Let's have a meeting tomorrow", "Let's meet tomorrow")
    vague_meeting = re.match(r"^(?:let'?s\s+have\s+a\s+meeting|let'?s\s+meet|we\s+need\s+to\s+meet)\s+(?:tomorrow|today|this week)[!.?]*$", clean_lower)
    if vague_meeting:
        return {
            "ambiguity_detected": True,
            "ambiguity_details": "The proposed meeting lacks a scheduled time and agenda.",
            "suggested_actions": [
                "Suggest an exact time and timezone (e.g. 3:00 PM IST).",
                "Mention the meeting topic or provide a link."
            ],
            "clarification_prompt": "What time and agenda should the meeting have?",
            "improved_draft": f"{clean} at [time, e.g. 3:00 PM] to discuss [topic].",
        }

    return None
