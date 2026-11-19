"""Who is calling? Temporary stand-in until real auth exists.

TODO(Module 7): replace this whole file with real authentication. Every route
gets the caller's role through get_current_role / require_admin, so swapping
the implementation here is the only change needed.
"""

from fastapi import Depends, Header, HTTPException

ADMIN_ROLE = "admin"
DEFAULT_ROLE = "researcher"


def get_current_role(x_role: str = Header(default=DEFAULT_ROLE, alias="X-Role")) -> str:
    # TEMPORARY: trusts whatever the client sends in X-Role. Not secure.
    return x_role.strip() or DEFAULT_ROLE


def require_admin(role: str = Depends(get_current_role)) -> str:
    if role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Admin role required")
    return role
