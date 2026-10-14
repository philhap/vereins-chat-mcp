"""Tool-Use-Schleife mit gemocktem Anthropic-Client (Phase C)."""
from types import SimpleNamespace

import pytest

from webling_chat import chat
from webling_mcp import domain, tools


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(name, args, id_="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id_)


class FakeClient:
    """Spielt vorgegebene Antworten ab und sammelt alle Requests."""

    def __init__(self, antworten):
        self._antworten = list(antworten)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        inhalt, stop = self._antworten.pop(0)
        return SimpleNamespace(content=inhalt, stop_reason=stop)


WERKZEUGE = tools.ANTHROPIC_TOOLS


def test_direkte_antwort_ohne_tools():
    client = FakeClient([([_text("Hallo!")], "end_turn")])
    verlauf = []
    text = chat.antworte(client, verlauf, "Hi", WERKZEUGE)
    assert text == "Hallo!"
    assert verlauf[0] == {"role": "user", "content": "Hi"}
    assert client.requests[0]["model"] == chat.MODELL
    assert client.requests[0]["tools"] == WERKZEUGE


def test_system_prompt_nennt_das_aktuelle_datum(monkeypatch):
    """Ohne Datum im Prompt rät das Modell die Jahreszahl — es hat im E2E die
    Jubilare von 2025 geliefert, obwohl 2026 gefragt war."""
    monkeypatch.setattr(chat, "_heute", lambda: "Dienstag, 21.07.2026")
    client = FakeClient([([_text("ok")], "end_turn")])

    chat.antworte(client, [], "Wer wird dieses Jahr 70?", WERKZEUGE)

    assert "21.07.2026" in client.requests[0]["system"]


def test_tool_runde(monkeypatch):
    monkeypatch.setitem(tools.WERKZEUGE, "list_groups", lambda: {"gruppen": []})
    client = FakeClient([
        ([_tool_use("list_groups", {})], "tool_use"),
        ([_text("Keine Gruppen.")], "end_turn"),
    ])
    status = []
    text = chat.antworte(client, [], "Welche Gruppen?", WERKZEUGE,
                         status_cb=status.append)
    assert text == "Keine Gruppen."
    assert status == ["list_groups"]
    # Tool-Ergebnis ging als tool_result mit passender ID zurück
    letzte = client.requests[1]["messages"][-1]
    assert letzte["role"] == "user"
    assert letzte["content"][0]["tool_use_id"] == "tu_1"


def test_tool_antwort_ohne_hinweise_auf_lokale_dateien(monkeypatch):
    """Die Hinweise in tools.py gelten für den MCP-Zugang, wo der Nutzer
    Pseudonyme selbst über lokale Dateien auflöst. Im Chat werden Klarnamen
    direkt angezeigt — das Modell gab den Satz sonst wörtlich weiter. Der
    absolute Dateipfad (inkl. Benutzername) hat an der API ohnehin nichts
    verloren."""
    monkeypatch.setitem(tools.WERKZEUGE, "jubilaeen", lambda jahr=None: {
        "jahr": 2026,
        "anzahl": 1,
        "jubilare": [{"id": "M-1", "alter": 70, "monat": 3}],
        "namensliste_lokal": r"C:\Users\PCUser\phil-os\output\jubilaeen.md",
        "hinweis": "Echte Namen stehen nur in der lokalen Datei.",
    })
    client = FakeClient([
        ([_tool_use("jubilaeen", {})], "tool_use"),
        ([_text("Ein Jubilar.")], "end_turn"),
    ])

    chat.antworte(client, [], "Jubilare?", WERKZEUGE)

    inhalt = client.requests[1]["messages"][-1]["content"][0]["content"]
    assert "namensliste_lokal" not in inhalt
    assert "lokalen Datei" not in inhalt
    assert "PCUser" not in inhalt
    assert '"M-1"' in inhalt and '"alter": 70' in inhalt   # Nutzdaten bleiben


def test_nicht_erlaubtes_tool_wird_nicht_ausgefuehrt():
    # Modell will ein Tool, das die Policy nicht freigegeben hat
    nur_gruppen = [t for t in WERKZEUGE if t["name"] == "list_groups"]
    client = FakeClient([
        ([_tool_use("unbezahlte_beitraege", {})], "tool_use"),
        ([_text("Ok.")], "end_turn"),
    ])
    chat.antworte(client, [], "Beiträge?", nur_gruppen)
    inhalt = client.requests[1]["messages"][-1]["content"][0]["content"]
    assert "nicht erlaubt" in inhalt


def test_max_runden_begrenzt():
    client = FakeClient(
        [([_tool_use("list_groups", {})], "tool_use")] * chat.MAX_RUNDEN)
    text = chat.antworte(client, [], "Loop?", WERKZEUGE)
    assert "abgebrochen" in text.lower()


def test_system_prompt_enthaelt_legende_und_begriffsklaerung():
    prompt = chat.SYSTEM_PROMPT.format(heute="Montag, 01.01.2026",
                                       legende=domain.status_legende())
    assert "A-Mitglied" in prompt          # Legende eingebettet
    assert "150" in prompt
    # Die drei aehnlich klingenden Felder werden getrennt benannt
    assert "mitgliedsbeitrag" in prompt
    assert "beitragsstatus" in prompt
