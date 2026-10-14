"""FastAPI-Routen: Login, Schutz, Status, Chat-Stream (Phase C)."""
import logging
import threading
import time

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from webling_chat import app as app_modul
from webling_chat import auth


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBLING_CHAT_DATEN_DIR", str(tmp_path))
    monkeypatch.setenv("WEBLING_CHAT_COOKIE_SECURE", "0")
    con = auth.oeffne_db()
    auth.lege_nutzer_an(con, "phil", "geheim-und-lang")
    con.close()
    # Webling/Anthropic nicht anfassen: Kontext + Chat mocken
    monkeypatch.setattr(app_modul, "_kontext", lambda: (
        _FakeVormask(), _FakeRuecks()))
    monkeypatch.setattr(app_modul.chat, "antworte",
                        lambda client, verlauf, frage, werkzeuge, status_cb=None:
                        f"Antwort auf: {frage}")
    app_modul._login_limit = auth.LoginLimit()      # frisches Limit pro Test
    app_modul._verlaeufe.clear()
    app_modul._sitzung_sperren.clear()
    return TestClient(app_modul.app)


class _FakeVormask:
    def maskiere(self, text):
        return text.replace("Timo Testmann", "M-1")


class _FakeRuecks:
    def ersetze(self, text):
        return text.replace("M-1", "Timo Testmann")


def _login(client):
    r = client.post("/api/login",
                    json={"benutzername": "phil", "passwort": "geheim-und-lang"})
    assert r.status_code == 200
    return r


def test_ohne_login_redirect_und_401(client):
    assert client.get("/", follow_redirects=False).status_code == 307
    assert client.get("/api/status").status_code == 401
    assert client.post("/api/chat", json={"nachricht": "x"}).status_code == 401


def test_login_falsches_passwort(client):
    r = client.post("/api/login",
                    json={"benutzername": "phil", "passwort": "falsch"})
    assert r.status_code == 401


def test_login_log_enthaelt_keine_identifizierenden_daten(client, caplog):
    with caplog.at_level(logging.WARNING, logger="webling_chat.app"):
        client.post("/api/login",
                    json={"benutzername": "phil", "passwort": "falsch"})
    assert "phil" not in caplog.text
    assert "testclient" not in caplog.text


def test_login_rate_limit(client):
    for _ in range(5):
        client.post("/api/login", json={"benutzername": "phil", "passwort": "falsch"})
    r = client.post("/api/login",
                    json={"benutzername": "phil", "passwort": "geheim-und-lang"})
    assert r.status_code == 429


def test_login_und_status(client):
    _login(client)
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["benutzer"] == "phil"


def test_status_zeigt_letzten_ingest_lauf(client, tmp_index):
    """Nicht das Dateidatum des Index: das bleibt stehen, solange sich in Webling
    nichts ändert, und ein aktueller Index sähe tagealt aus."""
    from webling_mcp.rag import index as rag

    con = rag.oeffne_db()
    rag.setze_meta(con, "letzter_ingest", "2026-07-21T12:04:00")
    con.close()
    _login(client)

    assert client.get("/api/status").json()["index_vom"] == "21.07.2026"


def test_status_ohne_ingest_vermerk(client, tmp_index):
    _login(client)
    assert client.get("/api/status").json()["index_vom"] is None


def test_logout(client):
    _login(client)
    client.post("/api/logout")
    assert client.get("/api/status").status_code == 401


def test_chat_stream_mit_ruecksubstitution(client):
    _login(client)
    r = client.post("/api/chat", json={"nachricht": "Wo ist Timo Testmann?"})
    assert r.status_code == 200
    körper = r.text
    # Vormaskierung lief (Frage ging als M-1 rein), Rücksubstitution lief (Anzeige M-1 -> Name)
    assert "event: antwort" in körper
    assert "Timo Testmann" in körper
    assert "event: ende" in körper


# --- Fehlermeldungen ----------------------------------------------------------

def _antwort(status):
    return httpx.Response(status,
                          request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def test_chat_meldet_konfigurationsfehler_als_dauerhaft(client, monkeypatch):
    """Leere Credits oder ein falscher Key sind Dauerzustände — 'gleich nochmal'
    würde ein Vorstandsmitglied endlos wiederholen lassen, statt zu melden."""
    def kaputt(*args, **kwargs):
        raise anthropic.BadRequestError(
            "Your credit balance is too low to access the Anthropic API.",
            response=_antwort(400), body=None)

    monkeypatch.setattr(app_modul.chat, "antworte", kaputt)
    _login(client)

    körper = client.post("/api/chat", json={"nachricht": "x"}).text

    assert "event: fehler" in körper
    assert "gleich nochmal" not in körper
    assert "Admin" in körper
    assert "credit balance" not in körper      # keine API-Interna an den Browser


def test_chat_meldet_stoerung_als_voruebergehend(client, monkeypatch):
    def kaputt(*args, **kwargs):
        raise anthropic.APIConnectionError(
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))

    monkeypatch.setattr(app_modul.chat, "antworte", kaputt)
    _login(client)

    körper = client.post("/api/chat", json={"nachricht": "x"}).text

    assert "event: fehler" in körper
    assert "gleich nochmal" in körper


def test_fehlerlog_enthaelt_keine_api_meldung(client, monkeypatch, caplog):
    def kaputt(*args, **kwargs):
        raise anthropic.BadRequestError("credit balance too low",
                                        response=_antwort(400), body=None)

    monkeypatch.setattr(app_modul.chat, "antworte", kaputt)
    _login(client)
    with caplog.at_level(logging.ERROR, logger="webling_chat.app"):
        client.post("/api/chat", json={"nachricht": "x"})

    assert "credit balance" not in caplog.text


# --- Verlaufsverwaltung -------------------------------------------------------

def _turn(nummer):
    """Ein vollständiger Turn: Frage, tool_use, tool_result, Antwort."""
    return [
        {"role": "user", "content": f"Frage {nummer}"},
        {"role": "assistant",
         "content": [{"type": "tool_use", "id": f"t{nummer}", "name": "x"}]},
        {"role": "user",
         "content": [{"type": "tool_result", "tool_use_id": f"t{nummer}"}]},
        {"role": "assistant", "content": f"Antwort {nummer}"},
    ]


def _tool_results_haben_ihr_tool_use(verlauf):
    """Jedes tool_result muss ein tool_use mit derselben id vor sich haben."""
    offene = set()
    for eintrag in verlauf:
        if not isinstance(eintrag["content"], list):
            continue
        for block in eintrag["content"]:
            if block.get("type") == "tool_use":
                offene.add(block["id"])
            elif block.get("type") == "tool_result":
                if block["tool_use_id"] not in offene:
                    return False
    return True


def test_kappe_verlauf_laesst_kurzen_verlauf_unberuehrt(monkeypatch):
    monkeypatch.setattr(app_modul, "MAX_VERLAUF_TURNS", 5)
    verlauf = _turn(0) + _turn(1)
    vorher = list(verlauf)

    app_modul._kappe_verlauf(verlauf)

    assert verlauf == vorher


def test_kappe_verlauf_schneidet_nur_an_turn_grenzen(monkeypatch):
    """Ein Schnitt mitten in einem Turn ließe ein tool_result ohne sein
    tool_use zurück — die Anthropic-API lehnt so einen Verlauf mit 400 ab."""
    monkeypatch.setattr(app_modul, "MAX_VERLAUF_TURNS", 2)
    verlauf = [eintrag for nummer in range(4) for eintrag in _turn(nummer)]

    app_modul._kappe_verlauf(verlauf)

    assert verlauf[0] == {"role": "user", "content": "Frage 2"}
    assert len(verlauf) == 8                      # genau die letzten zwei Turns
    assert _tool_results_haben_ihr_tool_use(verlauf)


def test_pruning_entfernt_verlaeufe_abgelaufener_sessions(client):
    _login(client)
    client.post("/api/chat", json={"nachricht": "Hallo"})
    gueltige = set(app_modul._verlaeufe)
    assert gueltige                                # der eigene Verlauf existiert
    app_modul._verlaeufe["abgelaufen"] = [{"role": "user", "content": "alt"}]
    app_modul._sitzung_sperren["abgelaufen"] = threading.Lock()

    client.post("/api/chat", json={"nachricht": "Und noch was"})

    assert "abgelaufen" not in app_modul._verlaeufe
    assert "abgelaufen" not in app_modul._sitzung_sperren
    assert set(app_modul._verlaeufe) == gueltige   # gültige Session bleibt


def test_parallele_chats_derselben_session_werden_serialisiert(client, monkeypatch):
    """Zwei gleichzeitige /api/chat-Requests derselben Session dürfen sich nicht
    verschränken. Sonst schiebt sich ein fremder Turn zwischen tool_use und
    tool_result, und die API lehnt die Session danach dauerhaft mit 400 ab."""
    laufend = []
    ueberlappungen = []

    def langsam(api, verlauf, frage, werkzeuge, status_cb=None):
        laufend.append(frage)
        if len(laufend) > 1:
            ueberlappungen.append(list(laufend))
        time.sleep(0.2)
        laufend.remove(frage)
        return f"Antwort auf: {frage}"

    monkeypatch.setattr(app_modul.chat, "antworte", langsam)
    _login(client)

    antworten = {}

    def frage_stellen(nummer):
        antworten[nummer] = client.post("/api/chat",
                                        json={"nachricht": f"Frage {nummer}"})

    threads = [threading.Thread(target=frage_stellen, args=(n,)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert [r.status_code for r in antworten.values()] == [200, 200]
    assert ueberlappungen == []
