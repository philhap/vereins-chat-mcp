"""
PII-Maskierung für den RAG-Index — die EINZIGE Stelle, die entscheidet,
was vom Dokumenttext LLM-sichtbar wird (analog privacy.py für Mitglieder).

Zweistufig (siehe Phase-B-Spec):
- Stufe 1 (deterministisch): bekannte Mitgliedernamen in allen Varianten
  -> M-<Webling-ID> (dieselben Pseudonyme wie die Phase-A-Tools).
- Stufe 2 (Sicherheitsnetz): spaCy-NER findet fremde Personennamen
  -> P-<Dokument-ID>-<lfd> (pro Dokument stabil). Einmal erkannte Namen
  werden dokumentübergreifend deterministisch maskiert (die NER erkennt
  denselben Namen nicht in jedem Dokument) — dafür sammelt erkenne_fremde()
  in einem Vorab-Pass, und bekannte_fremde seedet Namen aus früheren Läufen.
Zusätzlich Regex-Pässe für E-Mail, Telefon, IBAN.

Best-Effort: Spitznamen/Tippfehler/Umschreibungen werden nicht erkannt —
Restrisiko von Phil akzeptiert (Spec, Entscheidungstabelle). Ebenfalls
akzeptiert (Phil, 2026-07-18): einzelne Vornamen ohne Nachnamen (z.B.
"Anwesend: Timo, Jenny, ...") und mehrdeutige Nachnamen bleiben stehen.
"""

import logging
import re

logger = logging.getLogger(__name__)

REGEX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
REGEX_TELEFON = re.compile(r"(?<!\w)(?:\+49[\d /()\-]{6,}|0\d[\d /()\-]{5,})\d")
REGEX_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?\d{4}){3,7}(?: ?\d{1,3})?\b")
# Volle Geburtsdaten sind verboten (CLAUDE.md) — aber nur mit Geburts-Kontext
# maskieren, damit Sitzungs-/Beschlussdaten erhalten bleiben.
# Satzzeichen-tolerant: "Geburtstag? 12.03.1990" oder "geboren: am 12.03.1990"
# sind reale Chat-/Protokoll-Schreibweisen und dürfen nicht durchrutschen.
REGEX_GEBURTSDATUM = re.compile(
    r"(?i)(geboren|geb\.|geburtstag|geburtsdatum)\W{0,2}\s*(?:am\W{0,2}\s*)?"
    r"\d{1,2}\.\d{1,2}\.\d{2,4}"
)

_nlp_cache = None


def _namensmuster(begriff: str, flags: int = 0) -> re.Pattern:
    """Regex für einen Namen, bei dem zwischen den Wörtern beliebiger
    Whitespace stehen darf — PDF-Extraktion bricht Namen mitten in der
    Zeile um ("Anna\\nMeier")."""
    teile = [re.escape(w) for w in begriff.split()]
    return re.compile(r"\b" + r"\s+".join(teile) + r"\b", flags)


def _plausibler_name(kandidat: str) -> bool:
    """NER-Fund nur als Personenname werten, wenn er aus mind. zwei
    großgeschriebenen Wörtern besteht ("Hans Besucher"). Einzelwörter sind
    fast immer Fehlerkennungen (normale Substantive wie "Kassierer") und
    würden den Index unlesbar/unsuchbar machen (Entscheidung Phil, 2026-07-18)."""
    woerter = kandidat.split()
    return len(woerter) >= 2 and all(w[0].isupper() for w in woerter)


def _lade_nlp():
    """Lädt das deutsche spaCy-Modell lazy (einmal pro Prozess)."""
    global _nlp_cache
    if _nlp_cache is None:
        import spacy

        _nlp_cache = spacy.load("de_core_news_md")
    return _nlp_cache


def namensvarianten(vorname: str, name: str) -> list[str]:
    """Schreibvarianten eines Mitgliedsnamens, wie sie in Protokollen vorkommen."""
    v, n = (vorname or "").strip(), (name or "").strip()
    if not n:
        return []
    if not v:
        return [n]
    return [f"{v} {n}", f"{n}, {v}", f"{v[0]}. {n}"]


def mitglieder_ersetzungen(mitglieder: list[dict]) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Baut (Pseudonym->Klarname, [(Namensvariante, Pseudonym), ...]) für alle
    Mitglieder; Nachname allein nur bei vereinsweiter Eindeutigkeit.
    Längste Varianten zuerst, damit "Max Mustermann" vor "Mustermann" greift."""
    klarnamen: dict[str, str] = {}
    ersetzungen: list[tuple[str, str]] = []
    nachnamen = [(m.get("name") or "").strip() for m in mitglieder]
    for m in mitglieder:
        pseudo = f"M-{int(m['id'])}"
        v, n = (m.get("vorname") or "").strip(), (m.get("name") or "").strip()
        klarnamen[pseudo] = f"{v} {n}".strip()
        for variante in namensvarianten(v, n):
            ersetzungen.append((variante, pseudo))
        if v and n and nachnamen.count(n) == 1:
            ersetzungen.append((n, pseudo))
    ersetzungen.sort(key=lambda e: len(e[0]), reverse=True)
    return klarnamen, ersetzungen


class Maskierer:
    """Maskiert Personendaten in Dokumenttext. Eine Instanz pro Ingest-Lauf."""

    def __init__(self, mitglieder: list[dict], nlp=None,
                 bekannte_fremde: set[str] | None = None):
        self._nlp = nlp
        self._klarnamen: dict[str, str] = {}
        self._ersetzungen: list[tuple[str, str]] = []
        # Seeds (z.B. aus alter Mapping-Datei) durch denselben Filter wie
        # NER-Funde — sonst sickern alte Fehlerkennungen wieder ein.
        self._fremde_bekannt: set[str] = {
            n for n in (bekannte_fremde or ()) if _plausibler_name(n)
        }

        self._klarnamen, self._ersetzungen = mitglieder_ersetzungen(mitglieder)

    def _ner_kandidaten(self, text: str) -> set[str]:
        """Fremde Personennamen, die die NER in diesem Text erkennt."""
        if self._nlp is None:
            self._nlp = _lade_nlp()
        kandidaten = set()
        for ent in self._nlp(text).ents:
            # Whitespace normalisieren: Spans über Zeilenumbrüche ("Hans\n
            # Besucher") würden sonst die Mapping-Datei zerreißen und in
            # anderen Dokumenten nicht greifen.
            kandidat = " ".join(ent.text.split())
            if (ent.label_ == "PER" and _plausibler_name(kandidat)
                    and not re.search(r"\b[MP]-\d+", kandidat)):
                kandidaten.add(kandidat)
        return kandidaten

    def erkenne_fremde(self, text: str) -> None:
        """Vorab-Pass: sammelt fremde Namen, ohne zu ersetzen. Damit wird ein
        Name, den die NER nur in einem Dokument erkennt, überall maskiert."""
        self._fremde_bekannt |= self._ner_kandidaten(text)

    def maskiere(self, text: str, dokument_id: int) -> tuple[str, dict[str, str]]:
        """Maskiert einen Dokumenttext; gibt (maskierter Text, Pseudonym-Mapping) zurück."""
        mapping: dict[str, str] = {}

        # Stufe 1: bekannte Mitglieder (deterministisch)
        for variante, pseudo in self._ersetzungen:
            muster = _namensmuster(variante)
            if muster.search(text):
                text = muster.sub(pseudo, text)
                mapping[pseudo] = self._klarnamen[pseudo]

        # Stufe 2: fremde Personennamen — NER-Funde dieses Texts PLUS alle
        # bereits bekannten fremden Namen (Vorab-Pass, frühere Läufe).
        # Case-insensitiv: Anwesenheitslisten schreiben Namen oft in Versalien.
        self._fremde_bekannt |= self._ner_kandidaten(text)
        # Bei Nachmaskierung enthält der Text schon P-<id>-n aus früheren
        # Läufen — neue Nummern dahinter anschließen, sonst kollidieren
        # zwei Personen auf demselben Pseudonym.
        vergeben = [int(n) for n in re.findall(rf"\bP-{dokument_id}-(\d+)\b", text)]
        naechste = max(vergeben, default=0) + 1
        fremde: dict[str, str] = {}
        for kandidat in sorted(self._fremde_bekannt, key=len, reverse=True):
            if _namensmuster(kandidat, re.IGNORECASE).search(text):
                fremde[kandidat] = f"P-{dokument_id}-{naechste + len(fremde)}"
        for kandidat, pseudo in sorted(fremde.items(), key=lambda e: len(e[0]), reverse=True):
            text = _namensmuster(kandidat, re.IGNORECASE).sub(pseudo, text)
            mapping[pseudo] = kandidat

        # Regex-Pässe: Kontaktdaten brauchen kein Mapping, nur Entfernung.
        # WICHTIG: IBAN vor Telefon, sonst frisst die Telefon-Regex IBAN-Teile.
        text = REGEX_EMAIL.sub("[E-MAIL]", text)
        text = REGEX_IBAN.sub("[IBAN]", text)
        text = REGEX_TELEFON.sub("[TELEFON]", text)
        text = REGEX_GEBURTSDATUM.sub(r"\1 [GEBURTSDATUM]", text)

        logger.info("Dokument %s maskiert: %d Pseudonyme", dokument_id, len(mapping))
        return text, mapping
