"""Tests für Dokument-Download und Jahresordner-Auflistung (gemockt, kein Live-Zugriff)."""

from webling_mcp.client import documents, http


class FakeResponse:
    def __init__(self, content=b"", json_daten=None):
        self.content = content
        self._json = json_daten

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def test_get_bytes_liefert_rohdaten(monkeypatch):
    aufrufe = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        aufrufe["url"] = url
        aufrufe["headers"] = headers
        return FakeResponse(content=b"%PDF-1.7 test")

    monkeypatch.setenv("WEBLING_BASE_URL", "https://verein.webling.eu/api/1")
    monkeypatch.setenv("WEBLING_MCP_API_KEY", "testkey")
    monkeypatch.setattr(http.requests, "get", fake_get)

    daten = http.get_bytes("document/55/download")

    assert daten == b"%PDF-1.7 test"
    assert aufrufe["url"] == "https://verein.webling.eu/api/1/document/55/download"
    assert aufrufe["headers"]["apikey"] == "testkey"


def test_get_bytes_nutzt_absoluten_href_gegen_serverhost(monkeypatch):
    """Ein href aus properties.file (z.B. '/api/1/document/55/file/x.pdf') geht an den
    Server-Host, NICHT an base_url + href (sonst dupliziert sich '/api/1')."""
    aufrufe = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        aufrufe["url"] = url
        return FakeResponse(content=b"PK\x03\x04 test")

    monkeypatch.setenv("WEBLING_BASE_URL", "https://verein.webling.eu/api/1")
    monkeypatch.setenv("WEBLING_MCP_API_KEY", "testkey")
    monkeypatch.setattr(http.requests, "get", fake_get)

    daten = http.get_bytes("/api/1/document/55/file/Anwesenheitsliste+GV2026.pdf")

    assert daten == b"PK\x03\x04 test"
    assert aufrufe["url"] == "https://verein.webling.eu/api/1/document/55/file/Anwesenheitsliste+GV2026.pdf"


def test_lade_dokument_nutzt_href_aus_dokument_metadaten(monkeypatch):
    """Webling liefert Downloads nicht über 'document/<id>/download' (404 im Live-Check),
    sondern über properties.file.href aus den Dokument-Metadaten."""
    doc = {"properties": {"file": {"href": "/api/1/document/55/file/test.pdf"}}}
    monkeypatch.setattr(documents, "get", lambda endpoint: doc if endpoint == "document/55" else {})
    monkeypatch.setattr(
        documents,
        "get_bytes",
        lambda href: b"DATEN" if href == "/api/1/document/55/file/test.pdf" else b"",
    )
    assert documents.lade_dokument(55) == b"DATEN"


def test_lade_dokument_fehler_wenn_href_fehlt(monkeypatch):
    """lade_dokument wirft ValueError, wenn properties.file.href fehlt."""
    import pytest
    doc = {"properties": {"file": {}}}
    monkeypatch.setattr(documents, "get", lambda endpoint: doc if endpoint == "document/55" else {})

    with pytest.raises(ValueError, match="Kein Datei-href für Dokument 55"):
        documents.lade_dokument(55)


def test_alle_jahresordner_filtert_auf_jahreszahlen(monkeypatch):
    gruppen = {
        "documentgroup": {"objects": [1, 2, 3]},
        "documentgroup/1": {"properties": {"title": "2025"}},
        "documentgroup/2": {"properties": {"title": "Vorlagen"}},
        "documentgroup/3": {"properties": {"title": "2026"}},
    }
    monkeypatch.setattr(documents, "get", lambda endpoint: gruppen[endpoint])

    assert documents.alle_jahresordner() == [("2025", 1), ("2026", 3)]


def test_alle_dokumentordner_liefert_alle_gruppen(monkeypatch):
    gruppen = {
        "documentgroup": {"objects": [1, 2, 3]},
        "documentgroup/1": {"properties": {"title": "2025"}},
        "documentgroup/2": {"properties": {"title": "Satzungen"}},
        "documentgroup/3": {"properties": {"title": "2026"}},
    }
    monkeypatch.setattr(documents, "get", lambda endpoint: gruppen[endpoint])

    assert documents.alle_dokumentordner() == [("2025", 1), ("2026", 3), ("Satzungen", 2)]
