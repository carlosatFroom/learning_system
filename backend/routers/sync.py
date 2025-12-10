from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.sync_service import SyncService
from typing import Optional
import os

router = APIRouter(prefix="/api/sync", tags=["sync"])

@router.get("/status")
def get_sync_status():
    service = SyncService()
    state = service._get_state()
    can_sync = service.can_sync()
    
    return {
        "last_sync": state.get("last_sync"),
        "remote_configured": bool(service.remote_url),
        "can_sync": can_sync['allowed'],
        "message": can_sync['reason']
    }

@router.post("/trigger")
def trigger_sync(force: bool = Query(False), reset: bool = Query(False)):
    service = SyncService()
    result = service.run_sync(force=force, reset=reset)
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    
    return result
