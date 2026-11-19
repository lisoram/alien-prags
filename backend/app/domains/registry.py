"""Registries of names that a domain pack may refer to.

For now they hold names only. Module 2 attaches real connector classes and
Module 9 attaches real check functions; until then, registering a new name is
a one-line change: add it to the register(...) call below.
"""


class NameRegistry:
    def __init__(self, kind: str):
        self.kind = kind
        self._names: set[str] = set()

    def register(self, *names: str) -> None:
        self._names.update(names)

    def is_registered(self, name: str) -> bool:
        return name in self._names

    def names(self) -> list[str]:
        return sorted(self._names)


CONNECTOR_TYPES = NameRegistry("connector type")
CONNECTOR_TYPES.register("pdf_folder", "web_page", "csv", "docx_folder")

CUSTOM_CHECKS = NameRegistry("custom check")
CUSTOM_CHECKS.register("includes_disclaimer", "includes_safety_caveat")
