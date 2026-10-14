"""
FastAPI-App: Chat-PWA mit Login. Klarnamen existieren nur zwischen diesem
Server und dem Browser — die Anthropic-API sieht ausschließlich Pseudonyme
(Vormaskierung am Eingang, Rücksubstitution am Ausgang, Verlauf serverseitig).
"""

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from webling_chat import auth, chat, policy
from webling_chat.ruecksubstitution import Ruecksubstituierer
from webling_chat.vormaskierung import Vormaskierer
from webling_mcp.client import members
from webling_mcp.rag import index as rag_index
from webling_mcp.rag.ingest import lade_pseudonym_mapping

load_dotenv()
logger = logging.getLogger(__name__)

# Auto-Doku abgeschaltet: /docs, /redoc und /openapi.json waeren oeffentlich
# erreichbar (vor dem Login) und legen die Routen offen. Keine Mitgliederdaten
# darin, aber Angriffsflaeche ohne Nutzen — die PWA braucht sie nicht.
app = FastAPI(title="webling-chat", docs_url=None, redoc_url=None, openapi_url=None)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_login_limit = auth.LoginLimit()
_verlaeufe: dict[str, list] = {}          # Session-Token -> pseudonymer Verlauf
_verlaeufe_lock = threading.Lock()
_sitzung_sperren: dict[str, threading.Lock] = {}  # Session-Token -> Lock für eine ganze Chat-Runde
_anthropic = None
_kontext_cache: tuple[float, tuple] | None = None
KONTEXT_TTL_S = 6 * 3600
# Verlauf vor jedem API-Aufruf auf die letzten N User-Turns kappen (Tokenkosten
# + irgendwann "prompt too long"-400 über die 30-Tage-Gleitsession hinweg).
MAX_VERLAUF_TURNS = 40


def _anthropic_client():
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.Anthropic()      # liest ANTHROPIC_API_KEY
    return _anthropic


def _kontext() -> tuple[Vormaskierer, Ruecksubstituierer]:
    """Mitglieder + Mapping laden, 6 h gecacht (Webling nicht pro Nachricht fragen)."""
    global _kontext_cache
    if _kontext_cache and time.monotonic() - _kontext_cache[0] < KONTEXT_TTL_S:
        return _kontext_cache[1]
    mitglieder = members.hole_alle_mitglieder()
    mapping = lade_pseudonym_mapping()
    paar = (Vormaskierer(mitglieder, mapping),
            Ruecksubstituierer(mitglieder, mapping))
    _kontext_cache = (time.monotonic(), paar)
    return paar


def _cookie_secure() -> bool:
    return os.environ.get("WEBLING_CHAT_COOKIE_SECURE", "1") != "0"


def aktueller_nutzer(sitzung: str | None = Cookie(default=None)) -> dict:
    if not sitzung:
        raise HTTPException(status_code=401, detail="Nicht angemeldet")
    con = auth.oeffne_db()
    try:
        nutzer = auth.hole_session(con, sitzung)
    finally:
        con.close()
    if nutzer is None:
        raise HTTPException(status_code=401, detail="Sitzung abgelaufen")
    return nutzer


class LoginDaten(BaseModel):
    benutzername: str
    passwort: str


class ChatAnfrage(BaseModel):
    nachricht: str


def _sitzung_sperre(sitzung: str) -> threading.Lock:
    """Pro Session ein Lock, das lauf() für die gesamte Chat-Runde hält.
    Ohne das würden zwei parallele /api/chat-Requests derselben Session
    dieselbe Verlaufsliste ungeschützt mutieren — verschränkt sich dabei ein
    tool_use-Turn mit einem fremden Turn vor seinem tool_result, lehnt die
    Anthropic-API jeden weiteren Request der Session mit 400 ab (bis Logout)."""
    with _verlaeufe_lock:
        return _sitzung_sperren.setdefault(sitzung, threading.Lock())


def _kappe_verlauf(verlauf: list) -> None:
    """Kappt den Verlauf in-place auf die letzten MAX_VERLAUF_TURNS echten
    User-Turns. Geschnitten wird ausschließlich an Turn-Grenzen: ein echter
    User-Turn hat reinen Text-Content (role=user, content=str). tool_use/
    tool_result-Paare (role=user mit Listen-Content) hängen an ihrem Turn und
    werden nie getrennt."""
    grenzen = [i for i, eintrag in enumerate(verlauf)
               if eintrag["role"] == "user" and isinstance(eintrag["content"], str)]
    if len(grenzen) > MAX_VERLAUF_TURNS:
        del verlauf[:grenzen[-MAX_VERLAUF_TURNS]]


def _pruning_verlaeufe() -> None:
    """Gelegenheitsbereinigung bei jedem Chat-Zugriff: entfernt Verläufe (und
    ihre Locks), deren Session laut auth.hole_session nicht mehr gültig ist.
    Kein Hintergrund-Thread nötig — die Gelegenheit reicht."""
    with _verlaeufe_lock:
        tokens = list(_verlaeufe.keys())
    if not tokens:
        return
    con = auth.oeffne_db()
    try:
        ungueltig = [t for t in tokens if auth.hole_session(con, t) is None]
    finally:
        con.close()
    if ungueltig:
        with _verlaeufe_lock:
            for token in ungueltig:
                _verlaeufe.pop(token, None)
                _sitzung_sperren.pop(token, None)


@app.get("/")
def startseite(sitzung: str | None = Cookie(default=None)):
    if sitzung:
        con = auth.oeffne_db()
        try:
            if auth.hole_session(con, sitzung):
                return FileResponse(STATIC / "index.html")
        finally:
            con.close()
    return RedirectResponse("/login")


@app.get("/login")
def login_seite():
    return FileResponse(STATIC / "login.html")


@app.post("/api/login")
def api_login(daten: LoginDaten, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if not _login_limit.erlaubt(ip):
        raise HTTPException(status_code=429, detail="Zu viele Versuche — 15 Minuten warten")
    con = auth.oeffne_db()
    try:
        nutzer = auth.pruefe_login(con, daten.benutzername, daten.passwort)
        if nutzer is None:
            _login_limit.fehlversuch(ip)
            logger.warning("Fehlgeschlagener Login")
            raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch")
        _login_limit.erfolg(ip)
        token = auth.erstelle_session(con, nutzer["id"])
    finally:
        con.close()
    response.set_cookie("sitzung", token, httponly=True, secure=_cookie_secure(),
                        samesite="lax", max_age=int(auth.SESSION_DAUER.total_seconds()))
    return {"ok": True}


@app.post("/api/logout")
def api_logout(response: Response, sitzung: str | None = Cookie(default=None)):
    if sitzung:
        con = auth.oeffne_db()
        try:
            auth.loesche_session(con, sitzung)
        finally:
            con.close()
        with _verlaeufe_lock:
            _verlaeufe.pop(sitzung, None)
            _sitzung_sperren.pop(sitzung, None)
    response.delete_cookie("sitzung")
    return {"ok": True}


def _index_stand() -> str | None:
    """Datum des letzten abgeschlossenen Ingest-Laufs. Bewusst NICHT das
    Änderungsdatum der Index-Datei: die bleibt stehen, solange sich in Webling
    nichts ändert — ein aktueller Index sähe dann tagealt aus."""
    if not rag_index.db_datei().exists():
        return None
    con = rag_index.oeffne_db()
    try:
        vermerk = rag_index.hole_meta(con, "letzter_ingest")
    finally:
        con.close()
    if not vermerk:
        return None
    try:
        return datetime.fromisoformat(vermerk).strftime("%d.%m.%Y")
    except ValueError:
        logger.warning("Unlesbarer Ingest-Vermerk im Index")
        return None


@app.get("/api/status")
def api_status(nutzer: dict = Depends(aktueller_nutzer)):
    return {"benutzer": nutzer["benutzername"], "index_vom": _index_stand()}


@app.post("/api/chat")
def api_chat(anfrage: ChatAnfrage,
             nutzer: dict = Depends(aktueller_nutzer),
             sitzung: str = Cookie(default=None)):
    vormask, ruecks = _kontext()
    werkzeuge = policy.erlaubte_tools(nutzer["rolle"])
    frage = vormask.maskiere(anfrage.nachricht)
    _pruning_verlaeufe()
    sperre = _sitzung_sperre(sitzung)

    q: queue.Queue = queue.Queue()

    def lauf():
        with sperre:
            with _verlaeufe_lock:
                verlauf = _verlaeufe.setdefault(sitzung, [])
            _kappe_verlauf(verlauf)
            try:
                text = chat.antworte(_anthropic_client(), verlauf, frage, werkzeuge,
                                     status_cb=lambda name: q.put(("werkzeug", name)))
                q.put(("antwort", ruecks.ersetze(text)))
            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                    anthropic.BadRequestError) as e:
                # Dauerzustand (leeres Guthaben, falscher/abgelaufener Key,
                # ungültiger Request). Wiederholen hilft nie — wer davorsitzt,
                # muss den Admin holen statt zehnmal zu klicken.
                logger.error("Anthropic-Konfigurationsfehler: %s", type(e).__name__)
                q.put(("fehler", "Der Zugang zu Claude ist gerade nicht nutzbar — "
                                 "bitte beim Admin melden."))
            except anthropic.APIError as e:
                logger.error("Anthropic-Fehler: %s", type(e).__name__)
                q.put(("fehler", "Claude ist gerade nicht erreichbar — bitte gleich nochmal."))
            except Exception as e:
                logger.error("Chat-Fehler: %s", type(e).__name__)
                q.put(("fehler", f"Interner Fehler ({type(e).__name__})."))
            finally:
                q.put(("ende", ""))

    threading.Thread(target=lauf, daemon=True).start()

    def ereignisse():
        while True:
            art, daten = q.get()
            yield f"event: {art}\ndata: {json.dumps(daten, ensure_ascii=False)}\n\n"
            if art == "ende":
                return

    return StreamingResponse(ereignisse(), media_type="text/event-stream")
