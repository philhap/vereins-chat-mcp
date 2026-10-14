// Tests fuer den Markdown-Renderer der Chat-PWA.
// Lauf: node --test tests/js   (wird auch von tests/test_markdown_js.py angestossen)
import test from "node:test";
import assert from "node:assert/strict";

import { rendereMarkdown } from "../../src/webling_chat/static/markdown.js";

// --- Sicherheit: alles wird escaped, bevor es HTML wird ----------------------

test("HTML im Text wird escaped, nicht ausgefuehrt", () => {
  const html = rendereMarkdown("<script>alert(1)</script>");
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("Attribut-Injektion in Bild-Tags wird escaped", () => {
  const html = rendereMarkdown('<img src=x onerror="alert(1)">');
  assert.ok(!html.includes("<img"));
  assert.ok(!html.includes("onerror=\""));
});

test("Sonderzeichen in Namen bleiben lesbar", () => {
  // Klarnamen laufen durch den Renderer - & und < duerfen nichts zerreissen
  const html = rendereMarkdown("Müller & Sohn <intern>");
  assert.ok(html.includes("Müller &amp; Sohn &lt;intern&gt;"));
});

test("Escaping passiert vor der Inline-Auszeichnung", () => {
  const html = rendereMarkdown("**<b>fett</b>**");
  assert.ok(html.includes("<strong>&lt;b&gt;fett&lt;/b&gt;</strong>"));
});

// --- Inline ------------------------------------------------------------------

test("Fettschrift", () => {
  assert.ok(rendereMarkdown("Das ist **wichtig**.").includes("<strong>wichtig</strong>"));
});

test("Kursiv", () => {
  assert.ok(rendereMarkdown("Das ist *kursiv*.").includes("<em>kursiv</em>"));
});

test("Code", () => {
  assert.ok(rendereMarkdown("Feld `id` pruefen").includes("<code>id</code>"));
});

test("Einzelne Sternchen ohne Partner bleiben stehen", () => {
  const html = rendereMarkdown("3 * 4 = 12");
  assert.ok(html.includes("3 * 4 = 12"));
  assert.ok(!html.includes("<em>"));
});

// --- Bloecke -----------------------------------------------------------------

test("Aufzaehlung wird zur Liste", () => {
  const html = rendereMarkdown("- Erster\n- Zweiter");
  assert.ok(html.includes("<ul>"));
  assert.equal((html.match(/<li>/g) || []).length, 2);
  assert.ok(html.includes("<li>Erster</li>"));
});

test("Nummerierte Aufzaehlung", () => {
  const html = rendereMarkdown("1. Eins\n2. Zwei");
  assert.ok(html.includes("<ol>"));
  assert.equal((html.match(/<li>/g) || []).length, 2);
});

test("Ueberschriften bleiben unterhalb der Seitengliederung", () => {
  // Die Blase steckt schon in der Seite - h1/h2 wuerden deren Gliederung kapern
  for (const quelle of ["# Jubilare", "## Jubilare", "###### Jubilare"]) {
    const html = rendereMarkdown(quelle);
    assert.ok(/^<h[3-6]>Jubilare<\/h[3-6]>$/.test(html), quelle + " -> " + html);
  }
});

test("Ueberschriftstufen bleiben unterscheidbar", () => {
  assert.notEqual(rendereMarkdown("# A"), rendereMarkdown("## A"));
});

test("Tabelle mit Kopfzeile", () => {
  const html = rendereMarkdown(
    "| Pseudonym | Alter | Monat |\n|---|---|---|\n| M-1 | 70 | 3 |\n| M-2 | 65 | 8 |");
  assert.ok(html.includes("<table>"));
  assert.equal((html.match(/<th>/g) || []).length, 3);
  assert.equal((html.match(/<tr>/g) || []).length, 3);   // Kopf + zwei Zeilen
  assert.ok(html.includes("<td>M-1</td>"));
  assert.ok(!html.includes("---"));                       // Trennzeile verschwindet
});

test("Tabelle ohne Trennzeile wird trotzdem gerendert", () => {
  const html = rendereMarkdown("| A | B |\n| 1 | 2 |");
  assert.ok(html.includes("<table>"));
  assert.ok(html.includes("<td>1</td>"));
});

test("Absaetze bleiben getrennt", () => {
  const html = rendereMarkdown("Erster Absatz.\n\nZweiter Absatz.");
  assert.equal((html.match(/<p>/g) || []).length, 2);
});

test("Zeilenumbruch innerhalb eines Absatzes", () => {
  assert.ok(rendereMarkdown("Zeile eins\nZeile zwei").includes("<br>"));
});

test("Leerer Text ergibt leeres Ergebnis", () => {
  assert.equal(rendereMarkdown(""), "");
  assert.equal(rendereMarkdown("   \n  "), "");
});

test("Gemischte Antwort: Text, Tabelle, Liste", () => {
  const html = rendereMarkdown(
    "Im Jahr 2026 gibt es **2 Jubilare**:\n\n" +
    "| Pseudonym | Alter |\n|---|---|\n| M-1 | 70 |\n\n" +
    "Hinweise:\n- Namen stehen lokal\n- Tag fehlt bewusst");
  assert.ok(html.includes("<strong>2 Jubilare</strong>"));
  assert.ok(html.includes("<table>"));
  assert.ok(html.includes("<ul>"));
});
