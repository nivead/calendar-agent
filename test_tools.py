from tools.calendar_tools import (
    list_events,
    create_event,
    update_event,
    delete_event,
    check_availability,
)

def test_list():
    print("=== list_events ===")
    result = list_events.invoke({"days_ahead": 7})
    print(result)

def test_availability():
    print("\n=== check_availability ===")
    result = check_availability.invoke({
        "start_time": "2026-05-12T10:00:00",
        "end_time": "2026-05-12T11:00:00",
    })
    print(result)

def test_create():
    print("\n=== create_event ===")
    result = create_event.invoke({
        "title": "Test Meeting (delete me)",
        "start_time": "2026-05-12T14:00:00",
        "end_time": "2026-05-12T14:30:00",
        "description": "Created by the calendar agent test",
    })
    print(result)
    return result  # contains the event ID

def test_update(event_id: str):
    print("\n=== update_event ===")
    result = update_event.invoke({
        "event_id": event_id,
        "title": "Test Meeting (updated title)",
    })
    print(result)

def test_delete(event_id: str):
    print("\n=== delete_event ===")
    result = delete_event.invoke({"event_id": event_id})
    print(result)


if __name__ == "__main__":
    test_list()
    test_availability()

    create_result = test_create()

    # Pull the event ID out of the create result
    # Result format: "Event created: '...'\n  ID: <id>\n ..."
    event_id = None
    for line in create_result.split("\n"):
        if "ID:" in line:
            event_id = line.split("ID:")[-1].strip()
            break

    if event_id:
        test_update(event_id)
        test_delete(event_id)
    else:
        print("Could not extract event ID to test update/delete")