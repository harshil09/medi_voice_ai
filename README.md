# Medical Care Hospital Voice Assistant Backend

A production-style FastAPI backend for a hospital call assistant built with [Vapi](https://vapi.ai). The service provides real doctor data, dynamic appointment slots, booking and cancellation workflows, insurance checks, and emergency routing through a single webhook-backed tool layer.

## Overview

This project is designed for a voice agent such as Sarah to:

- route callers to the right specialty
- offer only real doctors returned by backend tools
- generate appointment times from doctor availability windows
- book and cancel appointments against a local SQLite database
- verify insurance providers or list accepted plans
- handle emergency calls separately from routine scheduling

## Key Features

- **Specialty-based doctor lookup** for `general`, `cardiologist`, and `orthopedic`
- **Emergency routing** for urgent callers using a dedicated emergency flow
- **Dynamic slot generation** from availability windows, patient capacity, and a fixed **10-minute buffer** between slot start times
- **Appointment booking** with caller name and phone number
- **Appointment cancellation** with flexible matching by patient, date, time, and optional doctor
- **Insurance support** for both provider lookup and accepted-plan listing
- **Vapi webhook integration** with tool-name aliases and input normalization

## Tech Stack

- Python 3.11+
- [FastAPI](https://fastapi.tiangolo.com/)
- Uvicorn
- SQLite
- ngrok (for exposing the local webhook to Vapi)

## How It Works

The assistant never invents operational data. Instead, it calls backend tools that read from `hospital.db`.

Typical routine booking flow:

1. Caller describes their issue.
2. Assistant calls `get_doctors_by_specialty`.
3. Caller chooses a doctor.
4. Assistant calls `get_available_slots`.
5. Caller selects a returned time.
6. Assistant collects caller details.
7. Assistant calls `book_appointment`.
8. Assistant confirms the booking and closes the call.

Emergency callers are handled separately through `get_emergency_doctors` and are not sent through the routine booking flow unless they explicitly ask for a scheduled visit.

## Project Structure

```text
main.py                  FastAPI application entry point
database.py              SQLite schema creation and lightweight migrations
names.py                 Seed script for doctors, availability, and insurance data
sarah.txt                Voice assistant prompt used in Vapi
services/
  hospital.py            Business logic for doctors, slots, bookings, cancellations, insurance
  scheduling.py          Dynamic slot generation and slot validation
routers/
  doctor.py              REST endpoints for doctor lookup
  insurance.py           REST endpoint for accepted insurance
  vapi_webhook.py        Vapi tool-call webhook handler
start-ngrok.sh           Optional helper for starting ngrok
requirements.txt         Python dependencies
hospital.db              Local SQLite database created after seeding
```

## Getting Started

### 1. Clone and install dependencies

```bash
git clone <your-repo-url>
cd VAPI_MED
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the environment with:

```bash
venv\Scripts\activate
```

### 2. Seed the database

```bash
python3 names.py
```

This creates `hospital.db` with:

- sample doctors
- availability windows
- emergency coverage
- insurance providers

To reseed from scratch:

```bash
rm -f hospital.db
python3 names.py
```

### 3. Run the API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Available local endpoints:

| Endpoint | Description |
|----------|-------------|
| `http://localhost:8000/` | API index |
| `http://localhost:8000/health` | Health check |
| `http://localhost:8000/doctors/specialty/general` | Doctors by specialty |
| `http://localhost:8000/doctors/emergency` | Emergency doctors |
| `http://localhost:8000/insurance/accepted` | Accepted insurance list |
| `http://localhost:8000/vapi/webhook` | Vapi tool-calls webhook |

Interactive API docs are available at `http://localhost:8000/docs`.

### 4. Expose the webhook to Vapi

Vapi must reach your app over HTTPS.

Start ngrok in a separate terminal:

```bash
ngrok http 8000
```

Or use the included helper:

```bash
chmod +x start-ngrok.sh
./start-ngrok.sh
```

Use the resulting HTTPS URL as the server URL for every Vapi function tool:

```text
https://<your-ngrok-host>/vapi/webhook
```

## Slot Generation

Appointment times are generated dynamically from the `doctor_availability` table.

Each availability window uses:

- `start_time`
- `end_time`
- `max_patients`
- optional `slot_duration_minutes`

If `slot_duration_minutes` is not set, slot duration is calculated as:

```text
(end_time - start_time) / max_patients
```

The system then adds a fixed **10-minute buffer** between consecutive slot start times.

Examples from the seeded data:

- **Dr. Patel**: `12:00-13:00`, 4 patients  
  Calculated visit length = 15 minutes  
  Offered times = `12:00`, `12:25`

- **Dr. Mehta**: `09:00-11:00`, 4 patients  
  Calculated visit length = 30 minutes  
  Offered times = `09:00`, `09:40`, `10:20`

To change the global gap later, update `SLOT_BUFFER_MINUTES` in `services/scheduling.py`.

## Vapi Configuration

### Create function tools

In the Vapi dashboard, create one function tool for each backend action below. Every tool should point to the same webhook URL.

| Tool name | Parameters | Purpose |
|-----------|------------|---------|
| `get_doctors_by_specialty` | `specialty` | Get routine doctors by specialty |
| `get_emergency_doctors` | none | Get the doctor on emergency duty |
| `get_available_slots` | `doctor_name`, optional `limit` | Return offered appointment slots |
| `book_appointment` | `doctor_name`, `patient_name`, `phone`, `slot_date`, `slot_time` | Book an appointment |
| `cancel_appointment` | `patient_name`, `slot_date`, optional `slot_time`, optional `doctor_name` | Cancel an appointment |
| `list_accepted_insurance` | none | List accepted insurance providers |
| `check_insurance` | `provider_name` | Check one provider |

Important notes:

- Use **snake_case** function names exactly as shown.
- Set **maxTokens** to **500** for each tool to avoid truncated responses.
- If your ngrok URL changes, update the server URL on every Vapi tool.

### Assistant prompt

This repository includes a ready-to-edit prompt file:

```text
sarah.txt
```

That prompt enforces:

- tool-first doctor and slot handling
- one-question-at-a-time booking flow
- emergency routing rules
- insurance verification rules
- call-closing instructions

### End-call behavior

If you want the assistant to actually hang up after goodbye, enabling prompt instructions alone is not enough. In Vapi, also enable the built-in end-call capability for the assistant.

Recommended checks in Vapi:

1. Attach all backend tools to the assistant.
2. Enable the built-in **endCall** capability on the assistant.
3. Review idle or silence prompts such as "Are you still there?" so they do not fire after a completed closing.

## Example Booking Flow

1. Caller: "I need a general checkup."
2. Assistant calls `get_doctors_by_specialty("general")`.
3. Backend returns `Dr. Patel` and `Dr. Smith`.
4. Caller chooses `Dr. Patel`.
5. Assistant calls `get_available_slots("Dr. Patel", limit=3)`.
6. Backend returns times such as `2026-05-26 at 12:00` and `2026-05-26 at 12:25`.
7. Caller picks a slot.
8. Assistant collects name and phone.
9. Assistant calls `book_appointment(...)`.
10. Assistant confirms the booking using the tool result.

## Seed Data

Current seeded doctors include:

- **Dr. Shah** - cardiologist, emergency doctor
- **Dr. Mehta** - cardiologist
- **Dr. Patel** - general
- **Dr. Smith** - general
- **Dr. Kapoor** - orthopedic

Seed data is defined in `names.py`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Tool is not firing | Confirm the assistant has the tool attached and the prompt tells it when to use the tool. |
| ngrok URL changed | Update the server URL for every Vapi tool. |
| No slots returned | Check doctor availability data, booked appointments, and whether the database needs reseeding. |
| Slots look different than before | The scheduler now applies a fixed 10-minute buffer between slot start times. |
| The assistant says goodbye but does not hang up | Enable Vapi's built-in `endCall` capability and review idle/silence prompts. |
| The assistant repeats the greeting | Update the Vapi prompt with the rules in `sarah.txt` and make sure the greeting is only defined once. |
| Insurance list is missing | Use `list_accepted_insurance`; `check_insurance` only verifies one provider. |
| Wrong specialty gets passed | Use only `general`, `cardiologist`, or `orthopedic`. |

For debugging, watch the API logs for lines like:

```text
tool=get_doctors_by_specialty args=... result=...
```
