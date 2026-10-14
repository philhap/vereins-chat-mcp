"""
webling-mcp: FastMCP-Server (stdio). Die Tool-Logik liegt in tools.py
(gemeinsam mit der Chat-Schleife aus webling_chat genutzt).
"""

import logging
import threading

from mcp.server.fastmcp import FastMCP

from webling_mcp import tools
from webling_mcp.client import documents, members  # noqa: F401 (Re-Export für Tests)
from webling_mcp.client.http import WeblingKonfigFehler, pruefe_konfiguration
from webling_mcp.rag import index as rag_index

# Rückwärtskompatible Re-Exporte (bestehende Tests importieren aus server)
from webling_mcp.tools import (  # noqa: F401
    _sicher, baue_beitraege, baue_jubilaeen, baue_lies_dokument, baue_list_groups,
    baue_list_members, baue_mannschaften, baue_statistik, baue_suche_dokumente,
    get_member, list_documents,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("webling-mcp")
for _fn in tools.WERKZEUGE.values():
    mcp.tool()(_fn)


def _waerme_suche_vor() -> None:
    """Lädt das Embedding-Modell im Hintergrund vor, damit die erste
    suche_dokumente-Anfrage nicht ~10 s auf torch + Modell warten muss."""
    try:
        from webling_mcp.rag import embeddings

        embeddings._lade_modell()
        logger.info("Embedding-Modell vorgewärmt.")
    except Exception as e:
        logger.warning("Vorwärmen fehlgeschlagen (%s) — erste Suche lädt lazy.",
                       type(e).__name__)


def main() -> None:
    """Serverstart mit Konfigurationsprüfung (klare Meldung statt spätem Tool-Fehler)."""
    logging.basicConfig(level=logging.INFO)
    try:
        pruefe_konfiguration()
    except WeblingKonfigFehler as e:
        raise SystemExit(f"Konfigurationsfehler: {e}")
    if rag_index.db_datei().exists():
        threading.Thread(target=_waerme_suche_vor, daemon=True).start()
    mcp.run()


if __name__ == "__main__":
    main()
