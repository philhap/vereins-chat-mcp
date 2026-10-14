"""
Tool-Use-Schleife gegen die Anthropic-API (manuelle Schleife, kein Beta-Runner).

Das Modell sieht ausschließlich Pseudonyme: die Frage ist vormaskiert, die
Tool-Antworten sind konstruktionsbedingt pseudonym (tools.py). Der Verlauf
bleibt serverseitig und pseudonym — es existiert kein Pfad, über den ein
Klarname Richtung API wandern kann.

Modell: claude-sonnet-5 — adaptives Thinking ist dort standardmäßig aktiv;
KEINE temperature/top_p/thinking-Parameter setzen (400).
"""

import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

MODELL = os.environ.get("WEBLING_CHAT_MODELL", "claude-sonnet-5")
MAX_TOKENS = 4096
MAX_RUNDEN = 8

SYSTEM_PROMPT = """\
Du bist der Assistent des Vereins und beantwortest Fragen
des Vorstands zu Mitgliedern, Beiträgen, Jubiläen, Mannschaften und
Vereinsdokumenten.

Regeln:
- Personen erscheinen als Pseudonyme (z.B. M-123 oder P-45-1). Verwende diese
  Pseudonyme in deiner Antwort exakt unverändert — sie werden dem Nutzer
  automatisch als echte Namen angezeigt. Erfinde niemals Namen.
- Sprich die Pseudonyme nicht als solche an: beschrifte Spalten mit "Name",
  nicht mit "Pseudonym", und verweise den Nutzer nie auf lokale Dateien oder
  Mapping-Listen, um Namen aufzulösen. Er sieht die echten Namen bereits.
- Nutze für alle Fakten die Tools; rate nicht.
- Meldet ein Tool unter "datenqualitaet" eine Lücke (gepflegt < gesamt), sage
  das dazu. Ein fehlender Wert heißt "in Webling nicht eingetragen", nicht
  "trifft nicht zu" — bei Fragen nach ältesten, längsten oder ersten Einträgen
  ist eine Antwort ohne diesen Hinweis schlicht falsch.
- Antworte auf Deutsch, knapp und konkret.
- Meldet ein Tool einen Fehler, gib die Meldung verständlich wieder.

Mitglieder-Status & Beitrag:
- `status` ist die Mitgliedskategorie. Bedeutung und Jahresbeitrag:
{legende}
- `mitgliedsbeitrag` ist der aus `status` abgeleitete Jahresbeitrag in Euro.
- Nicht verwechseln mit `beitragsstatus` — das ist das Jahr, bis zu dem
  bezahlt wurde, nicht die Kategorie.

Heute ist {heute}. Beziehe "dieses Jahr", "letzte Saison" und ähnliche Angaben
immer auf dieses Datum. Rate niemals eine Jahreszahl — lässt du den Parameter
weg, setzen die Tools von sich aus das laufende Jahr ein.
"""

WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag")

# Schlüssel, die nur für den MCP-Zugang (Claude Code) gelten: dort löst der
# Nutzer Pseudonyme über lokale Dateien auf. Im Chat werden Klarnamen direkt
# angezeigt — der Hinweis wäre falsch, und das Modell gibt ihn wörtlich weiter.
# Der Pfad enthält zudem den Benutzernamen und hat an der API nichts verloren.
NUR_FUER_MCP = ("namensliste_lokal", "hinweis")

from webling_mcp import domain, tools  # noqa: E402  (nach Konstanten, wie im Projekt üblich)


def _fuer_chat(ergebnis):
    """Entfernt die MCP-spezifischen Hinweisfelder aus einer Tool-Antwort."""
    if isinstance(ergebnis, dict):
        return {k: v for k, v in ergebnis.items() if k not in NUR_FUER_MCP}
    return ergebnis


def _heute() -> str:
    """Indirektion, damit Tests die Uhr ersetzen können. Wochentage fest
    verdrahtet — Locale-Namen sind auf Windows und Linux nicht verlässlich."""
    heute = date.today()
    return f"{WOCHENTAGE[heute.weekday()]}, {heute.strftime('%d.%m.%Y')}"


def antworte(client, verlauf: list, frage_maskiert: str,
             werkzeuge: list[dict], status_cb=None) -> str:
    """Führt eine Chat-Runde aus; mutiert `verlauf` (pseudonymisierter Verlauf)."""
    erlaubte_namen = {t["name"] for t in werkzeuge}
    verlauf.append({"role": "user", "content": frage_maskiert})

    for _ in range(MAX_RUNDEN):
        antwort = client.messages.create(
            model=MODELL, max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT.format(heute=_heute(), legende=domain.status_legende()),
            tools=werkzeuge, messages=list(verlauf))
        verlauf.append({"role": "assistant", "content": antwort.content})

        if antwort.stop_reason != "tool_use":
            return "".join(b.text for b in antwort.content if b.type == "text")

        ergebnisse = []
        for block in antwort.content:
            if block.type != "tool_use":
                continue
            if block.name not in erlaubte_namen:
                inhalt = f"Tool {block.name!r} ist für diese Rolle nicht erlaubt."
            else:
                if status_cb:
                    status_cb(block.name)
                inhalt = json.dumps(
                    _fuer_chat(tools.fuehre_aus(block.name, dict(block.input))),
                    ensure_ascii=False)
            ergebnisse.append({"type": "tool_result",
                               "tool_use_id": block.id, "content": inhalt})
        verlauf.append({"role": "user", "content": ergebnisse})

    logger.warning("Chat-Runde nach %d Tool-Runden abgebrochen", MAX_RUNDEN)
    return "Die Anfrage wurde nach zu vielen Tool-Schritten abgebrochen — bitte konkreter fragen."
