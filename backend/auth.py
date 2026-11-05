"""FastAPI dependencies: who is calling, and are they allowed."""
from typing import Optional

from fastapi import Depends, Header, HTTPException

from . import service


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required.", headers={"WWW-Authenticate": "Bearer"})
    try:
        return service.user_from_token(authorization[7:].strip())
    except service.ServiceError as exc:
        raise HTTPException(exc.status, exc.message, headers={"WWW-Authenticate": "Bearer"})


def require(*roles: str):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Your role does not allow this action.")
        return user
    return dependency
