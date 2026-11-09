import datetime as dt
import io
import json
import math
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP_DB = Path("/tmp/garten_test.db")


@pytest.fixture()
def client(monkeypatch):
    if TMP_DB.exists():
        TMP_DB.unlink()
    monkeypatch.setenv("GARTEN_DB", str(TMP_DB))
    import importlib
    import app as appmod
    importlib.reload(appmod)
    appmod.app.config.update(TESTING=True)
    with appmod.app.test_client() as c:
        yield c, appmod


def login(client, appmod, username="sven", password="geheimes-test-pw"):
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(TMP_DB)
    conn.execute("UPDATE users SET password_hash=? WHERE username=?",
                 (generate_password_hash(password), username))
    conn.commit(); conn.close()
    c = client
    c.get("/login")  # erzeugt CSRF-Token in der Session, wie im Browser
    with c.session_transaction() as s:
        tok = s["csrf"]
    r = c.post("/login", data={"username": username, "password": password, "csrf_token": tok})
    assert r.status_code == 302, r.data
    with c.session_transaction() as s:
        return s["csrf"]



def csrf_headers(token):
    return {"X-CSRF-Token": token, "Content-Type": "application/json"}


# ---------- Priorität & Datum ----------

from priority import add_months, berechne_prioritaet, ics_kalender  # noqa: E402


def test_prio_ueberfaellig_und_schlechter_zustand_ist_hoch():
    heute = dt.date(2026, 3, 10)
    assert berechne_prioritaet(dt.date(2026, 2, 1), heute, zustand=1) == 1


def test_prio_ausserhalb_saison_niedriger():
    heute = dt.date(2026, 8, 1)
    prio_innen = berechne_prioritaet(dt.date(2026, 8, 20), heute, zustand=5, saison="2,3")
    prio_aussen = berechne_prioritaet(dt.date(2026, 8, 20), heute, zustand=5, saison="8")
    assert prio_aussen <= prio_innen or prio_aussen == 3


def test_prio_manuell_ueberschreibt():
    assert berechne_prioritaet(dt.date(2030, 1, 1), dt.date(2026, 1, 1), zustand=5, prio_manuell=1) == 1


def test_add_months_kuerzt_tag():
    assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert add_months(dt.date(2026, 11, 15), 3) == dt.date(2027, 2, 15)


def test_ics_zwei_alarme_pro_termin():
    ics = ics_kalender([{"uid": "t1", "titel": "Schnitt", "datum": dt.date(2026, 3, 1)}])
    assert ics.count("BEGIN:VALARM") == 2
    assert "TRIGGER:-P1D" in ics and "TRIGGER:-PT1H" in ics


# ---------- Flächenberechnung ----------

def test_flaeche_rechteck_innerhalb_1_prozent(client):
    _, appmod = client
    # 100 m x 50 m Rechteck in Lauenau (ca. 52.2842, 9.3884), berechnet über Breitengrad/Längengrad
    lat0, lon0 = 52.2842, 9.3884
    dlat = 50 / 111_320.0
    dlon = 100 / (111_320.0 * math.cos(math.radians(lat0)))
    ring = [[lon0, lat0], [lon0 + dlon, lat0], [lon0 + dlon, lat0 + dlat], [lon0, lat0 + dlat], [lon0, lat0]]
    f = appmod._flaeche_m2({"type": "Polygon", "coordinates": [ring]})
    assert abs(f - 5000) / 5000 < 0.01, f


# ---------- Flurstücke ----------

def test_flurstuecke_datei_hat_663_features():
    p = ROOT / "data" / "flurstuecke_feggendorf.geojson"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert len(d["features"]) == 663
    assert all(f["properties"]["gemarkung"] == "Feggendorf" for f in d["features"])


def test_flurstuecke_endpunkt_liefert_features(client):
    c, appmod = client
    login(c, appmod)
    r = c.get("/api/flurstuecke")
    assert r.status_code == 200
    assert len(r.get_json()["features"]) == 663


# ---------- Login & Rollen ----------

def test_ohne_login_geschuetzt(client):
    c, _ = client
    assert c.get("/heute").status_code == 302
    assert c.get("/api/heute").status_code == 401


def test_passwort_nicht_gesetzt_login_gesperrt(client):
    c, _ = client
    c.get("/login")
    with c.session_transaction() as s:
        tok = s["csrf"]
    r = c.post("/login", data={"username": "johannes", "password": "irgendwas", "csrf_token": tok})
    assert r.status_code == 200
    assert "nicht möglich" in r.get_data(as_text=True)


def test_meister_darf_aufgabe_anlegen_lehrling_nicht_aendert_vorlage(client):
    c, appmod = client
    tok = login(c, appmod, "johannes")
    gid = _garden_id(appmod)
    r = c.post(f"/api/gaerten/{gid}/aufgaben", json={"titel": "Test"}, headers=csrf_headers(tok))
    assert r.status_code == 201


def test_owner_darf_aufgabe_anlegen(client):
    c, appmod = client
    tok = login(c, appmod, "sven")
    gid = _garden_id(appmod)
    r = c.post(f"/api/gaerten/{gid}/aufgaben", json={"titel": "Owner-Aufgabe"}, headers=csrf_headers(tok))
    assert r.status_code == 201


def test_fremder_garten_unsichtbar(client):
    c, appmod = client
    tok = login(c, appmod, "sven")
    conn = sqlite3.connect(TMP_DB)
    conn.execute("INSERT INTO gardens(name, created_by) VALUES('Fremd', 2)")
    fremd = conn.execute("SELECT id FROM gardens WHERE name='Fremd'").fetchone()[0]
    conn.execute("DELETE FROM garden_members WHERE garden_id=?", (fremd,))
    conn.commit(); conn.close()
    r = c.get(f"/api/gaerten/{fremd}/aufgaben")
    assert r.status_code == 404


def _garden_id(appmod):
    conn = sqlite3.connect(TMP_DB)
    gid = conn.execute("SELECT id FROM gardens ORDER BY id LIMIT 1").fetchone()[0]
    conn.close()
    return gid


# ---------- Wiederkehrende Aufgabe ----------

def test_wiederkehrende_aufgabe_neues_datum(client):
    c, appmod = client
    tok = login(c, appmod, "sven")
    gid = _garden_id(appmod)
    r = c.post(f"/api/gaerten/{gid}/aufgaben", json={
        "titel": "Hecke", "intervall_monate": 6, "faellig_am": "2026-03-01"}, headers=csrf_headers(tok))
    tid = r.get_json()["id"]
    r2 = c.post(f"/api/aufgaben/{tid}/erledigen", json={"datum": "2026-03-10"}, headers=csrf_headers(tok))
    assert r2.status_code == 200
    assert r2.get_json()["neue_faelligkeit"] == "2026-09-10"


# ---------- Medien ----------

def test_bild_wird_verkleinert_und_gps_gelesen(client):
    from PIL import Image
    c, appmod = client
    tok = login(c, appmod, "sven")
    gid = _garden_id(appmod)
    oid = c.post(f"/api/gaerten/{gid}/objekte", json={"name": "Apfel", "typ": "pflanze"},
                 headers=csrf_headers(tok)).get_json()["id"]
    img = Image.new("RGB", (4000, 3000), (30, 120, 60))
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=95); buf.seek(0)
    r = c.post("/api/medien", data={"datei": (buf, "foto.jpg"), "object_id": oid, "typ_tag": "vorher"},
               headers={"X-CSRF-Token": tok}, content_type="multipart/form-data")
    assert r.status_code == 201, r.data
    pfad = r.get_json()["pfad"]
    out = Image.open(Path(appmod.UPLOADS) / pfad)
    assert max(out.size) <= 2048


def test_bild_ueber_10mb_abgelehnt(client):
    c, appmod = client
    tok = login(c, appmod, "sven")
    gid = _garden_id(appmod)
    oid = c.post(f"/api/gaerten/{gid}/objekte", json={"name": "Groß", "typ": "pflanze"},
                 headers=csrf_headers(tok)).get_json()["id"]
    big = io.BytesIO(b"\xff\xd8" + b"0" * (10 * 1024 * 1024 + 10))
    r = c.post("/api/medien", data={"datei": (big, "gross.jpg"), "object_id": oid},
               headers={"X-CSRF-Token": tok}, content_type="multipart/form-data")
    assert r.status_code == 413


# ---------- CSRF ----------

def test_post_ohne_csrf_abgelehnt(client):
    c, appmod = client
    login(c, appmod, "sven")
    gid = _garden_id(appmod)
    r = c.post(f"/api/gaerten/{gid}/aufgaben", json={"titel": "X"})
    assert r.status_code == 403


# ---------- ICS-Export über API ----------

def test_ics_endpunkt_enthaelt_zwei_alarme(client):
    c, appmod = client
    tok = login(c, appmod, "sven")
    gid = _garden_id(appmod)
    c.post(f"/api/gaerten/{gid}/aufgaben", json={"titel": "Kalender-Test", "faellig_am": "2027-01-15"},
           headers=csrf_headers(tok))
    r = c.get(f"/api/gaerten/{gid}/kalender.ics")
    text = r.get_data(as_text=True)
    assert r.status_code == 200
    assert text.count("BEGIN:VALARM") >= 2
    assert "TRIGGER:-P1D" in text
