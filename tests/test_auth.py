"""Login, Sessions, Rate-Limit (Phase C). Nur fiktive Nutzer."""
import pytest

from webling_chat import auth


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBLING_CHAT_DATEN_DIR", str(tmp_path))
    c = auth.oeffne_db()
    yield c
    c.close()


def test_login_richtig_und_falsch(con):
    auth.lege_nutzer_an(con, "phil", "geheim-und-lang")
    assert auth.pruefe_login(con, "phil", "geheim-und-lang")["rolle"] == "vorstand"
    assert auth.pruefe_login(con, "phil", "falsch") is None
    assert auth.pruefe_login(con, "unbekannt", "x") is None


def test_doppelter_benutzername(con):
    auth.lege_nutzer_an(con, "phil", "pw1-lang-genug")
    with pytest.raises(ValueError):
        auth.lege_nutzer_an(con, "phil", "pw2-lang-genug")


def test_session_lebenszyklus(con):
    nid = auth.lege_nutzer_an(con, "phil", "geheim-und-lang")
    token = auth.erstelle_session(con, nid)
    assert auth.hole_session(con, token)["benutzername"] == "phil"
    auth.loesche_session(con, token)
    assert auth.hole_session(con, token) is None
    assert auth.hole_session(con, "gibtsnicht") is None


def test_abgelaufene_session(con):
    nid = auth.lege_nutzer_an(con, "phil", "geheim-und-lang")
    token = auth.erstelle_session(con, nid)
    con.execute("UPDATE sessions SET ablauf = '2000-01-01T00:00:00+00:00'")
    con.commit()
    assert auth.hole_session(con, token) is None


def test_passwort_wird_gehasht(con):
    auth.lege_nutzer_an(con, "phil", "geheim-und-lang")
    hash_ = con.execute("SELECT passwort_hash FROM nutzer").fetchone()[0]
    assert "geheim-und-lang" not in hash_ and hash_.startswith("$argon2")


def test_login_limit():
    limit = auth.LoginLimit(max_versuche=2, fenster_s=900)
    assert limit.erlaubt("1.2.3.4")
    limit.fehlversuch("1.2.3.4"); limit.fehlversuch("1.2.3.4")
    assert not limit.erlaubt("1.2.3.4")
    assert limit.erlaubt("5.6.7.8")          # andere IP unabhängig
    limit.erfolg("1.2.3.4")
    assert limit.erlaubt("1.2.3.4")
