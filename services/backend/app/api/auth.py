from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_superadmin
from app.core.config import get_settings
from app.core.errors import AuthAppError, NotFoundAppError
from app.core.security import create_token, decode_token
from app.db.session import get_db_session
from app.models.entities import AdminUser
from app.schemas.api import (
    LoginRequest,
    RefreshRequest,
    TokenPayload,
    UserCreateRequest,
    UserPasswordResetRequest,
    UserRead,
    UserUpdateRequest,
)
from app.services.platform_service import PlatformService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPayload)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)) -> TokenPayload:
    _, tokens = PlatformService(db).login(payload)
    return TokenPayload(**tokens)


@router.post("/refresh", response_model=TokenPayload)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db_session)) -> TokenPayload:
    try:
        data = decode_token(payload.refresh_token)
    except Exception as exc:
        raise AuthAppError(f"刷新令牌无效：{exc}") from exc
    if data.get("type") != "refresh":
        raise AuthAppError("刷新令牌无效。")
    user = db.get(AdminUser, int(data["sub"]))
    if user is None:
        raise NotFoundAppError("用户不存在。")
    settings = get_settings()
    return TokenPayload(
        access_token=create_token(
            str(user.id),
            "access",
            settings.access_token_expire_minutes,
            {"username": user.username, "role": user.role},
        ),
        refresh_token=create_token(
            str(user.id),
            "refresh",
            settings.refresh_token_expire_minutes,
            {"username": user.username, "role": user.role},
        ),
    )


@router.get("/me", response_model=UserRead)
def me(current_user: AdminUser = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user, from_attributes=True)


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(require_superadmin),
) -> list[UserRead]:
    return [UserRead.model_validate(item, from_attributes=True) for item in PlatformService(db).list_users()]


@router.post("/users", response_model=UserRead)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(require_superadmin),
) -> UserRead:
    user = PlatformService(db).create_user(payload)
    return UserRead.model_validate(user, from_attributes=True)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(require_superadmin),
) -> UserRead:
    user = PlatformService(db).update_user(user_id, payload)
    return UserRead.model_validate(user, from_attributes=True)


@router.post("/users/{user_id}/reset-password", response_model=UserRead)
def reset_user_password(
    user_id: int,
    payload: UserPasswordResetRequest,
    db: Session = Depends(get_db_session),
    _: AdminUser = Depends(require_superadmin),
) -> UserRead:
    user = PlatformService(db).reset_user_password(user_id, payload)
    return UserRead.model_validate(user, from_attributes=True)
