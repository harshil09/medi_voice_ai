"""Database helpers for REST API and VAPI tools."""
import re

from database import get_connection
from services import scheduling

# Maps caller / LLM text → DB specialty column
STT_PHRASES = {
    "at pain": "orthopedic",
    "joint pain": "orthopedic",
    "back pain": "orthopedic",
    "chest pain": "cardiologist",
    "heart pain": "cardiologist",
}

EMERGENCY_MARKERS = (
    "emergency",
    "bleeding",
    "blood",
    "accident",
    "severe injury",
    "trauma",
    "urgent care",
    "walk-in emergency",
    "emergency doctor on duty",
    "life-threatening emergency",
)

SPECIALTY_ALIASES = {
    "cardiology": "cardiologist",
    "cardiologist": "cardiologist",
    "cardiac": "cardiologist",
    "heart": "cardiologist",
    "chest": "cardiologist",
    "general physician": "general",
    "general": "general",
    "gp": "general",
    "physician": "general",
    "orthopedics": "orthopedic",
    "orthopedic": "orthopedic",
    "ortho": "orthopedic",
    "joint": "orthopedic",
    "back": "orthopedic",
    "knee": "orthopedic",
    "fracture": "orthopedic",
    "bone": "orthopedic",
    "fever": "general",
    "cold": "general",
}


def _fetchall(sql: str, params=()) -> list[dict]:
    conn = get_connection()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def _fetchone(sql: str, params=()) -> dict | None:
    conn = get_connection()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row) if row else None


def _with_db(fn):
    """write logic with one connection."""
    conn = get_connection()
    try:
        return fn(conn)
    finally:
        conn.close()


def normalize_specialty(specialty: str) -> str:
    raw = specialty.strip().lower()
    raw = raw.replace("physicists", "physician").replace("physicist", "physician")

    if raw in STT_PHRASES:
        return STT_PHRASES[raw]
    for phrase, canon in STT_PHRASES.items():
        if phrase in raw:
            return canon

    key = " ".join(raw.replace("specialist", "").replace("specialty", "").split())
    if key in SPECIALTY_ALIASES:
        return SPECIALTY_ALIASES[key]

    for token, canon in SPECIALTY_ALIASES.items():
        if token in raw or token in key:
            return canon

    if "pain" in raw:
        return "cardiologist" if any(w in raw for w in ("chest", "heart", "cardio")) else "orthopedic"

    return key


def is_emergency_request(text: str) -> bool:
    raw = text.strip().lower()
    if not raw:
        return False
    if raw in ("emergency", "er", "urgent"):
        return True
    return any(marker in raw for marker in EMERGENCY_MARKERS)


def get_doctors_by_specialty(specialty: str) -> list[dict]:
    spec = normalize_specialty(specialty)
    return _fetchall(
        """
        SELECT id, name, specialty, emergency FROM doctors
        WHERE LOWER(specialty) = LOWER(?) AND available = 1 AND emergency = 0
        """,
        (spec,),
    )


def get_emergency_doctors() -> list[dict]:
    return _fetchall(
        "SELECT id, name, specialty FROM doctors WHERE emergency = 1 AND available = 1"
    )


def _doctor_key(name: str) -> str:
    n = name.strip().lower()
    for prefix in ("doctor ", "dr. ", "dr "):
        if n.startswith(prefix):
            return n[len(prefix) :].strip()
    return n


def get_doctor_by_name(doctor_name: str) -> dict | None:
    raw = doctor_name.strip()
    if not raw:
        return None

    exact = _fetchone(
        "SELECT id, name, specialty FROM doctors WHERE LOWER(name) = LOWER(?)",
        (raw,),
    )
    if exact:
        return exact

    query = _doctor_key(raw)
    for doc in _fetchall("SELECT id, name, specialty FROM doctors WHERE available = 1"):
        norm = _doctor_key(doc["name"])
        surname = norm.split()[-1] if norm else ""
        if query in (norm, surname) or norm.endswith(query) or query in surname:
            return doc
    return None


def get_available_slots(doctor_name: str, limit: int = 3) -> list[dict]:
    doctor = get_doctor_by_name(doctor_name)
    if not doctor:
        return []
    return scheduling.get_available_slots(doctor["id"], limit=limit)


def book_appointment(
    doctor_name: str,
    patient_name: str,
    phone: str,
    slot_date: str,
    slot_time: str,
) -> dict:
    doctor = get_doctor_by_name(doctor_name)
    if not doctor:
        return {"success": False, "message": f"Doctor not found: {doctor_name}"}

    slot_time_norm = scheduling.normalize_time(slot_time)
    if not slot_time_norm:
        return {"success": False, "message": "Invalid time format. Use HH:MM (e.g. 09:00)."}

    if not scheduling.is_slot_available(doctor["id"], slot_date, slot_time_norm):
        return {"success": False, "message": "That slot is not available. Ask for other times."}

    def work(conn):
        cur = conn.cursor()
        scheduled_at = f"{slot_date} {slot_time_norm}"
        pname = patient_name.strip()

        cur.execute("SELECT id FROM patients WHERE LOWER(full_name) = LOWER(?)", (pname,))
        patient = cur.fetchone()
        if patient:
            patient_id = patient["id"]
            cur.execute("UPDATE patients SET phone = ? WHERE id = ?", (phone, patient_id))
        else:
            cur.execute("INSERT INTO patients (full_name, phone) VALUES (?, ?)", (pname, phone))
            patient_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO appointments (patient_id, doctor_id, slot_id, scheduled_at, status)
            VALUES (?, ?, NULL, ?, 'confirmed')
            """,
            (patient_id, doctor["id"], scheduled_at),
        )
        conn.commit()
        return {
            "success": True,
            "message": f"Booked: {patient_name} with {doctor['name']} on {slot_date} at {slot_time_norm}.",
        }

    return _with_db(work)


def _patient_patterns(name: str) -> list[str]:
    n = name.strip().lower()
    parts = n.split()
    patterns = {f"%{n}%"}
    if parts:
        patterns.add(f"%{parts[-1]}%")
        if len(parts[-1]) >= 3:
            patterns.add(f"%{parts[-1][:4]}%")
    return list(patterns)


def _normalize_time(slot_time: str | None) -> str | None:
    return scheduling.normalize_time(slot_time)


def _date_patterns(slot_date: str) -> list[str]:
    d = slot_date.strip()
    patterns = [f"{d}%"]
    m = re.search(r"\d{4}-(\d{2})-(\d{2})", d)
    if m:
        patterns.append(f"%-{m.group(1)}-{m.group(2)}%")
    return patterns


def _find_appointments(patient_name: str, slot_date: str, slot_time=None, doctor_id=None) -> list[dict]:
    time_str = _normalize_time(slot_time)
    found, seen = [], set()

    conn = get_connection()
    for np in _patient_patterns(patient_name):
        for dp in _date_patterns(slot_date):
            sql = """
                SELECT a.id, a.slot_id, a.scheduled_at, d.name AS doctor_name
                FROM appointments a
                JOIN patients p ON p.id = a.patient_id
                JOIN doctors d ON d.id = a.doctor_id
                WHERE a.status = 'confirmed'
                AND LOWER(p.full_name) LIKE LOWER(?)
                AND a.scheduled_at LIKE ?
            """
            params = [np, dp]
            if doctor_id is not None:
                sql += " AND a.doctor_id = ?"
                params.append(doctor_id)
            if time_str:
                sql += " AND a.scheduled_at LIKE ?"
                params.append(f"%{time_str}%")
            for row in conn.execute(sql, params):
                item = dict(row)
                if item["id"] not in seen:
                    seen.add(item["id"])
                    found.append(item)
    conn.close()
    return found


def cancel_appointment(
    patient_name: str,
    slot_date: str,
    slot_time: str | None = None,
    doctor_name: str | None = None,
) -> dict:
    if not patient_name.strip() or not slot_date.strip():
        return {"success": False, "message": "Need patient full name and appointment date to cancel."}

    doctor_id = None
    if doctor_name and doctor_name.strip():
        doctor = get_doctor_by_name(doctor_name)
        if not doctor:
            return {"success": False, "message": f"Doctor not found: {doctor_name}"}
        doctor_id = doctor["id"]

    matches = _find_appointments(patient_name, slot_date, slot_time, doctor_id)
    if not matches:
        return {
            "success": False,
            "message": f"No appointment found for {patient_name} on {slot_date}. Use date YYYY-MM-DD.",
        }
    if len(matches) > 1:
        opts = "; ".join(f"{m['doctor_name']} on {m['scheduled_at']}" for m in matches)
        return {
            "success": False,
            "message": f"Multiple appointments found: {opts}. Ask which doctor and call again with doctor_name.",
        }

    appt = matches[0]

    def work(conn):
        conn.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appt["id"],))
        if appt.get("slot_id"):
            conn.execute("UPDATE doctor_slots SET is_booked = 0 WHERE id = ?", (appt["slot_id"],))
        conn.commit()
        return {
            "success": True,
            "message": f"Cancelled appointment for {patient_name} with {appt['doctor_name']} on {appt['scheduled_at']}.",
        }

    return _with_db(work)


def list_accepted_insurance() -> dict:
    rows = _fetchall(
        "SELECT name FROM insurance_providers WHERE accepted = 1 ORDER BY name"
    )
    names = [r["name"] for r in rows]
    if not names:
        return {
            "providers": [],
            "message": "No accepted insurance providers on file. Offer to transfer to billing.",
        }
    joined = ", ".join(names)
    return {
        "providers": names,
        "message": (
            f"We accept the following insurance providers: {joined}. "
            "If the caller's provider is not listed, offer to check a specific name with check_insurance "
            "or connect them with billing."
        ),
    }


def check_insurance(provider_name: str) -> dict:
    name = provider_name.strip()
    if not name:
        return {"accepted": False, "message": "Ask the caller for their insurance provider name."}
    row = _fetchone(
        "SELECT name, accepted FROM insurance_providers WHERE LOWER(name) LIKE LOWER(?) LIMIT 1",
        (f"%{name}%",),
    )
    if not row:
        return {
            "accepted": False,
            "message": (
                f"We could not find {provider_name} in our list. "
                "Tell the caller their plan may not be in-network. "
                "If they ask what you do accept, call list_accepted_insurance. "
                "Otherwise offer billing."
            ),
        }
    if row["accepted"]:
        return {
            "accepted": True,
            "message": f"Yes, we accept {row['name']}. Bring your insurance card and photo ID to your visit.",
        }
    return {
        "accepted": False,
        "message": f"We may not be in-network for {row['name']}. Transfer to billing for details.",
    }
