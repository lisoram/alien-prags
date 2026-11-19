"""Read domain packs from disk and validate them. Pure: no database, no global state.

A pack that has any problem is reported as one or more PackIssue(domain, file,
field, reason) and is NOT loaded at all (never half-loaded). Other packs are
unaffected.
"""

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.domains.glossary import Glossary, GlossaryError, parse_glossary
from app.domains.registry import CONNECTOR_TYPES, CUSTOM_CHECKS, NameRegistry
from app.schemas import DomainConfig

logger = logging.getLogger("app.domains.loader")

YAML_FILE = "domain.yaml"
GLOSSARY_FILE = "glossary.csv"
PROMPT_FILE = "prompt.md"


@dataclass(frozen=True)
class PackIssue:
    domain: str  # folder name (the declared name may itself be what is broken)
    file: str
    field: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"domain": self.domain, "file": self.file, "field": self.field, "reason": self.reason}


@dataclass(frozen=True)
class LoadedDomain:
    config: DomainConfig
    glossary: Glossary
    prompt: str
    config_hash: str
    folder: str
    enabled: bool  # effective: config.enabled AND the eval gate (see service.py)


def compute_pack_hash(folder: Path) -> str:
    """sha256 over every file in the pack (relative path + bytes), in a stable order."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _yaml_issues(folder: str, exc: yaml.YAMLError) -> list[PackIssue]:
    mark = getattr(exc, "problem_mark", None)
    where = f"line {mark.line + 1}, column {mark.column + 1}" if mark else "unknown position"
    problem = getattr(exc, "problem", None) or str(exc)
    return [PackIssue(folder, YAML_FILE, "(yaml syntax)", f"{problem} at {where}")]


def _pydantic_issues(folder: str, exc: ValidationError) -> list[PackIssue]:
    return [
        PackIssue(folder, YAML_FILE, ".".join(str(p) for p in err["loc"]) or "(root)", err["msg"])
        for err in exc.errors()
    ]


def load_pack(
    folder: Path,
    connectors: NameRegistry = CONNECTOR_TYPES,
    checks: NameRegistry = CUSTOM_CHECKS,
) -> tuple[LoadedDomain | None, list[PackIssue], str | None]:
    """Load one pack. Returns (pack or None, issues, declared name or None).

    The declared name is returned even when the pack fails, so the caller can
    detect two folders claiming the same name.
    """
    fname = folder.name
    issues: list[PackIssue] = []
    config: DomainConfig | None = None
    declared_name: str | None = None

    yaml_path = folder / YAML_FILE
    if not yaml_path.is_file():
        issues.append(PackIssue(fname, YAML_FILE, "(file)", "file is missing"))
    else:
        try:
            raw = yaml.safe_load(_read_text(yaml_path))
        except yaml.YAMLError as exc:
            issues += _yaml_issues(fname, exc)
        except UnicodeDecodeError as exc:
            issues.append(PackIssue(fname, YAML_FILE, "(encoding)", f"not valid UTF-8: {exc.reason}"))
        else:
            if not isinstance(raw, dict):
                issues.append(PackIssue(fname, YAML_FILE, "(root)", "must be a mapping of keys to values"))
            else:
                if isinstance(raw.get("name"), str):
                    declared_name = raw["name"]
                try:
                    config = DomainConfig.model_validate(raw)
                except ValidationError as exc:
                    issues += _pydantic_issues(fname, exc)

    if config is not None:
        if config.name != fname:
            issues.append(PackIssue(
                fname, YAML_FILE, "name",
                f"folder name '{fname}' must equal name '{config.name}'",
            ))
        for i, src in enumerate(config.sources):
            if not connectors.is_registered(src.type):
                issues.append(PackIssue(
                    fname, YAML_FILE, f"sources.{i}.type",
                    f"unknown connector type '{src.type}' (registered: {', '.join(connectors.names())})",
                ))
        for i, check in enumerate(config.eval.custom_checks):
            if not checks.is_registered(check):
                issues.append(PackIssue(
                    fname, YAML_FILE, f"eval.custom_checks.{i}",
                    f"unknown custom check '{check}' (registered: {', '.join(checks.names())})",
                ))

    prompt = ""
    prompt_path = folder / PROMPT_FILE
    if not prompt_path.is_file():
        issues.append(PackIssue(fname, PROMPT_FILE, "(file)", "file is missing"))
    else:
        try:
            prompt = _read_text(prompt_path)
        except UnicodeDecodeError as exc:
            issues.append(PackIssue(fname, PROMPT_FILE, "(encoding)", f"not valid UTF-8: {exc.reason}"))
        else:
            if not prompt.strip():
                issues.append(PackIssue(fname, PROMPT_FILE, "(content)", "file is empty"))

    glossary = Glossary()
    glossary_path = folder / GLOSSARY_FILE
    if not glossary_path.is_file():
        issues.append(PackIssue(fname, GLOSSARY_FILE, "(file)", "file is missing"))
    else:
        try:
            glossary = parse_glossary(_read_text(glossary_path))
        except GlossaryError as exc:
            issues.append(PackIssue(fname, GLOSSARY_FILE, exc.field, exc.reason))
        except UnicodeDecodeError as exc:
            issues.append(PackIssue(fname, GLOSSARY_FILE, "(encoding)", f"not valid UTF-8: {exc.reason}"))

    if issues or config is None:
        return None, issues, declared_name

    pack = LoadedDomain(
        config=config,
        glossary=glossary,
        prompt=prompt,
        config_hash=compute_pack_hash(folder),
        folder=fname,
        enabled=config.enabled,
    )
    return pack, [], declared_name


def scan_packs(
    domains_dir: Path,
    connectors: NameRegistry = CONNECTOR_TYPES,
    checks: NameRegistry = CUSTOM_CHECKS,
) -> tuple[list[LoadedDomain], list[PackIssue]]:
    """Load every pack folder under domains_dir. Valid packs load even if others fail."""
    if not domains_dir.is_dir():
        logger.error("domains_dir_missing", extra={"path": str(domains_dir)})
        return [], [PackIssue("(domains folder)", str(domains_dir), "(folder)", "domains folder does not exist")]

    folders = sorted(p for p in domains_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
    results: dict[str, LoadedDomain | None] = {}
    issues: list[PackIssue] = []
    declared: dict[str, list[str]] = defaultdict(list)  # declared name -> folders claiming it

    for folder in folders:
        pack, pack_issues, declared_name = load_pack(folder, connectors, checks)
        results[folder.name] = pack
        issues += pack_issues
        if declared_name is not None:
            declared[declared_name].append(folder.name)

    # Two folders claiming one name: reject both, naming both folders.
    for name, claimants in declared.items():
        if len(claimants) < 2:
            continue
        for folder_name in claimants:
            others = ", ".join(f"'{c}'" for c in claimants if c != folder_name)
            issues.append(PackIssue(
                folder_name, YAML_FILE, "name",
                f"duplicate domain name '{name}': folder '{folder_name}' and folder(s) {others} declare the same name",
            ))
            results[folder_name] = None

    for issue in issues:
        logger.error("domain_pack_failed", extra=issue.as_dict())

    return [p for p in results.values() if p is not None], issues
