"""
Lokale Embeddings (intfloat/multilingual-e5-small, 384 Dimensionen, CPU).

E5-Modelle VERLANGEN Präfixe: "passage: " beim Indexieren, "query: " bei
der Suche — ohne sie bricht die Trefferqualität ein. Query- und
Index-Embeddings müssen vom selben Modell stammen: Modellwechsel => Re-Ingest.
"""

import logging

logger = logging.getLogger(__name__)

MODELL_NAME = "intfloat/multilingual-e5-small"
DIMENSION = 384

_modell_cache = None


def _lade_modell():
    """Lädt das Modell lazy (einmal pro Prozess)."""
    global _modell_cache
    if _modell_cache is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Lade Embedding-Modell %s ...", MODELL_NAME)
        try:
            # Cache-only: spart mehrere Sekunden HuggingFace-Online-Checks
            # pro Prozessstart (Modell wurde beim Setup vorgeladen)
            _modell_cache = SentenceTransformer(MODELL_NAME, local_files_only=True)
        except Exception:
            logger.info("Modell nicht im Cache — lade von HuggingFace herunter ...")
            _modell_cache = SentenceTransformer(MODELL_NAME)
    return _modell_cache


def embed_passagen(texte: list[str]) -> list[list[float]]:
    """Vektorisiert Chunks fürs Indexieren (E5-Präfix 'passage: ')."""
    if not texte:
        return []
    vektoren = _lade_modell().encode(
        [f"passage: {t}" for t in texte], normalize_embeddings=True
    )
    return [[float(x) for x in v] for v in vektoren]


def embed_frage(frage: str) -> list[float]:
    """Vektorisiert eine Suchfrage (E5-Präfix 'query: ')."""
    vektoren = _lade_modell().encode(
        [f"query: {frage}"], normalize_embeddings=True
    )
    return [float(x) for x in vektoren[0]]
