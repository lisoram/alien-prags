import pytest

from app.core.providers import LocalStorage


def test_put_get_exists(tmp_path):
    s = LocalStorage(tmp_path)
    assert not s.exists("a/b.bin")
    s.put("a/b.bin", b"\x00\x01data")
    assert s.exists("a/b.bin")
    assert s.get("a/b.bin") == b"\x00\x01data"


def test_key_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).put("../escape.txt", b"x")
