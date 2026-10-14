// Minimaler Markdown-Renderer fuer Chat-Antworten (kein Build, keine Abhaengigkeit).
//
// SICHERHEIT: Durch diesen Renderer laufen Modellausgabe UND rueckersetzte
// Klarnamen. Deshalb wird JEDER Textschnipsel zuerst escaped und erst danach
// ausgezeichnet - Tags entstehen ausschliesslich hier im Code, nie aus dem
// Eingabetext. Wer das umbaut: escape() muss immer der erste Schritt bleiben.
//
// Umfang bewusst klein: fett, kursiv, Code, Ueberschriften, Listen, Tabellen.
// Alles andere erscheint als normaler Text.

function escape(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(text) {
  return escape(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
}

const IST_TABELLENZEILE = (z) => z.startsWith("|") && z.endsWith("|");
const IST_TRENNZEILE = (z) => /^\|[\s:|-]+\|$/.test(z) && z.includes("-");
const IST_PUNKT = (z) => /^[-*]\s+/.test(z);
const IST_NUMMER = (z) => /^\d+\.\s+/.test(z);

function zellen(zeile) {
  return zeile.slice(1, -1).split("|").map((z) => z.trim());
}

function tabelle(zeilen) {
  const hatTrenner = zeilen.length > 1 && IST_TRENNZEILE(zeilen[1]);
  const kopf = zellen(zeilen[0]);
  const koerper = zeilen.slice(hatTrenner ? 2 : 1).map(zellen);
  const kopfZeile = "<tr>" + kopf.map((z) => `<th>${inline(z)}</th>`).join("") + "</tr>";
  const rest = koerper
    .map((r) => "<tr>" + r.map((z) => `<td>${inline(z)}</td>`).join("") + "</tr>")
    .join("");
  return `<table>${kopfZeile}${rest}</table>`;
}

function liste(zeilen, geordnet) {
  const tag = geordnet ? "ol" : "ul";
  const punkte = zeilen
    .map((z) => z.replace(geordnet ? /^\d+\.\s+/ : /^[-*]\s+/, ""))
    .map((z) => `<li>${inline(z)}</li>`)
    .join("");
  return `<${tag}>${punkte}</${tag}>`;
}

function absatz(zeilen) {
  return `<p>${zeilen.map(inline).join("<br>")}</p>`;
}

// Ueberschriften starten bei h3: die Chat-Blase steckt schon in der Seite,
// h1/h2 wuerden die Dokumentgliederung durcheinanderbringen.
function ueberschrift(zeile) {
  const stufe = zeile.match(/^#{1,6}/)[0].length;
  const inhalt = zeile.replace(/^#{1,6}\s*/, "");
  const tag = `h${Math.min(stufe + 2, 6)}`;
  return `<${tag}>${inline(inhalt)}</${tag}>`;
}

export function rendereMarkdown(text) {
  const zeilen = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const teile = [];
  let i = 0;

  while (i < zeilen.length) {
    const zeile = zeilen[i].trim();

    if (zeile === "") { i++; continue; }

    if (zeile.startsWith("#")) {
      teile.push(ueberschrift(zeile));
      i++;
    } else if (IST_TABELLENZEILE(zeile)) {
      const block = [];
      while (i < zeilen.length && IST_TABELLENZEILE(zeilen[i].trim())) {
        block.push(zeilen[i].trim());
        i++;
      }
      teile.push(tabelle(block));
    } else if (IST_PUNKT(zeile) || IST_NUMMER(zeile)) {
      const geordnet = IST_NUMMER(zeile);
      const pruefe = geordnet ? IST_NUMMER : IST_PUNKT;
      const block = [];
      while (i < zeilen.length && pruefe(zeilen[i].trim())) {
        block.push(zeilen[i].trim());
        i++;
      }
      teile.push(liste(block, geordnet));
    } else {
      const block = [];
      while (i < zeilen.length) {
        const z = zeilen[i].trim();
        if (z === "" || z.startsWith("#") || IST_TABELLENZEILE(z)
            || IST_PUNKT(z) || IST_NUMMER(z)) break;
        block.push(z);
        i++;
      }
      teile.push(absatz(block));
    }
  }

  return teile.join("");
}
