"""
Klammert die JS-Tests des Markdown-Renderers an den normalen Testlauf.

Ohne das wuerde `pytest` gruen melden, waehrend der Renderer kaputt ist — und
genau der entscheidet, ob Modellausgabe escaped wird, bevor sie als HTML in die
Seite geht. Fehlt node, wird uebersprungen statt falsch gruen zu melden.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = sorted((Path(__file__).parent / "js").glob("*.test.mjs"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht installiert")
@pytest.mark.parametrize("testdatei", JS_TESTS, ids=lambda p: p.name)
def test_javascript(testdatei):
    ergebnis = subprocess.run(
        ["node", "--test", str(testdatei)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
