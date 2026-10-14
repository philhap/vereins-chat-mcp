"""
PII-Sweep API-Richtung: kompletter Chat-Durchlauf mit Klarnamen in der Frage —
KEIN bekannter Klarname darf in irgendeinem Request-Payload an die
(gemockte) Anthropic-API auftauchen. Gegenstück zum PII-Sweep aus Phase A.
Nur fiktive Personen.
"""
import json
from types import SimpleNamespace

from webling_chat import chat
from webling_chat.vormaskierung import Vormaskierer
from webling_mcp import tools

MITGLIEDER = [
    {"id": 1, "vorname": "Timo", "name": "Testmann"},
    {"id": 2, "vorname": "Jenny", "name": "Probefrau"},
]
FREMDE = {"P-9-1": "Hans Besucher"}
VERBOTEN = ["Testmann", "Probefrau", "Besucher", "timo@example.org"]


class FakeClient:
    def __init__(self, antworten):
        self._antworten = list(antworten)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # Payload sofort serialisieren — genau das ginge über den Draht
        self.requests.append(json.dumps(kwargs, ensure_ascii=False, default=str))
        inhalt, stop = self._antworten.pop(0)
        return SimpleNamespace(content=inhalt, stop_reason=stop)


def test_kein_klarname_in_api_requests(monkeypatch):
    monkeypatch.setitem(
        tools.WERKZEUGE, "unbezahlte_beitraege",
        lambda jahr=None: {"anzahl_offen": 1, "mitglieder": ["M-1"]})
    client = FakeClient([
        ([SimpleNamespace(type="tool_use", name="unbezahlte_beitraege",
                          input={}, id="tu_1")], "tool_use"),
        ([SimpleNamespace(type="text",
                          text="M-1 hat nicht bezahlt, P-9-1 war Gast.")], "end_turn"),
    ])
    vormask = Vormaskierer(MITGLIEDER, FREMDE)
    frage = vormask.maskiere(
        "Hat Timo Testmann bezahlt? Hans Besucher fragt auch — "
        "Antwort an timo@example.org. Und die probefrau?")
    verlauf = []
    chat.antworte(client, verlauf, frage, tools.ANTHROPIC_TOOLS)

    assert len(client.requests) == 2
    for payload in client.requests:
        for name in VERBOTEN:
            assert name.lower() not in payload.lower(), (
                f"Klarname {name!r} im API-Payload gefunden!")


def test_mehrere_runden_verlauf_bleibt_pseudonym():
    # Zweite Frage in derselben Session: alter Verlauf wird mitgesendet
    client = FakeClient([
        ([SimpleNamespace(type="text", text="M-1 fehlt.")], "end_turn"),
        ([SimpleNamespace(type="text", text="M-2 auch.")], "end_turn"),
    ])
    vormask = Vormaskierer(MITGLIEDER, FREMDE)
    verlauf = []
    chat.antworte(client, verlauf, vormask.maskiere("Wo ist Timo Testmann?"),
                  tools.ANTHROPIC_TOOLS)
    chat.antworte(client, verlauf, vormask.maskiere("Und Jenny Probefrau?"),
                  tools.ANTHROPIC_TOOLS)
    for payload in client.requests:
        for name in VERBOTEN:
            assert name.lower() not in payload.lower()


def test_sweep_sieht_tool_kanal(monkeypatch):
    # Kontrolltest: würde ein Tool einen Klarnamen leaken, MUSS er im
    # serialisierten Folge-Payload sichtbar sein — sonst wäre der Sweep auf
    # dem Tool-Kanal blind. "Lecky Leckmann" ist fiktiv.
    monkeypatch.setitem(
        tools.WERKZEUGE, "unbezahlte_beitraege",
        lambda jahr=None: {"anzahl_offen": 1, "mitglieder": ["Lecky Leckmann"]})
    client = FakeClient([
        ([SimpleNamespace(type="tool_use", name="unbezahlte_beitraege",
                          input={}, id="tu_1")], "tool_use"),
        ([SimpleNamespace(type="text", text="Fertig.")], "end_turn"),
    ])
    chat.antworte(client, [], "Wer hat nicht bezahlt?", tools.ANTHROPIC_TOOLS)
    assert "Lecky Leckmann" in client.requests[1], (
        "Tool-Ergebnisse sind im Sweep-Payload nicht sichtbar — Sweep blind!")


def test_sweep_sieht_assistant_kanal():
    # Kontrolltest: würde das Modell selbst einen Klarnamen in seinem
    # Antworttext leaken (Assistant-Kanal), MUSS er im serialisierten
    # Payload der nächsten Runde sichtbar sein — sonst wäre der Sweep auf
    # diesem Kanal blind. Der Verlauf enthält (wie im echten SDK) rohe
    # Content-Objekte; erst der nächste Request serialisiert sie über
    # json.dumps(..., default=str). "Lecky Leckmann" ist fiktiv.
    client = FakeClient([
        ([SimpleNamespace(type="text",
                          text="Der Vereinsvorsitz ist Lecky Leckmann.")], "end_turn"),
        ([SimpleNamespace(type="text", text="Alles klar.")], "end_turn"),
    ])
    verlauf = []
    chat.antworte(client, verlauf, "Wer ist im Vorstand?", tools.ANTHROPIC_TOOLS)
    chat.antworte(client, verlauf, "Und sonst noch wer?", tools.ANTHROPIC_TOOLS)

    assert len(client.requests) == 2
    assert "Lecky Leckmann" in client.requests[1], (
        "Assistant-Antworttext ist im Sweep-Payload der Folgerunde nicht "
        "sichtbar — Sweep blind auf dem Assistant-Kanal!")
