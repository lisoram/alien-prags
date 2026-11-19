def test_all_ok(make_client):
    r = make_client().get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "services": {k: {"status": "ok"} for k in ("postgres", "qdrant", "gemini", "storage")},
    }
    assert r.headers["X-Request-ID"]


def test_qdrant_down_is_named_with_503(make_client):
    r = make_client(qdrant_fail="connection refused").get("/api/v1/health")
    body = r.json()
    assert r.status_code == 503
    assert body["status"] == "degraded"
    assert body["services"]["qdrant"] == {"status": "error", "message": "connection refused"}
    assert body["services"]["postgres"]["status"] == "ok"
    assert body["services"]["storage"]["status"] == "ok"
