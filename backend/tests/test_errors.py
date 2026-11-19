def test_validation_error_uses_envelope(make_client):
    r = make_client().get("/api/v1/health?deep=notabool")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert isinstance(err["message"], str)
    assert "errors" in err["details"]


def test_not_found_uses_envelope(make_client):
    r = make_client().get("/api/v1/nope")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message", "details"}
