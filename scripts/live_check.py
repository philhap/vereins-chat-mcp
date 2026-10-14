"""
Manueller Read-only-Check gegen die echte Webling-API (braucht .env).
Verifiziert: Konfiguration, Bulk-Abruf, Felder, Jahresordner.
Gibt bewusst KEINE Namen aus — nur Zähler und Strukturen.
"""

import logging

from webling_mcp.client import documents, members
from webling_mcp.client.http import pruefe_konfiguration

logging.basicConfig(level=logging.INFO)

pruefe_konfiguration()
print("Konfiguration: OK")

mitglieder = members.hole_alle_mitglieder()
print(f"Mitglieder geladen: {len(mitglieder)}")

mit_geburtstag = sum(1 for m in mitglieder if m["geburtsdatum"])
mit_mannschaft = sum(1 for m in mitglieder if m["mannschaft"])
print(f"davon mit Geburtsdatum: {mit_geburtstag}, mit Mannschaft: {mit_mannschaft}")

status_werte = sorted({m["beitragsstatus"] for m in mitglieder if m["beitragsstatus"]})
print(f"Beitragsstatus-Werte: {status_werte}")

ordner_id = documents.finde_jahresordner()
print(f"Jahresordner (aktuelles Jahr): {'gefunden, ID ' + str(ordner_id) if ordner_id else 'NICHT gefunden'}")
if ordner_id:
    dokumente = documents.liste_dokumente(ordner_id)
    print(f"Dokumente im Jahresordner: {len(dokumente)}")
    if dokumente:
        erstes = dokumente[0]
        daten = documents.lade_dokument(erstes["id"])
        print(f"Download OK: Dokument-ID {erstes['id']}, {len(daten)} Bytes, Signatur {daten[:5]!r}")

alle = documents.alle_jahresordner()
print(f"Jahresordner gesamt: {[j for j, _ in alle]}")

print("Live-Check abgeschlossen.")
