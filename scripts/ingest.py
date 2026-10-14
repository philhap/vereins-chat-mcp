"""Manueller Ingest: Webling-Dokumente in den lokalen Suchindex (braucht .env)."""

import logging

from webling_mcp.client.http import pruefe_konfiguration
from webling_mcp.rag import ingest

logging.basicConfig(level=logging.INFO)

pruefe_konfiguration()
ergebnis = ingest.synchronisiere()

print(f"Neu indexiert:  {ergebnis['neu']}")
print(f"Unverändert:    {ergebnis['unveraendert']}")
print(f"Entfernt:       {ergebnis['entfernt']}")
print(f"Nachmaskiert:   {ergebnis['nachmaskiert']}")
if ergebnis["uebersprungen"]:
    print("Nicht indexierbar (kein Extraktor / kein Text):")
    for name in ergebnis["uebersprungen"]:
        print(f"  - {name}")
if ergebnis["fehler"]:
    print("Download fehlgeschlagen (beim nächsten Ingest erneut versuchen):")
    for name in ergebnis["fehler"]:
        print(f"  - {name}")
if ergebnis["mapping_datei"]:
    print(f"Pseudonym-Mapping (nur lokal): {ergebnis['mapping_datei']}")
