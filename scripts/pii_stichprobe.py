"""
PII-Stichprobe am echten Index: prüft, dass kein Klarname aus dem
Pseudonym-Mapping im Index vorkommt.

Terminal-Ausgabe: NUR Zähler (darf den Rechner verlassen, z.B. Chat-Kontexte).
Details (welche Namen wo) gehen über privacy.schreibe_namensliste nach
output/pii_stichprobe.md — nur lokal.

Zwei Stufen:
- KRITISCH: voller Name ("Vorname Nachname") steht im Index -> echtes Leak.
- PRÜFEN: Nachname als eigenständiges Wort -> kann Leak ODER normales
  Wort/Ortsname sein (z.B. "Sommer", "Berg") — manuell bewerten.
"""

import re
import sqlite3

from webling_mcp import privacy
from webling_mcp.rag.index import db_datei
from webling_mcp.rag.maskierung import _namensmuster

mapping_pfad = privacy.OUTPUT_DIR / "pseudonym_mapping.md"
vollnamen: set[str] = set()
# Nach Herkunft getrennt: Mitglieder-Nachnamen sind meist Familiennamen
# (mehrdeutig, by design unmaskiert), Span-Endwörter oft NER-Rauschen.
nachnamen_mitglieder: set[str] = set()
endwoerter_spans: set[str] = set()
for zeile in mapping_pfad.read_text(encoding="utf-8").splitlines():
    m = re.match(r"^- (\S+) = (.+)$", zeile)
    if not m:
        continue
    klarname = m.group(2).strip()
    vollnamen.add(klarname)
    teile = klarname.replace(",", " ").split()
    if len(teile) >= 2:
        ziel = (nachnamen_mitglieder if m.group(1).startswith("M-")
                else endwoerter_spans)
        ziel.add(teile[-1])
endwoerter_spans -= nachnamen_mitglieder

con = sqlite3.connect(db_datei())
texte = [z[0] for z in con.execute("SELECT volltext FROM dokumente")]
texte += [z[0] for z in con.execute("SELECT text FROM chunks")]

def fundstellen(begriff: str) -> int:
    # Gleicher flexibler Whitespace-Match wie die Maskierung — sonst wären
    # Namen mit Zeilenumbruch ("Anna\nMeier") der blinde Fleck der Stichprobe.
    muster = _namensmuster(begriff, re.IGNORECASE)
    return sum(1 for t in texte if muster.search(t))

kritisch = {n: fundstellen(n) for n in sorted(vollnamen)}
kritisch = {n: c for n, c in kritisch.items() if c}
pruefen_mitglieder = {n: fundstellen(n)
                      for n in sorted(nachnamen_mitglieder) if len(n) >= 4}
pruefen_mitglieder = {n: c for n, c in pruefen_mitglieder.items() if c}
pruefen_spans = {n: fundstellen(n) for n in sorted(endwoerter_spans) if len(n) >= 4}
pruefen_spans = {n: c for n, c in pruefen_spans.items() if c}

zeilen = ["## KRITISCH — voller Name im Index (echtes Leak)", ""]
zeilen += [f"- {n} ({c} Texte)" for n, c in kritisch.items()] or ["(keine)"]
zeilen += ["", "## PRÜFEN — Mitglieder-Nachname als Wort", "",
           "Mehrere Träger im Verein = Familienname, bleibt by design stehen.", ""]
zeilen += [f"- {n} ({c} Texte)" for n, c in pruefen_mitglieder.items()] or ["(keine)"]
zeilen += ["", "## PRÜFEN — Endwort eines NER-Spans (oft harmlos)", "",
           "Letztes Wort eines erkannten Fremd-Namens; einzeln meist normales Wort.", ""]
zeilen += [f"- {n} ({c} Texte)" for n, c in pruefen_spans.items()] or ["(keine)"]
pfad = privacy.schreibe_namensliste("pii_stichprobe.md", "PII-Stichprobe", zeilen)

print(f"Index: {len(texte)} Texte (Volltexte + Chunks)")
print(f"KRITISCH (voller Name gefunden): {len(kritisch)}")
print(f"PRÜFEN Mitglieder-Nachname: {len(pruefen_mitglieder)}")
print(f"PRÜFEN Span-Endwort: {len(pruefen_spans)}")
print(f"Details (nur lokal): {pfad}")
