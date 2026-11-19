"""Glossary: a term, any of its synonyms, or its abbreviation all resolve to one entry."""

import csv
import io
from dataclasses import dataclass, field

REQUIRED_COLUMNS = ("term", "synonyms", "abbreviation", "definition")


class GlossaryError(Exception):
    """A problem in glossary.csv. `field` says which column or row."""

    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    synonyms: tuple[str, ...]
    abbreviation: str | None
    definition: str


@dataclass(frozen=True)
class Glossary:
    entries: tuple[GlossaryEntry, ...] = ()
    _lookup: dict[str, GlossaryEntry] = field(default_factory=dict, repr=False, compare=False)

    def lookup(self, text: str) -> GlossaryEntry | None:
        """Find the entry for a term, synonym or abbreviation (case-insensitive)."""
        return self._lookup.get(text.strip().casefold())

    def __len__(self) -> int:
        return len(self.entries)


def parse_glossary(text: str) -> Glossary:
    """Parse glossary.csv content. Raises GlossaryError on the first problem found."""
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise GlossaryError("header", f"missing column(s): {', '.join(missing)}")

    entries: list[GlossaryEntry] = []
    lookup: dict[str, GlossaryEntry] = {}
    for row_no, row in enumerate(reader, start=2):  # row 1 is the header
        term = (row.get("term") or "").strip()
        definition = (row.get("definition") or "").strip()
        if None in row:
            raise GlossaryError(f"row {row_no}", "too many columns (an unquoted comma in a value?)")
        if not term:
            raise GlossaryError(f"row {row_no}: term", "must not be empty")
        if not definition:
            raise GlossaryError(f"row {row_no}: definition", f"must not be empty (term '{term}')")
        synonyms = tuple(s.strip() for s in (row.get("synonyms") or "").split("|") if s.strip())
        abbreviation = (row.get("abbreviation") or "").strip() or None
        entry = GlossaryEntry(term, synonyms, abbreviation, definition)

        keys = [term, *synonyms] + ([abbreviation] if abbreviation else [])
        for key in keys:
            folded = key.casefold()
            existing = lookup.get(folded)
            if existing is not None and existing is not entry:
                raise GlossaryError(
                    f"row {row_no}: term",
                    f"'{key}' already belongs to the entry for '{existing.term}', so lookups would be ambiguous",
                )
            lookup[folded] = entry
        entries.append(entry)

    return Glossary(entries=tuple(entries), _lookup=lookup)
