"""
LADA API — Auth routes (/auth/*)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Body, Header, Request, Response, Depends
from modules.api.deps import set_request_id_header

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


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
        token = ""
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        if state.validate_session_token(token):
            return {"valid": True}
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    @r.post("/auth/logout")
    async def auth_logout(authorization: Optional[str] = Header(None)):
        """Invalidate a session token."""
        token = ""
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        state.invalidate_token(token)
        return {"success": True}

    return r
