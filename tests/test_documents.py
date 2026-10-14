"""Tests für den Dokumente-Client (Jahresordner, Dokumentlisten)."""

from webling_mcp.client import documents


def _fake_webling(monkeypatch, antworten: dict):
    """Ersetzt documents.get durch ein Lookup in `antworten`."""

    def fake_get(endpoint, params=None):
        if endpoint in antworten:
            return antworten[endpoint]
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(documents, "get", fake_get)


def test_finde_jahresordner(monkeypatch):
    _fake_webling(monkeypatch, {
        "documentgroup": {"objects": [10, 20]},
        "documentgroup/10": {"properties": {"title": "Protokolle"}},
        "documentgroup/20": {"properties": {"title": "2026"}},
    })

    assert documents.finde_jahresordner("2026") == 20


def test_jahresordner_nicht_gefunden(monkeypatch):
    _fake_webling(monkeypatch, {
        "documentgroup": {"objects": [10]},
        "documentgroup/10": {"properties": {"title": "Protokolle"}},
    })

    assert documents.finde_jahresordner("1999") is None


def test_liste_dokumente(monkeypatch):
    _fake_webling(monkeypatch, {
        "documentgroup/20": {
            "properties": {"title": "2026"},
            "children": {"document": [301, 302]},
        },
        "document/301": {
            "properties": {"title": "Einladung_JHV_2026.pdf",
                           "file": {"name": "Einladung_JHV_2026.pdf", "size": 54321}},
        },
        "document/302": {
            "properties": {"title": "Satzung", "file": None},
        },
    })

    dokumente = documents.liste_dokumente(20)

    assert len(dokumente) == 2
    assert dokumente[0] == {"id": 301, "title": "Einladung_JHV_2026.pdf",
                            "name": "Einladung_JHV_2026.pdf", "size": 54321}
    # Dokument ohne Datei-Anhang crasht nicht
    assert dokumente[1]["name"] == ""
