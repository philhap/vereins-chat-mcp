"""
Manueller Extraktionscheck gegen echte Webling-Dokumente (braucht .env).

Gibt pro Dokument nur Dateiname, Extraktionsstatus und Zeichenzahl aus —
die ersten 300 Zeichen NUR auf ausdrückliche Anforderung (--zeige-text),
da echte Dokumente Klarnamen enthalten (bleibt lokal im Terminal).
"""

import sys

from webling_mcp.client import documents
from webling_mcp.rag.extraktion import extrahiere_text

zeige_text = "--zeige-text" in sys.argv

for jahr, ordner_id in documents.alle_jahresordner():
    for doku in documents.liste_dokumente(ordner_id):
        daten = documents.lade_dokument(doku["id"])
        text = extrahiere_text(doku["name"], daten)
        status = f"{len(text)} Zeichen" if text else "NICHT EXTRAHIERBAR"
        print(f"[{jahr}] {doku['name']}: {status}")
        if text and zeige_text:
            print("   " + text[:300].replace("\n", " ") + "\n")
