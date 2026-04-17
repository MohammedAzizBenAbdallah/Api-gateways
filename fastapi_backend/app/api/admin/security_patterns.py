# app/api/admin/security_patterns.py
"""Admin API router for zero-code Prompt Injection Pattern management."""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.infrastructure.db.session import get_db_with_user
from app.models.security_pattern import SecurityPattern
from app.schemas.security_pattern import SecurityPatternCreate, SecurityPatternOut
from app.core.middleware import verify_kong_header

router = APIRouter(
    prefix="/admin/security-patterns",
    tags=["Admin - Security control"],
    dependencies=[Depends(verify_kong_header)]
)

@router.get("", response_model=List[SecurityPatternOut])
async def list_patterns(db: AsyncSession = Depends(get_db_with_user)):
    result = await db.execute(select(SecurityPattern).order_by(SecurityPattern.id))
    return result.scalars().all()

@router.post("", response_model=SecurityPatternOut)
async def create_pattern(pattern_data: SecurityPatternCreate, db: AsyncSession = Depends(get_db_with_user)):
    # Basic validation so admins don't crash the scanning engine with bad regex
    import re
    try:
        re.compile(pattern_data.pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid Regex Pattern: {e}")

    db_pattern = SecurityPattern(
        name=pattern_data.name,
        pattern=pattern_data.pattern,
        weight=pattern_data.weight,
        description=pattern_data.description,
        is_active=pattern_data.is_active
    )
    db.add(db_pattern)
    try:
        await db.commit()
        await db.refresh(db_pattern)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity Error (Duplicate Name?): {e}")

    return db_pattern

@router.delete("/{pattern_id}")
async def delete_pattern(pattern_id: int, db: AsyncSession = Depends(get_db_with_user)):
    result = await db.execute(select(SecurityPattern).where(SecurityPattern.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    await db.delete(pattern)
    await db.commit()
    return {"status": "success"}

@router.post("/reload")
async def reload_patterns(request: Request, db: AsyncSession = Depends(get_db_with_user)):
    svc = request.app.state.prompt_security_service
    await svc.reload_patterns(db)
    return {"status": "success", "message": "Patterns reloaded into memory"}
