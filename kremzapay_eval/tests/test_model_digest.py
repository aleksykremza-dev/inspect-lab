"""model_digest: the digest is read before and after a campaign; unreadable or changed digests fail loudly."""
import json

import httpx
import pytest

from kremzapay_eval import model_digest
from kremzapay_eval.model_digest import DigestError, digest, main

MODEL = "qwen2.5:7b-instruct"


def _tags(monkeypatch, payload=None, error=None, status=200):
    def get(url, timeout):
        if error:
            raise error
        return httpx.Response(status, json=payload, request=httpx.Request("GET", url))
    monkeypatch.setattr(model_digest.httpx, "get", get)


def test_digest_of_the_named_model(monkeypatch):
    _tags(monkeypatch, {"models": [{"name": "other:1b", "digest": "aa"}, {"name": MODEL, "digest": "sha256:bb"}]})
    assert digest("http://o", MODEL) == "sha256:bb"


@pytest.mark.parametrize("kwargs,message", [
    ({"error": httpx.ConnectError("down")}, "cannot read"),
    ({"payload": {"models": []}, "status": 500}, "cannot read"),
    ({"payload": {"nope": 1}}, "cannot read"),
    ({"payload": {"models": [{"name": "other:1b", "digest": "aa"}]}}, "0 matching entries"),
    ({"payload": {"models": [{"name": MODEL}]}}, "no digest"),
])
def test_unreadable_digest_is_an_error(monkeypatch, kwargs, message):
    _tags(monkeypatch, **kwargs)
    with pytest.raises(DigestError, match=message):
        digest("http://o", MODEL)


def test_record_then_verify_same_digest_passes(monkeypatch, tmp_path):
    _tags(monkeypatch, {"models": [{"name": MODEL, "digest": "sha256:bb"}]})
    assert main(["record", "http://o", MODEL, str(tmp_path / "before.json")]) == 0
    assert main(["verify", "http://o", MODEL, str(tmp_path / "before.json"), str(tmp_path / "after.json")]) == 0
    assert json.loads((tmp_path / "after.json").read_text())["same_as_before"] is True


def test_changed_digest_fails_the_verify(monkeypatch, tmp_path):
    _tags(monkeypatch, {"models": [{"name": MODEL, "digest": "sha256:bb"}]})
    main(["record", "http://o", MODEL, str(tmp_path / "before.json")])
    _tags(monkeypatch, {"models": [{"name": MODEL, "digest": "sha256:cc"}]})
    assert main(["verify", "http://o", MODEL, str(tmp_path / "before.json"), str(tmp_path / "after.json")]) == 1
    assert json.loads((tmp_path / "after.json").read_text())["same_as_before"] is False


def test_unreachable_ollama_fails_record_and_writes_the_reason(monkeypatch, tmp_path, capsys):
    _tags(monkeypatch, error=httpx.ConnectError("down"))
    assert main(["record", "http://o", MODEL, str(tmp_path / "before.json")]) == 1
    assert "cannot read" in json.loads((tmp_path / "before.json").read_text())["error"]
    assert "cannot read" in capsys.readouterr().err
