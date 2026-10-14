"""
Auth: Nutzer-Tabelle (Argon2id) + serverseitige Sessions (Zufallstoken in
SQLite, Cookie trägt nur das Token) + In-Memory-Rate-Limit für /login.

Kein Selbst-Registrieren — Nutzer werden per scripts/nutzer_anlegen.py angelegt.
Sessions sind gezielt widerrufbar (Zeile löschen = Gerät ausgesperrt).
"""

import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

SESSION_DAUER = timedelta(days=30)  # gleitend — am Handy nicht ständig neu tippen

_hasher = PasswordHasher()


def daten_dir() -> Path:
    """Datenverzeichnis (gitignored); Env-Override analog privacy.OUTPUT_DIR."""
    return Path(os.environ.get("WEBLING_CHAT_DATEN_DIR")
                or Path(__file__).resolve().parents[2] / "daten")


def oeffne_db() -> sqlite3.Connection:
    daten_dir().mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(daten_dir() / "chat.db")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS nutzer(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            benutzername TEXT NOT NULL UNIQUE,
            passwort_hash TEXT NOT NULL,
            rolle TEXT NOT NULL DEFAULT 'vorstand',
            aktiv INTEGER NOT NULL DEFAULT 1,
            erstellt_am TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
            token TEXT PRIMARY KEY,
            nutzer_id INTEGER NOT NULL,
            ablauf TEXT NOT NULL);
    """)
    return con


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def lege_nutzer_an(con: sqlite3.Connection, benutzername: str, passwort: str,
                   rolle: str = "vorstand") -> int:
    try:
        cur = con.execute(
            "INSERT INTO nutzer(benutzername, passwort_hash, rolle, erstellt_am) "
            "VALUES (?, ?, ?, ?)",
            (benutzername, _hasher.hash(passwort), rolle, _jetzt().isoformat()))
    except sqlite3.IntegrityError:
        raise ValueError(f"Benutzername {benutzername!r} existiert bereits")
    con.commit()
    return cur.lastrowid


def pruefe_login(con: sqlite3.Connection, benutzername: str, passwort: str) -> dict | None:
    zeile = con.execute(
        "SELECT id, passwort_hash, rolle FROM nutzer "
        "WHERE benutzername = ? AND aktiv = 1", (benutzername,)).fetchone()
    if zeile is None:
        return None
    nutzer_id, hash_, rolle = zeile
    try:
        _hasher.verify(hash_, passwort)
    except VerifyMismatchError:
        return None
    return {"id": nutzer_id, "benutzername": benutzername, "rolle": rolle}


def erstelle_session(con: sqlite3.Connection, nutzer_id: int) -> str:
    token = secrets.token_urlsafe(32)
    con.execute("INSERT INTO sessions(token, nutzer_id, ablauf) VALUES (?, ?, ?)",
                (token, nutzer_id, (_jetzt() + SESSION_DAUER).isoformat()))
    con.commit()
    return token


def hole_session(con: sqlite3.Connection, token: str) -> dict | None:
    zeile = con.execute(
        "SELECT s.nutzer_id, s.ablauf, n.benutzername, n.rolle "
        "FROM sessions s JOIN nutzer n ON n.id = s.nutzer_id "
        "WHERE s.token = ? AND n.aktiv = 1", (token,)).fetchone()
    if zeile is None:
        return None
    nutzer_id, ablauf, benutzername, rolle = zeile
    if datetime.fromisoformat(ablauf) < _jetzt():
        loesche_session(con, token)
        return None
    con.execute("UPDATE sessions SET ablauf = ? WHERE token = ?",
                ((_jetzt() + SESSION_DAUER).isoformat(), token))
    con.commit()
    return {"id": nutzer_id, "benutzername": benutzername, "rolle": rolle}


def loesche_session(con: sqlite3.Connection, token: str) -> None:
    con.execute("DELETE FROM sessions WHERE token = ?", (token,))
    con.commit()


class LoginLimit:
    """5 Fehlversuche pro 15 Minuten pro IP (in-memory, reicht für v1)."""

    def __init__(self, max_versuche: int = 5, fenster_s: int = 900):
        self._max = max_versuche
        self._fenster = fenster_s
        self._versuche: dict[str, list[float]] = {}

    def erlaubt(self, ip: str) -> bool:
        jetzt = time.monotonic()
        self._versuche[ip] = [t for t in self._versuche.get(ip, [])
                              if jetzt - t < self._fenster]
        return len(self._versuche[ip]) < self._max

    def fehlversuch(self, ip: str) -> None:
        self._versuche.setdefault(ip, []).append(time.monotonic())

    def erfolg(self, ip: str) -> None:
        self._versuche.pop(ip, None)
