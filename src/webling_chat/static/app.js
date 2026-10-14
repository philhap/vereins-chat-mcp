// Chat-Logik: Nachricht senden, SSE-Stream lesen (Events: werkzeug/antwort/fehler/ende)
import { rendereMarkdown } from "/static/markdown.js";

const verlauf = document.getElementById("verlauf");
const form = document.getElementById("chat-form");
const eingabe = document.getElementById("nachricht");

function blase(klasse, text) {
  const div = document.createElement("div");
  div.className = "blase " + klasse;
  div.textContent = text;
  verlauf.appendChild(div);
  verlauf.scrollTop = verlauf.scrollHeight;
  return div;
}

async function lade_status() {
  const r = await fetch("/api/status");
  if (r.status === 401) { location.href = "/login"; return; }
  const s = await r.json();
  document.getElementById("status").textContent =
    s.index_vom ? `Index vom ${s.index_vom}` : "Kein Index";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const nachricht = eingabe.value.trim();
  if (!nachricht) return;
  eingabe.value = "";
  blase("ich", nachricht);
  const warte = blase("warte", "…");

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({nachricht}),
    });
    if (r.status === 401) { location.href = "/login"; return; }
    if (!r.ok) {
      warte.className = "blase fehler";
      warte.textContent = "Verbindungsfehler — bitte nochmal versuchen.";
      eingabe.disabled = false;
      return;
    }

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let puffer = "";
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      puffer += dec.decode(value, {stream: true});
      let idx;
      while ((idx = puffer.indexOf("\n\n")) >= 0) {
        const block = puffer.slice(0, idx);
        puffer = puffer.slice(idx + 2);
        const art = (/^event: (.+)$/m.exec(block) || [])[1];
        const daten = JSON.parse((/^data: (.+)$/m.exec(block) || [null, '""'])[1]);
        if (art === "werkzeug") warte.textContent = `🔎 ${daten} …`;
        // Nur die Antwort wird als Markdown gerendert. rendereMarkdown escaped
        // jeden Textschnipsel, bevor daraus HTML wird — Status- und
        // Fehlermeldungen bleiben bewusst bei textContent.
        else if (art === "antwort") { warte.className = "blase bot"; warte.innerHTML = rendereMarkdown(daten); }
        else if (art === "fehler") { warte.className = "blase fehler"; warte.textContent = daten; }
      }
    }
  } catch (fehler) {
    // Netzwerkfehler oder Abbruch mitten im Stream-Lesen
    warte.className = "blase fehler";
    warte.textContent = "Verbindungsfehler — bitte nochmal versuchen.";
    eingabe.disabled = false;
  }
});

document.getElementById("abmelden").addEventListener("click", async () => {
  await fetch("/api/logout", {method: "POST"});
  location.href = "/login";
});

lade_status();
