from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthAppError, PermissionAppError
from app.core.security import decode_token
from app.db.session import get_db_session
from app.models.entities import AdminUser, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings_dependency():
    return get_settings()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> AdminUser:
    if credentials is None:
        raise AuthAppError("缺少登录凭证。")
    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:
        raise AuthAppError(f"登录令牌无效：{exc}") from exc
    if payload.get("type") != "access":
        raise AuthAppError("令牌类型不正确。")
    user = db.scalar(select(AdminUser).where(AdminUser.id == int(payload["sub"])))
    if user is None:
        raise AuthAppError("用户不存在。")
    if not user.is_active:
        raise AuthAppError("当前账号已被禁用。", status_code=403, code="inactive_user")
    return user


def require_roles(*allowed_roles: str) -> Callable[[AdminUser], AdminUser]:
    allowed = set(allowed_roles)

    def dependency(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
        if current_user.role not in allowed:
            raise PermissionAppError("当前账号没有执行该操作的权限。")
        return current_user

    return dependency


def require_superadmin(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
    if current_user.role != UserRole.superadmin.value:
        raise PermissionAppError("当前账号仅具备只读或运维权限，不能执行该操作。")
    return current_user


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_internal_token != settings.internal_service_token:
        raise AuthAppError("内部服务令牌无效。")


def require_ops_token(x_internal_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_internal_token != settings.ops_agent_token:
        raise AuthAppError("运维代理令牌无效。")
