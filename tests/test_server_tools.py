"""Tests für Fehlerbehandlung und Tool-Verdrahtung."""

from webling_mcp import server


def test_sicher_gibt_ergebnis_durch():
    assert server._sicher(lambda: {"ok": True}) == {"ok": True}


def test_sicher_faengt_fehler_ohne_stacktrace():
    def kaputt():
        raise ValueError("interner Fehler mit Details")

    antwort = server._sicher(kaputt)

    assert "fehler" in antwort
    assert "ValueError" in antwort["fehler"]
    # Deutsche Meldung, kein Traceback-Objekt
    assert "Traceback" not in antwort["fehler"]


def test_get_member_parst_pseudonym(monkeypatch, mitglieder):
    monkeypatch.setattr(server.members, "hole_mitglied", lambda mid: mitglieder[0])

    antwort = server.get_member("M-101")

    assert antwort["id"] == "M-101"
    assert "vorname" not in antwort


def test_get_member_akzeptiert_nackte_id(monkeypatch, mitglieder):
    monkeypatch.setattr(server.members, "hole_mitglied", lambda mid: mitglieder[0])

    antwort = server.get_member("101")

    assert antwort["id"] == "M-101"


def test_get_member_unsinnige_id_gibt_fehler():
    antwort = server.get_member("quatsch")

    assert "fehler" in antwort


def test_list_documents_ordner_fehlt(monkeypatch):
    monkeypatch.setattr(server.documents, "finde_jahresordner", lambda jahr: None)

    antwort = server.list_documents("1999")

    assert "fehler" in antwort
    assert "1999" in antwort["fehler"]
