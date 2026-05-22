"""Generate appointment slots from doctor_availability windows."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from database import get_connection

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def time_to_minutes(value: str) -> int:
    m = _TIME_RE.match(str(value).strip())
    if not m:
        raise ValueError(f"Invalid time: {value!r}")
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"Invalid time: {value!r}")
    return hour * 60 + minute


def minutes_to_time(minutes: int) -> str:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize_time(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    t = str(value).strip().lower().replace(".", "")
    if _TIME_RE.fullmatch(t):
        return minutes_to_time(time_to_minutes(t))
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if not m:
        return t
    hour, minute, ampm = int(m.group(1)), m.group(2) or "00", m.group(3)
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute}"


def slot_duration_minutes(
    start_time: str,
    end_time: str,
    max_patients: int,
    override: int | None = None,
) -> int:
    if override and override > 0:
        return override
    window = time_to_minutes(end_time) - time_to_minutes(start_time)
    if window <= 0:
        return 0
    patients = max(1, int(max_patients or 1))
    return max(1, window // patients)


def generate_times_in_window(
    start_time: str,
    end_time: str,
    max_patients: int,
    slot_duration_override: int | None = None,
) -> list[str]:
    start_m = time_to_minutes(start_time)
    end_m = time_to_minutes(end_time)
    step = slot_duration_minutes(
        start_time, end_time, max_patients, slot_duration_override
    )
    if step <= 0 or start_m >= end_m:
        return []
    times: list[str] = []
    t = start_m
    while t + step <= end_m:
        times.append(minutes_to_time(t))
        t += step
    return times


def _parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _availability_windows(conn, doctor_id: int, slot_date: str) -> list[dict]:
    d = _parse_date(slot_date)
    weekday = d.weekday()  # Mon=0
    rows = conn.execute(
        """
        SELECT start_time, end_time, max_patients, slot_duration_minutes
        FROM doctor_availability
        WHERE doctor_id = ?
          AND (
            avail_date = ?
            OR (avail_date IS NULL AND day_of_week = ?)
          )
        ORDER BY start_time
        """,
        (doctor_id, slot_date, weekday),
    ).fetchall()
    return [dict(r) for r in rows]


def _booked_times(conn, doctor_id: int, slot_date: str) -> set[str]:
    booked: set[str] = set()
    prefix = f"{slot_date}%"
    for row in conn.execute(
        """
        SELECT scheduled_at FROM appointments
        WHERE doctor_id = ? AND status = 'confirmed' AND scheduled_at LIKE ?
        """,
        (doctor_id, prefix),
    ):
        raw = row["scheduled_at"]
        if not raw:
            continue
        parts = str(raw).split()
        if len(parts) >= 2:
            norm = normalize_time(parts[-1])
            if norm:
                booked.add(norm)
    return booked


def slots_for_date(conn, doctor_id: int, slot_date: str) -> list[str]:
    windows = _availability_windows(conn, doctor_id, slot_date)
    if not windows:
        return []
    booked = _booked_times(conn, doctor_id, slot_date)
    seen: set[str] = set()
    available: list[str] = []
    for w in windows:
        for t in generate_times_in_window(
            w["start_time"],
            w["end_time"],
            w["max_patients"],
            w.get("slot_duration_minutes"),
        ):
            if t not in booked and t not in seen:
                seen.add(t)
                available.append(t)
    available.sort(key=time_to_minutes)
    return available


def is_slot_available(doctor_id: int, slot_date: str, slot_time: str) -> bool:
    norm = normalize_time(slot_time)
    if not norm:
        return False
    conn = get_connection()
    try:
        return norm in slots_for_date(conn, doctor_id, slot_date)
    finally:
        conn.close()


def _dates_to_scan(conn, doctor_id: int, horizon_days: int) -> list[date]:
    today = date.today()
    specific = [
        _parse_date(r[0])
        for r in conn.execute(
            """
            SELECT DISTINCT avail_date FROM doctor_availability
            WHERE doctor_id = ? AND avail_date IS NOT NULL
            ORDER BY avail_date
            """,
            (doctor_id,),
        ).fetchall()
    ]
    has_weekly = conn.execute(
        """
        SELECT 1 FROM doctor_availability
        WHERE doctor_id = ? AND day_of_week IS NOT NULL
        LIMIT 1
        """,
        (doctor_id,),
    ).fetchone()
    scan: set[date] = set(specific)
    if has_weekly or not specific:
        scan.update(today + timedelta(days=i) for i in range(horizon_days))
    return sorted(d for d in scan if d >= today)


def get_available_slots(
    doctor_id: int,
    limit: int = 3,
    horizon_days: int = 60,
) -> list[dict]:
    conn = get_connection()
    try:
        scan_dates = _dates_to_scan(conn, doctor_id, horizon_days)

        found: list[dict] = []
        for d in scan_dates:
            ds = d.isoformat()
            for t in slots_for_date(conn, doctor_id, ds):
                found.append({"date": ds, "time": t})
                if len(found) >= limit:
                    return found
        return found
    finally:
        conn.close()
