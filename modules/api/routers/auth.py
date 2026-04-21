"""
LADA API — Auth routes (/auth/*)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Body, Header, Request, Response, Depends
from modules.api.deps import set_request_id_header

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _parse_bearer_token(authorization: Optional[str]) -> str:
    raw = (authorization or "").strip()
    if not raw:
        return ""

    parts = raw.split(None, 1)
    if len(parts) != 2:
        return ""

    scheme, token = parts
    if scheme.lower() != "bearer":
        return ""

    return token.strip()


def create_auth_router(state):
    """Create auth router bound to server state."""
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="auth")

    r = APIRouter(tags=["auth"], dependencies=[Depends(_trace_request)])

    @r.post("/auth/login")
    async def auth_login(body: dict = Body(default={})):
        """Validate password and return a session token."""
        password = body.get("password", "")
        if password == state._auth_password:
            token = state.create_session_token()
            return {"success": True, "token": token, "expires_in": state._session_ttl}
        raise HTTPException(status_code=401, detail="Invalid password")

    @r.get("/auth/check")
    async def auth_check(authorization: Optional[str] = Header(None)):
        """Check if current session token is still valid."""
        token = _parse_bearer_token(authorization)
        if state.validate_session_token(token):
            return {"valid": True}
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    @r.post("/auth/logout")
    async def auth_logout(authorization: Optional[str] = Header(None)):
        """Invalidate a session token."""
        token = _parse_bearer_token(authorization)
        state.invalidate_token(token)
        return {"success": True}

    return r
