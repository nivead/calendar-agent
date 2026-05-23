from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from googleapiclient.discovery import build

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from auth import get_credentials

USER_TIMEZONE = "America/Los_Angeles"  # change to your timezone

def get_service():
    """Build and return an authenticated Google Calendar service."""
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds)
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from googleapiclient.discovery import build

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from auth import get_credentials

USER_TIMEZONE = "America/Los_Angeles"  # change to your timezone


def get_service():
    """Build and return an authenticated Google Calendar service."""
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds)


def _to_rfc3339(dt_str: str, tz: ZoneInfo) -> str:
    """Ensure a datetime string has proper timezone info attached."""
    if dt_str.endswith("Z"):
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).isoformat()
    if "+" in dt_str[10:] or (len(dt_str) > 19 and dt_str[19] == "-"):
        return datetime.fromisoformat(dt_str).isoformat()
    return datetime.fromisoformat(dt_str).replace(tzinfo=tz).isoformat()


@tool
def list_events(days_ahead: int = 7, max_results: int = 10) -> str:
    """
    List upcoming calendar events. Use this when the user asks what's on
    their calendar, what meetings they have, or what's coming up.

    Args:
        days_ahead: How many days into the future to look (default 7)
        max_results: Maximum number of events to return (default 10)
    """
    service = get_service()
    tz = ZoneInfo(USER_TIMEZONE)

    now = datetime.now(tz)
    end = now + timedelta(days=days_ahead)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return f"No events in the next {days_ahead} days."

    lines = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date"))
        summary = e.get("summary", "(no title)")
        event_id = e["id"]
        location = e.get("location", "")
        loc_str = f" @ {location}" if location else ""
        lines.append(f"- [{event_id}] {start}: {summary}{loc_str}")

    return "\n".join(lines)


@tool
def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendee_emails: Optional[list[str]] = None,
) -> str:
    """
    Create a new calendar event. Use this when the user wants to book,
    schedule, or add a meeting or appointment.

    Args:
        title: Title/summary of the event
        start_time: Start time in ISO 8601 format, e.g. '2026-06-01T10:00:00'
        end_time: End time in ISO 8601 format, e.g. '2026-06-01T11:00:00'
        description: Optional description or agenda
        location: Optional location or video call link
        attendee_emails: Optional list of attendee email addresses
    """
    service = get_service()
    tz = ZoneInfo(USER_TIMEZONE)

    event_body = {
        "summary": title,
        "start": {"dateTime": _to_rfc3339(start_time, tz), "timeZone": USER_TIMEZONE},
        "end":   {"dateTime": _to_rfc3339(end_time, tz),   "timeZone": USER_TIMEZONE},
    }

    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendee_emails:
        event_body["attendees"] = [{"email": e} for e in attendee_emails]

    created = service.events().insert(
        calendarId="primary",
        body=event_body,
        sendUpdates="all" if attendee_emails else "none",
    ).execute()

    return (
        f"Event created: '{created['summary']}'\n"
        f"  ID: {created['id']}\n"
        f"  Start: {created['start']['dateTime']}\n"
        f"  Link: {created.get('htmlLink', 'n/a')}"
    )


@tool
def update_event(
    event_id: str,
    title: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Update an existing calendar event. Use this when the user wants to
    reschedule, rename, or modify an existing meeting.
    Requires the event_id which can be found using list_events.

    Args:
        event_id: The Google Calendar event ID
        title: New title (optional)
        start_time: New start time in ISO 8601 format (optional)
        end_time: New end time in ISO 8601 format (optional)
        description: New description (optional)
        location: New location (optional)
    """
    service = get_service()
    tz = ZoneInfo(USER_TIMEZONE)

    # Fetch current event first
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    # Apply only the fields the user wants to change
    if title:
        event["summary"] = title
    if start_time:
        event["start"] = {"dateTime": _to_rfc3339(start_time, tz), "timeZone": USER_TIMEZONE}
    if end_time:
        event["end"] = {"dateTime": _to_rfc3339(end_time, tz), "timeZone": USER_TIMEZONE}
    if description:
        event["description"] = description
    if location:
        event["location"] = location

    updated = service.events().update(
        calendarId="primary",
        eventId=event_id,
        body=event,
    ).execute()

    return f"Event updated: '{updated['summary']}' (ID: {updated['id']})"


@tool
def delete_event(event_id: str) -> str:
    """
    Delete a calendar event permanently. Use this when the user wants to
    cancel or remove a meeting. Always confirm with the user before calling this.
    Requires the event_id which can be found using list_events.

    Args:
        event_id: The Google Calendar event ID to delete
    """
    service = get_service()

    # Fetch the event first so we can confirm the title in the response
    event = service.events().get(calendarId="primary", eventId=event_id).execute()
    title = event.get("summary", "(no title)")

    service.events().delete(calendarId="primary", eventId=event_id).execute()

    return f"Event '{title}' (ID: {event_id}) has been deleted."


@tool
def check_availability(start_time: str, end_time: str) -> str:
    """
    Check if a time slot is free or busy. Use this before creating an event
    to avoid double-booking. Also use when the user asks if they're free
    at a specific time.

    Args:
        start_time: Start of the window to check, ISO 8601 format e.g. '2026-05-15T10:00:00'
        end_time: End of the window to check, ISO 8601 format e.g. '2026-05-15T11:00:00'
    """
    service = get_service()
    tz = ZoneInfo(USER_TIMEZONE)

    body = {
        "timeMin": _to_rfc3339(start_time, tz),
        "timeMax": _to_rfc3339(end_time, tz),
        "timeZone": USER_TIMEZONE,
        "items": [{"id": "primary"}],
    }

    result = service.freebusy().query(body=body).execute()
    busy_slots = result["calendars"]["primary"]["busy"]

    if not busy_slots:
        return f"You're free between {start_time} and {end_time}."

    conflicts = []
    for slot in busy_slots:
        conflicts.append(f"  Busy: {slot['start']} → {slot['end']}")

    return "Conflicts found:\n" + "\n".join(conflicts)

@tool
def find_free_slots(
    date: str,
    duration_minutes: int = 60,
    num_slots: int = 3,
    search_hours_start: int = 9,
    search_hours_end: int = 18,
) -> str:
    """
    Find available free time slots on a given date. Use this when the user
    asks 'when am I free?', when check_availability finds a conflict and you
    need to suggest alternatives, or when the user asks to find a good time
    to meet.

    Args:
        date: The date to search on in YYYY-MM-DD format, e.g. '2026-05-20'
        duration_minutes: Length of the slot needed in minutes (default 60)
        num_slots: How many free slots to return (default 3)
        search_hours_start: Start of working hours to search (default 9 = 9am)
        search_hours_end: End of working hours to search (default 18 = 6pm)
    """
    service = get_service()
    tz = ZoneInfo(USER_TIMEZONE)

    day_start = datetime.fromisoformat(
        f"{date}T{search_hours_start:02d}:00:00"
    ).replace(tzinfo=tz)
    day_end = datetime.fromisoformat(
        f"{date}T{search_hours_end:02d}:00:00"
    ).replace(tzinfo=tz)

    body = {
        "timeMin": day_start.isoformat(),
        "timeMax": day_end.isoformat(),
        "timeZone": USER_TIMEZONE,
        "items": [{"id": "primary"}],
    }

    result    = service.freebusy().query(body=body).execute()
    busy      = result["calendars"]["primary"]["busy"]
    delta     = timedelta(minutes=duration_minutes)
    free_slots = []
    cursor    = day_start

    while cursor + delta <= day_end and len(free_slots) < num_slots:
        slot_end = cursor + delta

        # Check if this window overlaps any busy period
        conflict = any(
            datetime.fromisoformat(b["start"].replace("Z", "+00:00")) < slot_end
            and
            datetime.fromisoformat(b["end"].replace("Z", "+00:00")) > cursor
            for b in busy
        )

        if not conflict:
            free_slots.append(
                f"  {cursor.strftime('%I:%M %p')} – {slot_end.strftime('%I:%M %p')}"
            )
            cursor = slot_end       # jump past this slot
        else:
            cursor += timedelta(minutes=15)  # step forward and try again

    if not free_slots:
        return (
            f"No free {duration_minutes}-minute slots found on {date} "
            f"between {search_hours_start}am and {search_hours_end}pm."
        )

    return (
        f"Free {duration_minutes}-minute slots on {date}:\n"
        + "\n".join(free_slots)
    )


@tool
def create_recurring_event(
    title: str,
    start_time: str,
    end_time: str,
    recurrence: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    occurrences: Optional[int] = None,
) -> str:
    """
    Create a recurring calendar event. Use this when the user says things
    like 'every Monday', 'daily standup', 'weekly on Tuesdays', 'every
    weekday', or 'monthly'. Do not use create_event for recurring requests.

    Args:
        title: Title of the event
        start_time: First occurrence start time in ISO 8601 format
        end_time: First occurrence end time in ISO 8601 format
        recurrence: One of 'daily', 'weekly', 'monthly', or 'weekdays'
        description: Optional description or agenda
        location: Optional location or video call link
        occurrences: How many times to repeat. Omit for no end date.
    """
    service = get_service()
    tz = ZoneInfo(USER_TIMEZONE)

    rrule_map = {
        "daily":    "RRULE:FREQ=DAILY",
        "weekly":   "RRULE:FREQ=WEEKLY",
        "monthly":  "RRULE:FREQ=MONTHLY",
        "weekdays": "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    }

    if recurrence not in rrule_map:
        return (
            f"Unknown recurrence '{recurrence}'. "
            f"Use one of: daily, weekly, monthly, weekdays."
        )

    rrule = rrule_map[recurrence]
    if occurrences:
        rrule += f";COUNT={occurrences}"

    event_body = {
        "summary": title,
        "start": {"dateTime": _to_rfc3339(start_time, tz), "timeZone": USER_TIMEZONE},
        "end":   {"dateTime": _to_rfc3339(end_time, tz),   "timeZone": USER_TIMEZONE},
        "recurrence": [rrule],
    }

    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location

    created = service.events().insert(
        calendarId="primary",
        body=event_body,
    ).execute()

    recurrence_desc = {
        "daily":    "every day",
        "weekly":   "every week",
        "monthly":  "every month",
        "weekdays": "every weekday (Mon–Fri)",
    }[recurrence]

    count_str = f" for {occurrences} occurrences" if occurrences else " (no end date)"

    return (
        f"Recurring event created: '{created['summary']}'\n"
        f"  Repeats: {recurrence_desc}{count_str}\n"
        f"  First occurrence: {created['start']['dateTime']}\n"
        f"  ID: {created['id']}\n"
        f"  Link: {created.get('htmlLink', 'n/a')}"
    )