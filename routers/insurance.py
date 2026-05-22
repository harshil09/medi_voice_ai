from fastapi import APIRouter
from services import hospital

router = APIRouter(prefix="/insurance", tags=["insurance"])


@router.get("/accepted")
def list_accepted():
    return hospital.list_accepted_insurance()
