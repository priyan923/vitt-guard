import hmac
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.settings import settings

http_basic = HTTPBasic(auto_error=False)


def require_api_auth(
    credentials: Annotated[
        HTTPBasicCredentials | None,
        Depends(http_basic),
    ],
) -> str | None:
    if not settings.auth_enabled:
        return None

    username = credentials.username if credentials is not None else ""
    password = credentials.password if credentials is not None else ""
    username_matches = hmac.compare_digest(
        username.encode("utf-8"),
        settings.auth_username.encode("utf-8"),
    )
    password_matches = hmac.compare_digest(
        password.encode("utf-8"),
        settings.auth_password.encode("utf-8"),
    )
    if not (username_matches and password_matches):
        raise HTTPException(
            status_code=401,
            detail={"code": "authentication_required"},
            headers={"WWW-Authenticate": "Basic"},
        )
    return username
