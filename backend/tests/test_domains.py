"""Loader, validator, glossary, service and endpoint tests for Module 1.

Packs are copied from tests/fixtures into a temp folder, so tests never touch
the real domains/ folder. Postgres is replaced by in-memory SQLite (the upsert
SQL is portable).
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domains import service
from app.domains.glossary import GlossaryError, parse_glossary
from app.domains.loader import compute_pack_hash, scan_packs
from app.domains.registry import CONNECTOR_TYPES, CUSTOM_CHECKS, NameRegistry
from app.main import app
from app.schemas import DomainConfig

FIXTURES = Path(__file__).parent / "fixtures"


# ---------- helpers ----------

@pytest.fixture
def domains_dir(tmp_path):
    d = tmp_path / "domains"
    d.mkdir()
    return d


def add(domains_dir: Path, kind: str, name: str) -> Path:
    dest = domains_dir / name
    shutil.copytree(FIXTURES / kind / name, dest)
    return dest


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE domains (name TEXT PRIMARY KEY, display_name TEXT, enabled BOOLEAN, "
            "config_hash TEXT, last_ingested_at TIMESTAMP, last_eval_run_id TEXT, loaded_at TIMESTAMP)"
        ))
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def reset_service():
    yield
    service._snapshot = service._Snapshot(domains={}, failures=[])


def issues_for(domains_dir, folder):
    _, issues = scan_packs(domains_dir)
    return [i for i in issues if i.domain == folder]


# ---------- DomainConfig validators ----------

def base_config():
    return DomainConfig.model_validate_json(
        '{"name":"demo","display_name":"D","sources":[{"type":"pdf_folder","path":"p"}],'
        '"chunking":{"strategy":"fixed","max_tokens":100,"overlap_tokens":10,"keep_tables_whole":true},'
        '"retrieval":{"top_k":5,"candidate_k":10,"hybrid":true,"keyword_weight":0.5,"rerank":false},'
        '"access":{"allowed_roles":["a"],"default_doc_label":"public"},'
        '"generation":{"disclaimer":"d","require_citations":true,"refuse_topics":[]},'
        '"eval":{"min_recall_at_5":0.8,"min_faithfulness":0.9,"min_citation_precision":0.9,"custom_checks":[]}}'
    ).model_dump()


@pytest.mark.parametrize(
    "path, value, expected_loc",
    [
        (("retrieval", "candidate_k"), 3, "candidate_k"),
        (("chunking", "overlap_tokens"), 100, "overlap_tokens"),
        (("eval", "min_faithfulness"), 1.2, "min_faithfulness"),
        (("eval", "min_recall_at_5"), -0.1, "min_recall_at_5"),
        (("retrieval", "keyword_weight"), 2, "keyword_weight"),
        (("name",), "Not A Slug", "name"),
        (("access", "allowed_roles"), [], "allowed_roles"),
    ],
)
def test_config_validators_reject(path, value, expected_loc):
    data = base_config()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError) as exc:
        DomainConfig.model_validate(data)
    assert expected_loc in {str(p) for e in exc.value.errors() for p in e["loc"]}


def test_config_rejects_unknown_key_and_sourceless_source():
    data = base_config()
    with pytest.raises(ValidationError):
        DomainConfig.model_validate({**data, "surprise": 1})
    data["sources"] = [{"type": "pdf_folder"}]
    with pytest.raises(ValidationError):
        DomainConfig.model_validate(data)


# ---------- Loader: valid and every malformed case ----------

def test_valid_packs_load(domains_dir):
    add(domains_dir, "valid", "alpha")
    add(domains_dir, "valid", "beta")
    packs, issues = scan_packs(domains_dir)
    assert issues == []
    assert [p.config.name for p in packs] == ["alpha", "beta"]
    assert packs[0].prompt.strip() == "Fixture prompt."


def test_bad_yaml_names_file_and_position(domains_dir):
    add(domains_dir, "broken", "bad_yaml")
    [issue] = issues_for(domains_dir, "bad_yaml")
    assert issue.file == "domain.yaml"
    assert "line" in issue.reason


def test_schema_violation_names_each_field(domains_dir):
    add(domains_dir, "broken", "schema_violation")
    issues = issues_for(domains_dir, "schema_violation")
    fields = {i.field for i in issues}
    assert {"retrieval.candidate_k", "retrieval.keyword_weight", "chunking.overlap_tokens"} <= fields
    assert all(i.file == "domain.yaml" for i in issues)


def test_folder_name_mismatch(domains_dir):
    add(domains_dir, "broken", "folder_mismatch")
    [issue] = issues_for(domains_dir, "folder_mismatch")
    assert issue.field == "name" and "must equal" in issue.reason


def test_unknown_connector(domains_dir):
    add(domains_dir, "broken", "unknown_connector")
    [issue] = issues_for(domains_dir, "unknown_connector")
    assert issue.field == "sources.0.type" and "carrier_pigeon" in issue.reason


def test_unknown_custom_check(domains_dir):
    add(domains_dir, "broken", "unknown_check")
    [issue] = issues_for(domains_dir, "unknown_check")
    assert issue.field == "eval.custom_checks.0" and "no_such_check" in issue.reason


def test_missing_prompt(domains_dir):
    add(domains_dir, "broken", "missing_prompt")
    [issue] = issues_for(domains_dir, "missing_prompt")
    assert issue.file == "prompt.md" and "missing" in issue.reason


def test_bad_glossary_row(domains_dir):
    add(domains_dir, "broken", "bad_glossary")
    [issue] = issues_for(domains_dir, "bad_glossary")
    assert issue.file == "glossary.csv" and issue.field == "row 2: term"


def test_missing_domain_yaml(domains_dir):
    (domains_dir / "empty_folder").mkdir()
    issues = issues_for(domains_dir, "empty_folder")
    assert {i.file for i in issues} == {"domain.yaml", "prompt.md", "glossary.csv"}
    assert all("missing" in i.reason for i in issues)


def test_duplicate_names_reject_both_and_name_both_folders(domains_dir):
    add(domains_dir, "broken", "dup_one")
    add(domains_dir, "broken", "dup_two")
    add(domains_dir, "valid", "alpha")
    packs, issues = scan_packs(domains_dir)
    assert [p.config.name for p in packs] == ["alpha"]  # neither duplicate loaded, others unaffected
    dup = [i for i in issues if "duplicate" in i.reason]
    assert {i.domain for i in dup} == {"dup_one", "dup_two"}
    assert all("dup_one" in i.reason and "dup_two" in i.reason for i in dup)


def test_one_bad_pack_does_not_block_others(domains_dir):
    add(domains_dir, "broken", "bad_yaml")
    add(domains_dir, "valid", "alpha")
    packs, issues = scan_packs(domains_dir)
    assert [p.config.name for p in packs] == ["alpha"] and len(issues) == 1


def test_registries_accept_new_name_in_one_line(domains_dir):
    add(domains_dir, "broken", "unknown_connector")
    connectors = NameRegistry("connector type")
    connectors.register("carrier_pigeon")  # the one-line change
    packs, issues = scan_packs(domains_dir, connectors=connectors)
    assert issues == [] and len(packs) == 1


def test_default_registrations():
    assert {"pdf_folder", "web_page", "csv", "docx_folder"} <= set(CONNECTOR_TYPES.names())
    assert {"includes_disclaimer", "includes_safety_caveat"} <= set(CUSTOM_CHECKS.names())


# ---------- Hash ----------

def test_hash_changes_when_any_file_changes(domains_dir):
    pack = add(domains_dir, "valid", "alpha")
    before = compute_pack_hash(pack)
    assert compute_pack_hash(pack) == before
    for rel in ("domain.yaml", "glossary.csv", "prompt.md", "eval/gold.jsonl"):
        original = (pack / rel).read_bytes()
        (pack / rel).write_bytes(original + b"\n# edit")
        assert compute_pack_hash(pack) != before, rel
        (pack / rel).write_bytes(original)
    assert compute_pack_hash(pack) == before


# ---------- Glossary ----------

def test_glossary_lookup_by_term_synonym_abbreviation_case_insensitive():
    g = parse_glossary("term,synonyms,abbreviation,definition\nAlpha term,first|beta,AT,Def.\n")
    entry = g.lookup("alpha TERM")
    assert entry is not None and entry.definition == "Def."
    assert g.lookup("FIRST") is entry and g.lookup("Beta") is entry and g.lookup("at") is entry
    assert g.lookup("unknown") is None


def test_glossary_errors():
    with pytest.raises(GlossaryError, match="missing column"):
        parse_glossary("term,definition\nx,y\n")
    with pytest.raises(GlossaryError, match="ambiguous"):
        parse_glossary("term,synonyms,abbreviation,definition\nA,x,,d\nB,X,,d\n")


# ---------- Service + enable gate + DB sync ----------

def test_service_reads(domains_dir, db):
    add(domains_dir, "valid", "alpha")
    result = service.reload(domains_dir, db, allow_unevaluated=False)
    assert result.loaded == ["alpha"] and result.failed == []
    assert service.get_domain("alpha").config.display_name == "Sample"
    assert service.get_domain("nope") is None
    assert service.get_glossary("alpha").lookup("first") is not None
    assert service.get_glossary("nope") is None


def test_new_folder_appears_after_reload_without_code_change(domains_dir, db):
    add(domains_dir, "valid", "alpha")
    service.reload(domains_dir, db, allow_unevaluated=False)
    assert service.list_domains(enabled_only=False) and not service.get_domain("beta")
    add(domains_dir, "valid", "beta")
    service.reload(domains_dir, db, allow_unevaluated=False)
    assert {d.config.name for d in service.list_domains(enabled_only=False)} == {"alpha", "beta"}


def test_enable_gate_blocks_unevaluated_domain(domains_dir, db, caplog):
    add(domains_dir, "valid", "enabled_pack")
    with caplog.at_level("WARNING"):
        service.reload(domains_dir, db, allow_unevaluated=False)
    assert service.get_domain("enabled_pack").config.enabled is True  # what the file says
    assert service.get_domain("enabled_pack").enabled is False  # what the system does
    assert service.list_domains(enabled_only=True) == []
    assert any(r.message == "domain_kept_disabled_no_eval_run" for r in caplog.records)


def test_enable_gate_dev_override(domains_dir, db):
    add(domains_dir, "valid", "enabled_pack")
    service.reload(domains_dir, db, allow_unevaluated=True)
    assert [d.config.name for d in service.list_domains(enabled_only=True)] == ["enabled_pack"]


def test_enable_gate_opens_with_eval_run(domains_dir, db):
    add(domains_dir, "valid", "enabled_pack")
    service.reload(domains_dir, db, allow_unevaluated=False)
    with db() as s:
        s.execute(text("UPDATE domains SET last_eval_run_id = 'run-1' WHERE name = 'enabled_pack'"))
        s.commit()
    service.reload(domains_dir, db, allow_unevaluated=False)
    assert service.get_domain("enabled_pack").enabled is True


def test_disabled_in_yaml_stays_disabled_even_with_override(domains_dir, db):
    add(domains_dir, "valid", "alpha")
    service.reload(domains_dir, db, allow_unevaluated=True)
    assert service.list_domains(enabled_only=True) == []
    assert service.get_domain("alpha") is not None


def test_list_domains_role_filter(domains_dir, db):
    add(domains_dir, "valid", "enabled_pack")
    service.reload(domains_dir, db, allow_unevaluated=True)
    assert len(service.list_domains(role="researcher")) == 1
    assert service.list_domains(role="stranger") == []
    assert len(service.list_domains(role=None)) == 1


def test_db_upsert_and_hash_change(domains_dir, db):
    pack = add(domains_dir, "valid", "alpha")
    service.reload(domains_dir, db, allow_unevaluated=False)
    with db() as s:
        row1 = s.execute(text("SELECT name, display_name, enabled, config_hash, last_ingested_at, last_eval_run_id FROM domains")).all()
    assert len(row1) == 1 and row1[0].name == "alpha" and row1[0].config_hash == compute_pack_hash(pack)
    assert row1[0].last_ingested_at is None and row1[0].last_eval_run_id is None

    (pack / "prompt.md").write_text("Changed prompt.\n", encoding="utf-8")
    service.reload(domains_dir, db, allow_unevaluated=False)
    with db() as s:
        row2 = s.execute(text("SELECT config_hash FROM domains")).all()
    assert len(row2) == 1 and row2[0].config_hash != row1[0].config_hash  # upsert, not insert


def test_failed_pack_not_written_or_served(domains_dir, db):
    add(domains_dir, "broken", "bad_yaml")
    result = service.reload(domains_dir, db, allow_unevaluated=False)
    assert result.loaded == [] and len(result.failed) == 1
    with db() as s:
        assert s.execute(text("SELECT COUNT(*) FROM domains")).scalar() == 0
    assert service.get_load_failures() == result.failed


# ---------- Endpoints ----------

@pytest.fixture
def client(domains_dir, db, monkeypatch):
    add(domains_dir, "valid", "enabled_pack")
    add(domains_dir, "valid", "alpha")
    add(domains_dir, "broken", "bad_yaml")
    monkeypatch.setattr(service, "get_session_factory", lambda: db)
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "DOMAINS_DIR", str(domains_dir))
    monkeypatch.setattr(settings, "ALLOW_UNEVALUATED_DOMAINS", True)
    service.reload()
    return TestClient(app)


def test_list_endpoint(client):
    r = client.get("/api/v1/domains")  # default role: researcher
    assert r.status_code == 200
    assert r.json() == [{"name": "enabled_pack", "display_name": "Sample", "disclaimer": "Sample disclaimer."}]
    assert client.get("/api/v1/domains", headers={"X-Role": "stranger"}).json() == []


def test_detail_endpoint_is_public_summary_only(client):
    r = client.get("/api/v1/domains/enabled_pack")
    assert r.status_code == 200
    assert set(r.json()) == {"name", "display_name", "disclaimer", "require_citations"}
    assert "access" not in r.text and "allowed_roles" not in r.text


@pytest.mark.parametrize("name, role", [("nope", "researcher"), ("alpha", "researcher"), ("enabled_pack", "stranger")])
def test_detail_404_uses_error_envelope(client, name, role):
    r = client.get(f"/api/v1/domains/{name}", headers={"X-Role": role})
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found" and set(err) == {"code", "message", "details"}


def test_reload_requires_admin(client):
    r = client.post("/api/v1/admin/domains/reload")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r = client.post("/api/v1/admin/domains/reload", headers={"X-Role": "researcher"})
    assert r.status_code == 403


def test_reload_endpoint_reports_loaded_and_failed(client, domains_dir):
    r = client.post("/api/v1/admin/domains/reload", headers={"X-Role": "admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["loaded"] == ["alpha", "enabled_pack"]
    assert len(body["failed"]) == 1
    assert set(body["failed"][0]) == {"domain", "file", "field", "reason"}
    assert body["failed"][0]["domain"] == "bad_yaml" and body["failed"][0]["file"] == "domain.yaml"

    add(domains_dir, "valid", "beta")  # drop in a new folder, no code change
    body = client.post("/api/v1/admin/domains/reload", headers={"X-Role": "admin"}).json()
    assert "beta" in body["loaded"]
