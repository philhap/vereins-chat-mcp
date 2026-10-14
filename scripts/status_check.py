"""
Manueller read-only Status-Check gegen die echte Webling-API (braucht .env).
Deckt Mitglieder auf, deren Alter nicht zur Status-Kategorie passt.

Konsole: NUR Pseudonyme (M-<id>), keine Namen.
Namen der Ausreißer: NUR lokal in output/status_pruefung.md.
Vorbild: scripts/live_check.py.
"""

import logging
from datetime import date

from webling_mcp import domain, privacy
from webling_mcp.client import members
from webling_mcp.client.http import pruefe_konfiguration

logging.basicConfig(level=logging.INFO)

pruefe_konfiguration()
print("Konfiguration: OK")

jahr = date.today().year
mitglieder = members.hole_alle_mitglieder()
ausreisser = domain.status_widersprueche(mitglieder, jahr)

print(f"Mitglieder geprüft: {len(mitglieder)}")
print(f"Alter/Kategorie-Widersprüche: {len(ausreisser)}")
for a in ausreisser:
    print(f"  M-{a['id']}  Status={a['status']}  Alter={a['alter']}  -> {a['grund']}")

if ausreisser:
    nach_id = {m["id"]: m for m in mitglieder}
    zeilen = [
        f"- **{nach_id[a['id']]['vorname']} {nach_id[a['id']]['name']}** "
        f"(M-{a['id']}): Status {a['status']}, Alter {a['alter']} — {a['grund']}"
        for a in ausreisser
    ]
    pfad = privacy.schreibe_namensliste(
        "status_pruefung.md", f"Status-Prüfung {jahr}", zeilen)
    print(f"Namen der Ausreißer (nur lokal): {pfad}")
else:
    print("Keine Ausreißer — keine Namensdatei geschrieben.")

print("Status-Check abgeschlossen.")
