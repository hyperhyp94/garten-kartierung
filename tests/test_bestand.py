import json

import pytest

from garten.db import verbinden
from garten.geo import abstand_m, flaeche_m2, pruefe_geometrie

from .conftest import ORT, foto, lege_pflanze_an, sende

RAHMEN = (9.36, 52.26, 9.45, 52.30)
# Rechteck von 20 mal 10 Metern bei Feggendorf
DLAT = 10 / 111194.9
DLON = 20 / (111194.9 * 0.6117)
RECHTECK = [[9.3835, 52.285], [9.3835 + DLON, 52.285], [9.3835 + DLON, 52.285 + DLAT], [9.3835, 52.285 + DLAT]]


def zeile(app, sql, *werte):
    con = verbinden(app.config["DATENBANK"])
    try:
        return con.execute(sql, werte).fetchall()
    finally:
        con.close()


def test_flaeche_eines_bekannten_rechtecks():
    assert flaeche_m2(RECHTECK) == pytest.approx(200, rel=0.01)
    assert abstand_m(RECHTECK[0], RECHTECK[1]) == pytest.approx(20, rel=0.01)


def test_geometrie_wird_geprueft_und_vermessen():
    punkt = pruefe_geometrie(ORT, RAHMEN)
    assert punkt["form"] == "punkt" and punkt["mass"] is None

    linie = pruefe_geometrie({"type": "LineString", "coordinates": RECHTECK[:2]}, RAHMEN)
    assert linie["form"] == "linie" and linie["mass"] == pytest.approx(20, rel=0.01)

    flaeche = pruefe_geometrie({"type": "Polygon", "coordinates": [RECHTECK + [RECHTECK[0]]]}, RAHMEN)
    assert flaeche["form"] == "flaeche"
    assert flaeche["mass"] == pytest.approx(200, rel=0.01)
    assert flaeche["umfang"] == pytest.approx(60, rel=0.01)
    assert flaeche["geometrie"]["coordinates"][0][0] == flaeche["geometrie"]["coordinates"][0][-1]

    for kaputt in (
        None,
        {"type": "Kreis"},
        {"type": "LineString", "coordinates": RECHTECK[:1]},
        {"type": "Polygon", "coordinates": [RECHTECK[:2]]},
        {"type": "Point", "coordinates": [11.5, 48.1]},  # München liegt nicht in Feggendorf
        {"type": "Point", "coordinates": ["x", "y"]},
    ):
        with pytest.raises((ValueError, TypeError)):
            pruefe_geometrie(kaputt, RAHMEN)


def test_pflanze_aus_dem_lexikon_bringt_aufgaben_mit(app, sven, garten):
    antwort = sende(sven, "/api/bestand", {
        "art": "pflanze", "name": "Apfelbaum am Zaun", "kategorie": "Obst", "lexikon_id": "apfel",
        "aufgaben_anlegen": "1", "zustand": "2", "standort_notiz": "hinter dem Schuppen",
        "geometrie": json.dumps(ORT), "bild": foto(), "vorschau": foto("vorschau.jpg"),
    })
    assert antwort.status_code == 201
    bestand_id = antwort.get_json()["id"]

    aufgaben = zeile(app, "SELECT titel, faellig_am, intervall_monate FROM aufgaben WHERE bestand_id = ?", bestand_id)
    assert {a["titel"] for a in aufgaben} == {
        "Obstbaum schneiden (Winterschnitt)", "Im Frühjahr düngen", "Auf Schädlinge und Krankheiten prüfen"
    }
    # Stichtag ist der 15. Januar: der Winterschnitt beginnt am 1. Februar.
    assert {a["titel"]: a["faellig_am"] for a in aufgaben}["Obstbaum schneiden (Winterschnitt)"] == "2027-02-01"
    assert all(a["intervall_monate"] == 12 for a in aufgaben)

    seite = sven.get(f"/bestand/{bestand_id}").get_data(as_text=True)
    assert "Apfelbaum am Zaun" in seite and "hinter dem Schuppen" in seite
    assert "Erfasst" in seite and "Richtwerte" in seite
    assert zeile(app, "SELECT zustand FROM bestand WHERE id = ?", bestand_id)[0]["zustand"] == 2
    assert len(zeile(app, "SELECT 1 FROM medien WHERE bestand_id = ? AND art = 'bild'", bestand_id)) == 1


def test_ohne_haken_keine_aufgaben(app, sven, garten):
    bestand_id = lege_pflanze_an(sven, lexikon_id="apfel")
    assert zeile(app, "SELECT 1 FROM aufgaben WHERE bestand_id = ?", bestand_id) == []


def test_eingaben_werden_geprueft(sven, garten):
    gut = {"art": "pflanze", "name": "Rose", "kategorie": "Strauch", "geometrie": json.dumps(ORT)}
    for aenderung in ({"name": ""}, {"kategorie": "Auto"}, {"geometrie": ""}, {"geometrie": "{kaputt"},
                      {"zustand": "9"}, {"lexikon_id": "gibt-es-nicht"},
                      {"geometrie": json.dumps({"type": "Point", "coordinates": [11.5, 48.1]})}):
        antwort = sende(sven, "/api/bestand", {**gut, **aenderung})
        assert antwort.status_code == 422, aenderung
        assert antwort.get_json()["fehler"]


def test_objekt_als_linie_und_flaeche(app, sven, garten):
    weg = sende(sven, "/api/bestand", {"art": "objekt", "name": "Weg", "kategorie": "Weg",
                                       "geometrie": json.dumps({"type": "LineString", "coordinates": RECHTECK[:2]})})
    beet = sende(sven, "/api/bestand", {"art": "objekt", "name": "Beet", "kategorie": "Beet",
                                        "geometrie": json.dumps({"type": "Polygon", "coordinates": [RECHTECK]})})
    assert weg.status_code == beet.status_code == 201
    masse = {z["name"]: (z["form"], z["mass"]) for z in zeile(app, "SELECT name, form, mass FROM bestand")}
    assert masse["Weg"][0] == "linie" and masse["Weg"][1] == pytest.approx(20, rel=0.01)
    assert masse["Beet"][0] == "flaeche" and masse["Beet"][1] == pytest.approx(200, rel=0.01)
    assert "20,0 m lang" in sven.get(f"/bestand/{weg.get_json()['id']}").get_data(as_text=True)
    # Eine Pflanzenkategorie passt nicht zu einem Objekt.
    assert sende(sven, "/api/bestand", {"art": "objekt", "name": "x", "kategorie": "Obst",
                                        "geometrie": json.dumps(ORT)}).status_code == 422


def test_liste_karte_aendern_und_entfernen(app, sven, pflanze):
    assert "Apfelbaum" in sven.get("/bestand").get_data(as_text=True)
    karte = sven.get("/karte").get_data(as_text=True)
    daten = json.loads(karte.split('id="daten">')[1].split("</script>")[0])
    assert [b["name"] for b in daten["bestand"]] == ["Apfelbaum"]
    assert "1 Eintrag" in karte

    neu = {"name": "Alter Apfelbaum", "kategorie": "Obst", "standort_notiz": "am Zaun",
           "geometrie": json.dumps({"type": "Point", "coordinates": [9.3836, 52.2851]})}
    assert sende(sven, f"/api/bestand/{pflanze}", neu).status_code == 200
    seite = sven.get(f"/bestand/{pflanze}").get_data(as_text=True)
    assert "Alter Apfelbaum" in seite and "am Zaun" in seite
    assert sven.get(f"/bestand/{pflanze}/bearbeiten").status_code == 200

    assert sende(sven, f"/api/bestand/{pflanze}/entfernen").status_code == 200
    assert "Alter Apfelbaum" not in sven.get("/bestand").get_data(as_text=True)
    assert sven.get(f"/bestand/{pflanze}").status_code == 404
    # Der Verlauf bleibt in der Datenbank erhalten.
    assert zeile(app, "SELECT archiviert FROM bestand WHERE id = ?", pflanze)[0]["archiviert"] == 1


def test_eigene_gartenflaeche(sven, garten):
    antwort = sende(sven, f"/api/gaerten/{garten}/flaeche",
                    {"geometrie": json.dumps({"type": "Polygon", "coordinates": [RECHTECK]})})
    assert antwort.status_code == 200
    assert antwort.get_json()["flaeche_m2"] == pytest.approx(200, rel=0.01)
    assert antwort.get_json()["umfang_m"] == pytest.approx(60, rel=0.01)
    seite = sven.get("/karte").get_data(as_text=True)
    assert "200 m²" in seite
    daten = json.loads(seite.split('id="daten">')[1].split("</script>")[0])
    assert len(daten["garten"]["umriss"]) == 4 and daten["garten"]["umriss_flurstuecke"]

    # Eine Linie ist keine Fläche.
    assert sende(sven, f"/api/gaerten/{garten}/flaeche",
                 {"geometrie": json.dumps({"type": "LineString", "coordinates": RECHTECK[:2]})}).status_code == 422
    # Löschen bringt die Flurstücksgrenze zurück.
    assert sende(sven, f"/api/gaerten/{garten}/flaeche", {"entfernen": "1"}).status_code == 200
    assert "1.317 m²" in sven.get("/karte").get_data(as_text=True)
