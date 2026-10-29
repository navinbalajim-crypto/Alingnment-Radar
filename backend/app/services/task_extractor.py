"""Intelligent task extraction service for detecting tasks and deadlines in conversation."""

import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

DEFAULT_TIMEZONE = "Asia/Kolkata"

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))

# Regular expressions for task intent
TASK_PATTERNS = [
    r"\b(submit|finish|complete|send|prepare|deliver|share|upload|push|deploy|present|fix|review|write|update)\b",
    r"\b(deadline|due|due date|assignment|report|implementation|frontend|backend|slides|project|pr|api)\b",
    r"\bremind\s+(?:me|us)\s+to\b",
]

# Incidental/past remarks to suppress
PAST_PATTERNS = [
    r"\b(yesterday|last\s+(?:week|month|night|year)|already\s+(?:finished|done|submitted))\b",
    r"\bwatched\s+a\s+movie\b",
]

CASUAL_PATTERNS = [
    r"^(hi|hello|hey|bro|thanks|thank you|ok|okay|cool|super|great|good morning|gn|bye)[\s!.]*$",
]


def _get_tz(tz_name: str = DEFAULT_TIMEZONE):
    if tz_name in {"Asia/Kolkata", "IST"}:
        return IST
    if tz_name in {"UTC", "GMT"}:
        return UTC
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return UTC


def extract_task_from_text(
    text: str,
    reference_dt: Optional[datetime] = None,
    tz_name: str = DEFAULT_TIMEZONE,
) -> Optional[Dict[str, Any]]:
    """
    Extract task details (title, due_at, advance_minutes) from message text.
    Returns None if text is casual, in the past, or lacks clear task intent.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()
    lower = cleaned.lower()

    # 1. Suppress casual or past remarks
    for cp in CASUAL_PATTERNS:
        if re.search(cp, lower):
            return None

    for pp in PAST_PATTERNS:
        if re.search(pp, lower):
            return None

    # 2. Check for task intent
    has_task_verb = any(re.search(p, lower) for p in TASK_PATTERNS)
    if not has_task_verb:
        return None

    tz = _get_tz(tz_name)
    now = reference_dt or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    target_date = None
    target_time = None

    # Parse relative day
    if re.search(r"\btomorrow\b", lower):
        target_date = (now + timedelta(days=1)).date()
    elif re.search(r"\btonight\b", lower):
        target_date = now.date()
        target_time = time(21, 0)  # default tonight = 9:00 PM
    elif re.search(r"\btoday\b", lower):
        target_date = now.date()
    else:
        # Day of week
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, day in enumerate(days):
            if re.search(rf"\b(?:next\s+)?{day}\b", lower):
                current_weekday = now.weekday()
                days_ahead = (idx - current_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target_date = (now + timedelta(days=days_ahead)).date()
                break

    # Parse time
    # Matches: 10 AM, 10:30 AM, 5 PM, 11:59 PM, 10am, 23:00, etc.
    time_match = re.search(
        r"\b(?:at\s+|before\s+|by\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        lower,
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        target_time = time(hour, minute)
    elif re.search(r"\b11:59\s*pm\b", lower):
        target_time = time(23, 59)
    elif re.search(r"\b(?:morning)\b", lower) and not target_time:
        target_time = time(10, 0)
    elif re.search(r"\b(?:afternoon)\b", lower) and not target_time:
        target_time = time(14, 0)
    elif re.search(r"\b(?:evening)\b", lower) and not target_time:
        target_time = time(18, 0)

    # If neither date nor time was found, we cannot confidently schedule a reminder
    if not target_date and not target_time:
        return None

    if not target_date:
        target_date = now.date()
        # If time already passed today, advance to tomorrow
        if target_time and datetime.combine(target_date, target_time, tzinfo=tz) <= now:
            target_date += timedelta(days=1)

    if not target_time:
        target_time = time(10, 0)  # default morning 10 AM

    due_dt = datetime.combine(target_date, target_time, tzinfo=tz)

    # Derive clean title
    title = cleaned
    # Remove leading phrases like "Tomorrow at 10 AM, we need to" or "Remind me to"
    title_sub = re.sub(
        r"^(?:(?:tomorrow|today|tonight|on\s+\w+)\s+(?:at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?,\s*)?)?"
        r"(?:(?:we\s+need\s+to|please|remind\s+me\s+to|i\s+will|let's)\s+)?",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    title_sub = re.sub(
        r"\s+(?:tomorrow|tonight|today|by\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?).*$",
        "",
        title_sub,
        flags=re.IGNORECASE,
    ).strip()

    if not title_sub:
        title_sub = "Task from conversation"
    else:
        # Capitalize first letter
        title_sub = title_sub[0].upper() + title_sub[1:]

    return {
        "title": title_sub,
        "due_at": due_dt.isoformat(),
        "timezone": tz_name,
        "advance_minutes": 30,
        "confidence": 0.9,
    }
