#!/usr/bin/env python3
"""
Rebuilds docs/calendar.ics from every CSV file currently sitting in data/.

This script has no dependency on OneDrive or Microsoft Graph - the CSVs are
pushed into data/ by the apply_event.py step (driven by a Power Automate
flow watching the OneDrive folder). This script just does the CSV -> ICS
conversion, and is fully idempotent: rerunning it always rebuilds the same
output from whatever is currently in data/. That means:
  - A CSV removed from data/ (because it was deleted from OneDrive)
    -> its events disappear from the next build.
  - A CSV changed in data/ -> its events are rebuilt with the same UID,
    so the calendar app updates them in place instead of duplicating.
  - A CSV added to data/ -> its events appear in the next build.

Expected CSV columns (header row required):
    Task ID, Subject, Start Date, End Date, Start Time, End Time

Dates are expected as DD/MM/YY (Australian format). Times are 24h HH:MM.
All events are treated as being in the Australia/Brisbane timezone
(no daylight saving in Queensland, so this is a fixed UTC+10 offset).
"""

import csv
import io
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

DATA_DIR = os.environ.get("CSV_DATA_DIR", "data")
OUTPUT_PATH = os.environ.get("ICS_OUTPUT_PATH", "docs/calendar.ics")
CALENDAR_NAME = os.environ.get("ICS_CALENDAR_NAME", "Job Schedule")
UID_DOMAIN = os.environ.get("ICS_UID_DOMAIN", "job-calendar.local")

TZ = ZoneInfo("Australia/Brisbane")


# ---------------------------------------------------------------------------
# CSV -> events
# ---------------------------------------------------------------------------
def parse_date(date_str: str) -> tuple[int, int, int]:
    d, m, y = date_str.strip().split("/")
    year = int(y)
    if year < 100:
        year += 2000
    return year, int(m), int(d)


def parse_datetime(date_str: str, time_str: str) -> datetime:
    year, month, day = parse_date(date_str)
    hour, minute = [int(p) for p in time_str.strip().split(":")]
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


def build_events_from_csv(job_name: str, csv_text: str) -> list[Event]:
    events = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}

        task_id = row.get("Task ID")
        subject = row.get("Subject")
        if not task_id or not subject:
            continue

        try:
            dtstart = parse_datetime(row["Start Date"], row["Start Time"])
            dtend = parse_datetime(row["End Date"], row["End Time"])
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Skipping row {task_id} in {job_name}: {exc}", file=sys.stderr)
            continue

        event = Event()
        event.add("uid", f"{task_id}@{UID_DOMAIN}")
        event.add("summary", subject)
        event.add("dtstart", dtstart)
        event.add("dtend", dtend)
        event.add("dtstamp", datetime.now(tz=ZoneInfo("UTC")))
        event.add("categories", [job_name])
        event.add("description", f"Job: {job_name}\nTask ID: {task_id}")
        events.append(event)

    return events


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_files = sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv"))
    print(f"Found {len(csv_files)} CSV file(s) in {DATA_DIR}/.")

    cal = Calendar()
    cal.add("prodid", "-//Job Calendar Sync//github-actions//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", CALENDAR_NAME)
    cal.add("x-wr-timezone", "Australia/Brisbane")

    total_events = 0
    for fname in csv_files:
        job_name = os.path.splitext(fname)[0]
        try:
            with open(os.path.join(DATA_DIR, fname), "r", encoding="utf-8-sig") as f:
                csv_text = f.read()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! Failed to read {fname}: {exc}", file=sys.stderr)
            continue

        events = build_events_from_csv(job_name, csv_text)
        print(f"  - {fname}: {len(events)} event(s)")
        total_events += len(events)
        for ev in events:
            cal.add_component(ev)

    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        f.write(cal.to_ical())

    print(f"Wrote {total_events} total event(s) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
