"""Tests für den Mitglieder-Client (Bulk-Abruf, Fallback, Normalisierung)."""

import requests

from webling_mcp.client import members


def _roh(vorname: str, **props) -> dict:
    """Baut eine rohe Webling-Member-Response."""
    eigenschaften = {
        "Vorname": vorname,
        "Name": "Musterfrau",
        "Geburtstag": "1961-03-15",
        "Beitritt": "2015-04-01",
        "Geschlecht": "w",
        "Mannschaft": "Damen",
        "Rang": 1,
        "Beitragsstatus": "2025",
    }
    eigenschaften.update(props)
    return {"type": "member", "properties": eigenschaften}


def test_bulk_abruf_nutzt_eine_anfrage(monkeypatch):
    aufrufe = []

    def fake_get(endpoint, params=None):
        aufrufe.append(endpoint)
        if endpoint == "member":
            return {"objects": [1, 2, 3]}
        if endpoint == "member/1,2,3":
            return [_roh("Anna"), _roh("Ben"), _roh("Cem")]
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)

    ergebnis = members.hole_alle_mitglieder()

    assert len(ergebnis) == 3
    assert ergebnis[0]["id"] == 1
    assert ergebnis[0]["vorname"] == "Anna"
    assert ergebnis[2]["id"] == 3
    # Genau 2 API-Calls: 1x ID-Liste + 1x Bulk (nicht 4)
    assert aufrufe == ["member", "member/1,2,3"]


def test_fallback_auf_einzelabrufe_bei_http_fehler(monkeypatch):
    def fake_get(endpoint, params=None):
        if endpoint == "member":
            return {"objects": [1, 2]}
        if endpoint == "member/1,2":
            raise requests.HTTPError("400 Bad Request")
        if endpoint == "member/1":
            return _roh("Anna")
        if endpoint == "member/2":
            return _roh("Ben")
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)

    ergebnis = members.hole_alle_mitglieder()

    assert [m["vorname"] for m in ergebnis] == ["Anna", "Ben"]


def test_normalisierung_fehlender_felder(monkeypatch):
    def fake_get(endpoint, params=None):
        if endpoint == "member":
            return {"objects": [7]}
        if endpoint == "member/7":
            return {"type": "member", "properties": {"Vorname": "Nur", "Name": "Vorname"}}
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)

    m = members.hole_alle_mitglieder()[0]

    assert m["id"] == 7
    assert m["geburtsdatum"] == ""
    assert m["beitrittsdatum"] == ""      # in Webling oft ungepflegt
    assert m["geschlecht"] == ""
    assert m["mannschaft"] == ""
    assert m["rang"] is None
    assert m["beitragsstatus"] == ""


def test_fallback_bei_unerwartetem_bulk_format(monkeypatch):
    """Liefert der Bulk-Endpoint ein Dict statt einer Liste, greifen Einzel-Abrufe."""
    aufrufe = []

    def fake_get(endpoint, params=None):
        aufrufe.append(endpoint)
        if endpoint == "member":
            return {"objects": [1, 2]}
        if endpoint == "member/1,2":
            return {"unerwartet": "dict statt liste"}
        if endpoint == "member/1":
            return _roh("Anna")
        if endpoint == "member/2":
            return _roh("Ben")
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)

    ergebnis = members.hole_alle_mitglieder()

    assert [m["vorname"] for m in ergebnis] == ["Anna", "Ben"]
    assert aufrufe == ["member", "member/1,2", "member/1", "member/2"]


def test_fallback_bei_nicht_passenden_bulk_ids(monkeypatch):
    """Tragen Bulk-Antworten fremde IDs, wird auf Einzel-Abrufe zurückgefallen."""
    aufrufe = []

    def fake_get(endpoint, params=None):
        aufrufe.append(endpoint)
        if endpoint == "member":
            return {"objects": [1, 2]}
        if endpoint == "member/1,2":
            # Gleiche Anzahl, aber vertauschte Reihenfolge -> IDs passen nicht
            return [dict(_roh("Ben"), id=2), dict(_roh("Anna"), id=1)]
        if endpoint == "member/1":
            return _roh("Anna")
        if endpoint == "member/2":
            return _roh("Ben")
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)

    ergebnis = members.hole_alle_mitglieder()

    assert [(m["id"], m["vorname"]) for m in ergebnis] == [(1, "Anna"), (2, "Ben")]
    assert aufrufe == ["member", "member/1,2", "member/1", "member/2"]


def test_rang_koerzion(monkeypatch):
    """rang muss int oder None sein: Floats werden konvertiert, Strings verworfen."""
    def fake_get(endpoint, params=None):
        if endpoint == "member":
            return {"objects": [1, 2]}
        if endpoint == "member/1,2":
            return [_roh("Anna", Rang=1.0), _roh("Ben", Rang="x")]
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)

    anna, ben = members.hole_alle_mitglieder()

    assert anna["rang"] == 1
    assert isinstance(anna["rang"], int)
    assert ben["rang"] is None


def test_hole_einzelnes_mitglied(monkeypatch):
    def fake_get(endpoint, params=None):
        assert endpoint == "member/42"
        return _roh("Erika")

    monkeypatch.setattr(members, "get", fake_get)

    m = members.hole_mitglied(42)

    assert m["id"] == 42
    assert m["vorname"] == "Erika"
    assert m["beitragsstatus"] == "2025"


def test_normalisierung_laedt_status(monkeypatch):
    def fake_get(endpoint, params=None):
        if endpoint == "member":
            return {"objects": [1]}
        if endpoint == "member/1":
            return _roh("Anna", Status="A-Mitglied")
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)
    assert members.hole_alle_mitglieder()[0]["status"] == "A-Mitglied"


def test_normalisierung_status_fehlt_ist_leer(monkeypatch):
    def fake_get(endpoint, params=None):
        if endpoint == "member":
            return {"objects": [7]}
        if endpoint == "member/7":
            return {"type": "member", "properties": {"Vorname": "Nur", "Name": "Vorname"}}
        raise AssertionError(f"Unerwarteter Endpoint: {endpoint}")

    monkeypatch.setattr(members, "get", fake_get)
    assert members.hole_alle_mitglieder()[0]["status"] == ""
