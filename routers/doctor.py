from fastapi import APIRouter, HTTPException
from database import get_connection
from services import hospital

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("/")
def get_all_doctors():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, specialty, available, emergency FROM doctors WHERE available = 1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/emergency")
def get_emergency_doctors():
    doctors = hospital.get_emergency_doctors()
    if not doctors:
        raise HTTPException(404, "No emergency doctors on duty")
    return doctors


@router.get("/specialty/{specialty}")
def get_doctors_by_specialty(specialty: str):
    doctors = hospital.get_doctors_by_specialty(specialty)
    if not doctors:
        raise HTTPException(404, f"No doctors found for specialty: {specialty}")
    return doctors
