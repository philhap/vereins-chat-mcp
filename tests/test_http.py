"""Tests für die GET-only HTTP-Basis."""

import pytest
import requests

from webling_mcp.client import http


class FakeResponse:
    """Minimaler Ersatz für requests.Response."""

    def __init__(self, daten):
        self._daten = daten

    def raise_for_status(self):
        pass

    def json(self):
        return self._daten


def test_get_wirft_bei_fehlender_konfiguration(monkeypatch):
    monkeypatch.delenv("WEBLING_BASE_URL", raising=False)
    monkeypatch.delenv("WEBLING_MCP_API_KEY", raising=False)
    with pytest.raises(http.WeblingKonfigFehler):
        http.get("member")


def test_pruefe_konfiguration_wirft_bei_fehlendem_key(monkeypatch):
    monkeypatch.setenv("WEBLING_BASE_URL", "https://test.webling.eu/api/1")
    monkeypatch.delenv("WEBLING_MCP_API_KEY", raising=False)
    with pytest.raises(http.WeblingKonfigFehler):
        http.pruefe_konfiguration()


def test_get_baut_url_und_header(monkeypatch):
    monkeypatch.setenv("WEBLING_BASE_URL", "https://test.webling.eu/api/1")
    monkeypatch.setenv("WEBLING_MCP_API_KEY", "testkey")
    erfasst = {}

    def fake_requests_get(url, headers=None, params=None, timeout=None):
        erfasst["url"] = url
        erfasst["headers"] = headers
        return FakeResponse({"objects": []})

    monkeypatch.setattr(http.requests, "get", fake_requests_get)

    daten = http.get("member")

    assert daten == {"objects": []}
    assert erfasst["url"] == "https://test.webling.eu/api/1/member"
    assert erfasst["headers"]["apikey"] == "testkey"


def test_get_propagiert_http_fehler(monkeypatch):
    """Nicht-2xx-Antworten müssen als requests.HTTPError aus get() herauskommen."""
    monkeypatch.setenv("WEBLING_BASE_URL", "https://test.webling.eu/api/1")
    monkeypatch.setenv("WEBLING_MCP_API_KEY", "testkey")

    class FehlerResponse(FakeResponse):
        def raise_for_status(self):
            raise requests.HTTPError("404 Client Error")

    def fake_requests_get(url, headers=None, params=None, timeout=None):
        return FehlerResponse({})

    monkeypatch.setattr(http.requests, "get", fake_requests_get)

    with pytest.raises(requests.HTTPError):
        http.get("member")


def test_get_toleriert_trailing_slash_in_base_url(monkeypatch):
    """Ein Trailing-Slash in WEBLING_BASE_URL darf keinen Doppel-Slash erzeugen."""
    monkeypatch.setenv("WEBLING_BASE_URL", "https://test.webling.eu/api/1/")
    monkeypatch.setenv("WEBLING_MCP_API_KEY", "testkey")
    erfasst = {}

    def fake_requests_get(url, headers=None, params=None, timeout=None):
        erfasst["url"] = url
        return FakeResponse({"objects": []})

    monkeypatch.setattr(http.requests, "get", fake_requests_get)

    http.get("member")

    assert erfasst["url"] == "https://test.webling.eu/api/1/member"


def test_modul_hat_keine_schreibfunktionen():
    """Read-only by design: Es darf keine post/put/delete Funktionen geben."""
    for verboten in ("post", "put", "put_binary", "delete", "patch"):
        assert not hasattr(http, verboten)
