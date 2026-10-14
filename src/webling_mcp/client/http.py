"""
Webling-API: Basis-HTTP-Schicht — bewusst NUR GET.

Schreiboperationen existieren in diesem Package nicht (read-only by design,
zusätzlich abgesichert durch einen API-Key mit nur Lese-Rechten).

API-Doku: https://verein.webling.eu/api/1
"""

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

# .env liegt im Repo-Root — nicht vom Arbeitsverzeichnis des MCP-Hosts abhängen
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

logger = logging.getLogger(__name__)


class WeblingKonfigFehler(RuntimeError):
    """Webling-Zugangsdaten fehlen oder sind unvollständig."""


def _konfiguration() -> tuple[str, str]:
    """Liest Base-URL und API-Key aus der Umgebung (zur Laufzeit, nicht beim Import)."""
    base_url = os.environ.get("WEBLING_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("WEBLING_MCP_API_KEY", "")
    if not base_url or not api_key:
        raise WeblingKonfigFehler(
            "WEBLING_BASE_URL und WEBLING_MCP_API_KEY müssen in der .env gesetzt sein."
        )
    return base_url, api_key


def pruefe_konfiguration() -> None:
    """Prüft beim Serverstart, ob die Zugangsdaten vollständig sind."""
    _konfiguration()


def get(endpoint: str, params: dict | None = None) -> dict | list:
    """GET-Request an die Webling-API, gibt geparstes JSON zurück."""
    base_url, api_key = _konfiguration()
    url = f"{base_url}/{endpoint}"
    response = requests.get(
        url,
        headers={"apikey": api_key, "Content-Type": "application/json"},
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_bytes(endpoint: str) -> bytes:
    """GET-Request an die Webling-API, gibt rohe Bytes zurück (Dokument-Download).

    `endpoint` ist entweder ein relativer API-Pfad (z.B. 'document/55/download')
    oder ein absoluter Server-Pfad aus einem href-Feld der Webling-Antwort
    (z.B. '/api/1/document/55/file/name.pdf'). Absolute Pfade gehen direkt an den
    Server-Host — nicht an base_url + endpoint, sonst dupliziert sich '/api/1'.
    """
    base_url, api_key = _konfiguration()
    if endpoint.startswith("/"):
        server = urlparse(base_url)
        url = f"{server.scheme}://{server.netloc}{endpoint}"
    else:
        url = f"{base_url}/{endpoint}"
    response = requests.get(url, headers={"apikey": api_key}, timeout=60)
    response.raise_for_status()
    return response.content
