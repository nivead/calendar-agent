import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from googleapiclient.discovery import build
from auth import get_credentials

load_dotenv()


def test_list_events():
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc).isoformat()

    print("Fetching your next 5 upcoming events...\n")
    result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=5,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])

    if not events:
        print("No upcoming events found. Your calendar is clear!")
        return

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(f"  {start}  →  {event['summary']}")

    print(f"\nSuccess! Found {len(events)} event(s).")


if __name__ == "__main__":
    test_list_events()
