"""Shared building blocks for the schemas."""

from datetime import timedelta, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, PlainSerializer

# IST has no daylight saving, so a fixed offset is exact (and needs no tzdata).
IST = timezone(timedelta(hours=5, minutes=30))

# Timezone-aware only (naive datetimes are rejected). Any input zone is accepted,
# but JSON output is always ISO 8601 in IST, e.g. 2026-11-18T14:30:00+05:30.
ISTDatetime = Annotated[
    AwareDatetime,
    PlainSerializer(lambda d: d.astimezone(IST).isoformat(), return_type=str, when_used="json"),
]

DocLabel = Literal["public", "internal", "restricted"]
