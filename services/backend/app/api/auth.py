from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models.entities import AdminUser
from app.schemas.api import LoginRequest, RefreshRequest, TokenPayload, UserRead
from app.services.platform_service import PlatformService
from app.core.security import create_token, decode_token
from app.core.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPayload)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)) -> TokenPayload:
    _, tokens = PlatformService(db).login(payload)
    return TokenPayload(**tokens)


@router.post("/refresh", response_model=TokenPayload)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db_session)) -> TokenPayload:
    data = decode_token(payload.refresh_token)
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="refresh token 无效")
    user = db.get(AdminUser, int(data["sub"]))
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    settings = get_settings()
    return TokenPayload(
        access_token=create_token(str(user.id), "access", settings.access_token_expire_minutes, {"username": user.username}),
        refresh_token=create_token(str(user.id), "refresh", settings.refresh_token_expire_minutes, {"username": user.username}),
    )


@router.get("/me", response_model=UserRead)
def me(current_user: AdminUser = Depends(get_current_user)) -> UserRead:
    return UserRead(
        id=current_user.id,
        username=current_user.username,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        last_login_at=current_user.last_login_at,
    )

