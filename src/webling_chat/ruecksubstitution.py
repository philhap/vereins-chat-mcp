"""
Rücksubstitution: Pseudonyme in der fertigen LLM-Antwort -> Klarnamen.
Läuft ausschließlich am Ausgang Richtung Browser (TLS); die Anthropic-API
sieht diese Klarnamen nie.

M-<id> kommt aus den Webling-Stammdaten, P-<dok>-<n> aus dem Ingest-Mapping.
Unbekannte Pseudonyme bleiben unverändert stehen (kein Fehler).
"""

import re

REGEX_PSEUDONYM = re.compile(r"\b(M-\d+|P-\d+-\d+)\b")


class Ruecksubstituierer:
    def __init__(self, mitglieder: list[dict], fremd_mapping: dict[str, str]):
        self._namen = {
            f"M-{int(m['id'])}":
                f"{(m.get('vorname') or '').strip()} {(m.get('name') or '').strip()}".strip()
            for m in mitglieder
        }
        # Nur P-Pseudonyme aus der Datei; M-Einträge dort sind nur Doku
        self._namen.update({p: n for p, n in fremd_mapping.items() if p.startswith("P-")})

    def ersetze(self, text: str) -> str:
        return REGEX_PSEUDONYM.sub(
            lambda m: self._namen.get(m.group(1), m.group(1)), text)
