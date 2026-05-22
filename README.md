# VAPI Medical Hospital Assistant

A **FastAPI** backend that connects a [VAPI](https://vapi.ai) voice assistant to a **SQLite** hospital database. The assistant uses real doctor names, computed appointment slots, bookings, cancellations, and insurance data instead of inventing answers.

## Features

- **Doctor lookup** by specialty (`general`, `cardiologist`, `orthopedic`)
- **Emergency routing** — on-call doctors (e.g. Dr. Shah) without booking flow
- **Dynamic slots** — times derived from availability windows and patient capacity
- **Book & cancel** appointments with patient name and phone
- **Insurance** — list accepted providers or verify a single plan
- **VAPI webhook** — single endpoint handles all tool calls with name aliases and specialty normalization

## Tech stack

- Python 3.11+
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn
- SQLite (`hospital.db`)

## Quick start

### 1. Clone and install

```bash
git clone <your-repo-url>
cd VAPI_MED
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Seed the database

```bash
python names.py
```

Creates `hospital.db` with sample doctors, availability windows, and insurance providers. To re-seed, delete `hospital.db` and run `python names.py` again.

### 3. Run the API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

| Endpoint | Description |
|----------|-------------|
| http://localhost:8000/ | API index |
| http://localhost:8000/health | Health check |
| http://localhost:8000/doctors/specialty/general | Doctors by specialty (REST) |
| http://localhost:8000/doctors/emergency | Emergency on-call doctors |
| http://localhost:8000/insurance/accepted | Accepted insurance list |
| http://localhost:8000/vapi/webhook | VAPI tool-calls (POST) |

Interactive docs: http://localhost:8000/docs

### 4. Expose for VAPI (ngrok)

VAPI must reach your server over HTTPS. In a second terminal:

```bash
ngrok http 8000
```

Or use the included helper (requires ngrok in `bin/` or on `PATH`):

```bash
chmod +x start-ngrok.sh
./start-ngrok.sh
```

Set each VAPI tool **Server URL** to:

```text
https://<your-ngrok-host>/vapi/webhook
```

## VAPI setup

### Create tools

In the VAPI dashboard: **Tools → Create Tool → Function**. Use the **Server URL** above for every tool. Function names must use **snake_case** (e.g. `get_doctors_by_specialty`, not the display title).

| Tool name | Parameters | When to use |
|-----------|------------|-------------|
| `get_doctors_by_specialty` | `specialty` (string) | Routine visits: general / cardiologist / orthopedic |
| `get_emergency_doctors` | (none) | Heart pain, bleeding, accident, or caller says emergency |
| `get_available_slots` | `doctor_name`, `limit` (optional, default 3) | Before offering appointment times |
| `book_appointment` | `doctor_name`, `patient_name`, `phone`, `slot_date`, `slot_time` | After caller picks a slot |
| `cancel_appointment` | `patient_name`, `slot_date`, `slot_time` (optional), `doctor_name` (optional) | Cancellation flow |
| `list_accepted_insurance` | (none) | Caller asks which insurance you accept |
| `check_insurance` | `provider_name` (string) | Verify one specific insurer |

Example schema for `get_doctors_by_specialty`:

```json
{
  "type": "object",
  "properties": {
    "specialty": {
      "type": "string",
      "description": "One of: cardiologist, general, orthopedic"
    }
  },
  "required": ["specialty"]
}
```

Attach all tools to your assistant. Set **maxTokens** to **500** on each tool (default 100 can truncate responses).

### Assistant prompt rules

- Never invent doctor names or appointment times — always call tools first.
- **Routine:** `get_doctors_by_specialty` → `get_available_slots` → collect name/phone → `book_appointment`.
- **Emergency:** `get_emergency_doctors` first; no booking for on-call emergency care.
- **Insurance list:** `list_accepted_insurance`. **Single provider:** `check_insurance`.

Seeded emergency doctor: **Dr. Shah** (`emergency = 1`, 24/7, no booking required).

### Optional tool messages

- **Request start:** e.g. "One moment please."
- **Request complete:** short acknowledgment or default

## Example call flow

1. Caller: "I need a general checkup."
2. Assistant → `get_doctors_by_specialty` → Dr. Patel, Dr. Smith.
3. Caller picks Dr. Patel.
4. Assistant → `get_available_slots` with `limit: 3` → e.g. `2026-05-26 at 12:00, 12:15, or 12:45`.
5. Caller picks a time; assistant collects name and phone.
6. Assistant → `book_appointment` and confirms from the tool result.

## Project structure

```text
main.py                  # FastAPI app entry
database.py              # SQLite schema and migrations
names.py                 # Seed doctors, availability, insurance
services/
  hospital.py            # Business logic (doctors, slots, bookings, insurance)
  scheduling.py          # Slot computation from availability windows
routers/
  doctor.py              # REST endpoints for testing
  insurance.py           # REST insurance list
  vapi_webhook.py        # VAPI tool-calls handler
start-ngrok.sh           # Optional ngrok launcher
requirements.txt
hospital.db              # Created after seed (not committed — add to .gitignore)
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 404 on doctors | Use `general`, `cardiologist`, or `orthopedic` (see `names.py`). |
| ngrok URL changed | Update Server URL on every VAPI tool. |
| Tool not firing | Tools attached to assistant; prompt instructs tool use. |
| Empty slots | Slot booked or no availability for that date; re-seed if needed. |
| Tool succeeds but voice says error | Set tool **maxTokens** to 500; use snake_case function names. |
| Wrong specialty on first call | Server maps common phrases; second call should use canonical specialty. |
| Won't list all insurance | Add `list_accepted_insurance`; `check_insurance` only checks one name. |

Check server logs for lines like `tool=get_doctors_by_specialty args=... result=...`.
