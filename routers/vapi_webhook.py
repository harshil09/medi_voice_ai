"""VAPI tool-calls webhook — POST https://<ngrok-host>/vapi/webhook"""
import json
import logging
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services import hospital

logger = logging.getLogger("vapi.webhook")
router = APIRouter(prefix="/vapi", tags=["vapi"])

TOOL_ALIASES = {
    "get doctors by specialty": "get_doctors_by_specialty",
    "get emergency doctors": "get_emergency_doctors",
    "get available slots": "get_available_slots",
    "book appointment": "book_appointment",
    "cancel appointment": "cancel_appointment",
    "check insurance": "check_insurance",
}

SPECIALTY_INTROS = {
    "general": "For general health concerns, we have",
    "cardiologist": "For cardiology, we have",
    "orthopedic": "For orthopedics, we have",
}

EMERGENCY_FLOW_MARKERS = (
    "emergency doctor on duty",
    "life-threatening emergency",
    "nearest emergency room",
    "call emergency services",
)


def _tool_name(name: str) -> str:
    key = (name or "").strip().lower()
    return TOOL_ALIASES.get(key, re.sub(r"[^a-z0-9_]+", "_", key).strip("_"))


def _parse_json_object(raw) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _parse_args(raw) -> dict:
    parsed = _parse_json_object(raw)
    return parsed if parsed is not None else {}


def _normalize_message(body) -> dict | None:
    """VAPI wraps events in {message: {...}}; message may be a JSON string."""
    if isinstance(body, str):
        body = _parse_json_object(body) or {}
    if not isinstance(body, dict):
        return None

    message = body.get("message", body)
    if isinstance(message, str):
        message = _parse_json_object(message)
    if not isinstance(message, dict):
        return None
    if "type" not in message and isinstance(body.get("type"), str):
        return body
    return message


def _tool_call_items(message: dict) -> list:
    items = message.get("toolCallList") or []
    if items:
        return items
    for entry in message.get("toolWithToolCallList") or []:
        if not isinstance(entry, dict):
            continue
        tc = entry.get("toolCall")
        if isinstance(tc, dict):
            if "name" not in tc and entry.get("name"):
                tc = {**tc, "name": entry["name"]}
            items.append(tc)
        elif entry.get("name"):
            items.append(entry)
    fn = message.get("functionCall") or message.get("function")
    if not items and isinstance(fn, dict):
        items.append(fn)
    return items


def _extract_call(tc: dict) -> tuple[str, str, dict]:
    tid = tc.get("id") or tc.get("toolCallId") or ""
    fn = tc.get("function") or {}
    name = tc.get("name") or (fn.get("name") if isinstance(fn, dict) else "") or ""
    raw = (
        tc.get("arguments")
        or tc.get("parameters")
        or (fn.get("arguments") if isinstance(fn, dict) else None)
        or (fn.get("parameters") if isinstance(fn, dict) else None)
        or {}
    )
    return tid, _tool_name(name), _parse_args(raw)


def _doctor_reply(doctors: list[dict]) -> str:
    names = " and ".join(d["name"] for d in doctors)
    if len(doctors) == 1:
        return f"We have {names} available. Would you like to book an appointment with {names}?"
    intro = SPECIALTY_INTROS.get(doctors[0]["specialty"], "We have")
    return f"{intro} {names} available. Which doctor would you prefer?"


def _handle_get_emergency(_args: dict) -> str:
    doctors = hospital.get_emergency_doctors()
    if not doctors:
        return "No emergency doctor on duty. Transfer to a hospital representative."
    names = " and ".join(d["name"] for d in doctors)
    if len(doctors) == 1:
        return (
            f"SAY TO CALLER: We have {names} available for emergency care. "
            f"No appointment is needed — {names} is available twenty-four hours a day, seven days a week; you can come anytime. "
            "If they ask about booking, say no booking is required. "
            "DO NOT mention Dr. Patel, Dr. Smith, or any general physician. "
            "DO NOT call get_doctors_by_specialty, get_available_slots, or book_appointment for this emergency visit."
        )
    return (
        f"SAY TO CALLER: Emergency doctors on duty: {names}. "
        "No appointment needed — available around the clock. "
        "DO NOT offer routine booking or general physicians unless they want a separate scheduled visit."
    )


def _conversation_text(message: dict) -> str:
    parts: list[str] = []

    def add_messages(items) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            role = (item.get("role") or "").lower()
            if role not in ("user", "assistant", "bot"):
                continue
            for key in ("content", "message", "text", "transcript"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    parts.append(val)
                elif isinstance(val, list):
                    for block in val:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(str(block.get("text") or ""))

    add_messages(message.get("messages"))
    artifact = message.get("artifact") or {}
    if isinstance(artifact, dict):
        add_messages(artifact.get("messages"))
    call = message.get("call") or {}
    if isinstance(call, dict):
        call_artifact = call.get("artifact") or {}
        if isinstance(call_artifact, dict):
            add_messages(call_artifact.get("messages"))
    transcript = message.get("transcript")
    if isinstance(transcript, str):
        parts.append(transcript)
    return " ".join(parts).lower()


def _call_in_emergency_flow(message: dict | None) -> bool:
    if not message:
        return False
    text = _conversation_text(message)
    if not text:
        return False
    if any(marker in text for marker in EMERGENCY_FLOW_MARKERS):
        return True
    return hospital.is_emergency_request(text)


def _handle_get_doctors(args: dict, message: dict | None = None) -> str:
    specialty = args.get("specialty", "")
    if hospital.is_emergency_request(specialty) or _call_in_emergency_flow(message):
        logger.info("routing get_doctors_by_specialty(%r) to get_emergency_doctors", specialty)
        return _handle_get_emergency(args)
    doctors = hospital.get_doctors_by_specialty(specialty)
    if not doctors:
        return (
            f"No match for '{specialty}'. Retry with specialty: "
            "orthopedic, cardiologist, or general only."
        )
    return _doctor_reply(doctors)


def _handle_get_slots(args: dict) -> str:
    doctor_name = args.get("doctor_name", "")
    doctor = hospital.get_doctor_by_name(doctor_name)
    if not doctor:
        return f"Doctor '{doctor_name}' not found. Use exact name from get_doctors_by_specialty."
    slots = hospital.get_available_slots(doctor["name"], int(args.get("limit", 2) or 2))
    if not slots:
        return f"No open slots for {doctor['name']}."
    times = " or ".join(f"{s['date']} at {s['time']}" for s in slots)
    return f"{doctor['name']} is available {times}. Which time works better for you?"


def _handle_book(args: dict) -> str:
    return hospital.book_appointment(
        args.get("doctor_name", ""),
        args.get("patient_name", ""),
        args.get("phone", ""),
        args.get("slot_date", ""),
        args.get("slot_time", ""),
    )["message"]


def _handle_cancel(args: dict) -> str:
    result = hospital.cancel_appointment(
        args.get("patient_name", ""),
        args.get("slot_date", ""),
        args.get("slot_time"),
        args.get("doctor_name") or None,
    )
    if result.get("success"):
        return f"Cancellation successful. {result['message']} Tell the caller the appointment is cancelled."
    return result["message"]


def _handle_insurance(args: dict) -> str:
    return hospital.check_insurance(args.get("provider_name", ""))["message"]


HANDLERS = {
    "get_emergency_doctors": _handle_get_emergency,
    "get_doctors_by_specialty": _handle_get_doctors,
    "get_available_slots": _handle_get_slots,
    "book_appointment": _handle_book,
    "cancel_appointment": _handle_cancel,
    "check_insurance": _handle_insurance,
}


def _run_tool(name: str, args: dict, message: dict | None = None) -> str:
    tool = _tool_name(name)
    handler = HANDLERS.get(tool)
    if not handler:
        return f"Unknown tool '{name}'. Use function name get_doctors_by_specialty etc."
    if tool == "get_doctors_by_specialty":
        return _handle_get_doctors(args, message)
    return handler(args)


@router.get("/webhook")
def webhook_ping():
    return {"status": "ok", "message": "Webhook reachable. VAPI sends POST tool-calls here."}


@router.post("/webhook")
async def vapi_webhook(request: Request):
    raw = await request.body()
    if not raw.strip():
        return JSONResponse(
            {"received": True, "hint": "Send JSON with message.type tool-calls"},
            status_code=200,
        )
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    message = _normalize_message(body)
    if not message:
        logger.warning("unrecognized webhook body keys=%s", list(body.keys()) if isinstance(body, dict) else type(body))
        return JSONResponse({"received": True}, status_code=200)

    msg_type = message.get("type")
    if msg_type not in ("tool-calls", "function-call"):
        return JSONResponse({"received": True}, status_code=200)

    results = []
    for tc in _tool_call_items(message):
        tid, name, args = _extract_call(tc)
        text = " ".join(_run_tool(name, args, message).split())
        logger.info("tool=%s args=%s result=%s", name, args, text[:200])
        results.append({"toolCallId": tid, "result": text})

    return JSONResponse({"results": results}, status_code=200)
