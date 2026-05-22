# VAPI + FastAPI + SQLite (Medical Hospital)

Basic setup so your VAPI voice assistant reads **real** doctor names, slots, and bookings from your database instead of inventing them.

## 1. Install and seed

```bash
cd /home/dell/VAPI_MED
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python names.py
```

## 2. Run FastAPI

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Test: http://localhost:8000/health  
Doctors: http://localhost:8000/doctors/specialty/general

## 3. Expose with ngrok

In another terminal:

```bash
ngrok http 8000
```

Copy the HTTPS URL, e.g. `https://abc123.ngrok-free.app`

Your VAPI tool server URL will be:

`https://abc123.ngrok-free.app/vapi/webhook`

## 4. Create tools in VAPI Dashboard

For each tool: **Tools → Create Tool → Function**  
Set **Server URL** to your ngrok URL + `/vapi/webhook`

| Tool name | Parameters (JSON schema) | When assistant uses it |
|-----------|--------------------------|-------------------------|
| `get_doctors_by_specialty` | `specialty` (string) | cardiologist / general / orthopedic |
| `get_emergency_doctors` | (none) | heart pain, bleeding, accident, or caller says emergency |
| `get_available_slots` | `doctor_name` (string), `limit` (number, optional, default 3) | before offering times |
| `book_appointment` | `doctor_name`, `patient_name`, `phone`, `slot_date`, `slot_time` | after caller picks a slot |
| `cancel_appointment` | `doctor_name`, `patient_name`, `slot_date`, `slot_time` (optional) | cancellation flow |
| `list_accepted_insurance` | (none) | caller asks which insurance you accept / wants a list |
| `check_insurance` | `provider_name` (string) | verify one specific insurance name |

Example parameter schema for `get_doctors_by_specialty`:

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

Add all tools to your assistant under **Tools**.

For `get_emergency_doctors`, use the schema in `vapi_tool_get_emergency_doctors.json` and a **description** that says to use it for emergency / heart pain / bleeding — not `get_doctors_by_specialty`. Attach it to the same assistant as the other tools.

For `list_accepted_insurance`, use `vapi_tool_list_accepted_insurance.json` (empty parameters). **Description:** use when the caller asks which insurance providers are accepted or wants a list — not for checking one name (use `check_insurance`).

Test accepted list: http://localhost:8000/insurance/accepted

## 5. Update assistant system prompt

Update your VAPI assistant system prompt with the insurance section in **`VAPI_INSURANCE_PROMPT_SNIPPET.txt`** (or your full prompt file).

Key rules:

- Never invent doctor names or appointment times.
- Routine booking: `get_doctors_by_specialty` → `get_available_slots` → name/phone → `book_appointment`.
- Emergency (heart pain, bleeding, accident): `get_emergency_doctors` first — e.g. **Dr. Shah** is on duty 24/7; no booking needed.
- Insurance list question → `list_accepted_insurance`. One provider check → `check_insurance`.

Doctors table includes `emergency` (1 = on-call emergency, 0 = routine only). Dr. Shah is seeded as emergency.

## 6. Tool messages (optional)

In each tool’s dashboard settings:

- **Request start:** "One moment please."
- **Request complete:** (leave default or short ack)

## Flow example

1. Caller: "I need a general checkup"  
2. Assistant calls `get_doctors_by_specialty` → `Dr. Patel, Dr. Smith`  
3. Caller picks Dr. Patel  
4. Assistant calls `get_available_slots` with `limit: 3` → e.g. `2026-05-26 at 12:00, 12:15, or 12:45` for Dr. Patel (slots computed from schedule window and patient capacity)  
5. Caller picks 09:00  
6. Assistant asks name + phone, then calls `book_appointment`  
7. Assistant confirms using the tool result text

## Project layout

```
main.py              # FastAPI app
database.py          # SQLite schema (doctor_availability + appointments)
names.py             # seed doctors + availability windows
services/hospital.py # business logic (shared by webhook)
routers/doctor.py    # REST for testing
routers/vapi_webhook.py  # VAPI tool-calls handler
hospital.db          # created after seed
```

## Troubleshooting

- **404 on doctors:** use `general`, `cardiologist`, or `orthopedic` (see `names.py`).
- **ngrok URL changed:** update every tool’s Server URL in VAPI.
- **Tool not firing:** ensure tools are attached to the assistant and prompt says to use them.
- **Empty slots:** slot may be booked or the doctor has no `doctor_availability` for that date. Delete `hospital.db` and run `python names.py` to re-seed.
- **Tool “succeeds” but Sarah says error:** In VAPI dashboard for each tool set **maxTokens** to **500** (default 100 truncates the response). Function name must be `get_doctors_by_specialty` (snake_case), not the display title “Get Doctors By Specialty”. Check uvicorn logs for `tool_call raw_name=... result=...`.
- **Tool called twice:** First call may use wrong `specialty` (e.g. `joint pain`); server maps it now. Second call should use `orthopedic`.
- **Sarah won't list insurance:** Add tool `list_accepted_insurance` in VAPI and update the prompt per `VAPI_INSURANCE_PROMPT_SNIPPET.txt`. Sarah only knows what tools return — `check_insurance` alone cannot list all providers.
