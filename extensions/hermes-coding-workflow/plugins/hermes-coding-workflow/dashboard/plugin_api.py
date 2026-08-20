"""Optional read-only dashboard payload for the integrated distribution."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
def status() -> dict[str, str]:
    return {"plugin": "hermes-coding-workflow", "status": "available"}
