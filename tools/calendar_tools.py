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