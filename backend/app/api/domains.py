"""Domain endpoints: list, detail, and admin reload."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_role, require_admin
from app.domains import service

logger = logging.getLogger("app.api.domains")
router = APIRouter()


class DomainListItem(BaseModel):
    name: str
    display_name: str
    disclaimer: str


class DomainSummary(BaseModel):
    """Public view of a domain. Deliberately omits access rules and other internals."""

    name: str
    display_name: str
    disclaimer: str
    require_citations: bool


class PackFailure(BaseModel):
    domain: str
    file: str
    field: str
    reason: str


class ReloadResponse(BaseModel):
    loaded: list[str]
    failed: list[PackFailure]


@router.get("/domains", response_model=list[DomainListItem])
def list_domains(role: str = Depends(get_current_role)):
    return [
        DomainListItem(
            name=d.config.name,
            display_name=d.config.display_name,
            disclaimer=d.config.generation.disclaimer,
        )
        for d in service.list_domains(enabled_only=True, role=role)
    ]


@router.get("/domains/{name}", response_model=DomainSummary)
def get_domain(name: str, role: str = Depends(get_current_role)):
    domain = service.get_domain(name)
    # Same 404 for "doesn't exist", "disabled" and "not for your role", so the
    # response doesn't reveal which domains exist.
    if domain is None or not domain.enabled or role not in domain.config.access.allowed_roles:
        raise HTTPException(status_code=404, detail=f"Domain '{name}' not found")
    return DomainSummary(
        name=domain.config.name,
        display_name=domain.config.display_name,
        disclaimer=domain.config.generation.disclaimer,
        require_citations=domain.config.generation.require_citations,
    )


@router.post("/admin/domains/reload", response_model=ReloadResponse)
def reload_domains(_: str = Depends(require_admin)):
    result = service.reload()
    return ReloadResponse(
        loaded=result.loaded,
        failed=[PackFailure(**issue.as_dict()) for issue in result.failed],
    )
