import json

from .conftest import FLURSTUECK, NACHBAR, melde_an


def test_ohne_garten_beginnt_man_beim_anlegen(sven):
    antwort = sven.get("/karte")
    assert antwort.status_code == 302
    assert antwort.headers["Location"] == "/garten/neu"
    assert "Schritt 1 von 2" in sven.get("/garten/neu").get_data(as_text=True)


def test_garten_anlegen_mit_flurstueck(sven, garten):
    seite = sven.get("/karte").get_data(as_text=True)
    assert "Testgarten" in seite
    assert "1.317 m²" in seite
    daten = json.loads(seite.split('id="daten">')[1].split("</script>")[0])
    assert daten["garten"]["flurstuecke"] == [FLURSTUECK]
    assert daten["garten"]["grenze"]["type"] == "MultiPolygon"
    assert daten["garten"]["ansicht"] is None
    # Ein einzelnes Flurstück: jede Kante gehört zum Umriss.
    ring = daten["garten"]["grenze"]["coordinates"][0][0]
    assert len(daten["garten"]["umriss"]) == len(ring) - 1


def test_flaeche_ist_die_summe_der_flurstuecke(sven):
    antwort = sven.post(
        "/api/gaerten", json={"name": "Zwei", "flurstuecke": [FLURSTUECK, NACHBAR, FLURSTUECK]}, headers=sven.kopf
    )
    assert antwort.status_code == 201
    assert "2.788 m² · 2 Flurstücke" in sven.get("/karte").get_data(as_text=True)


def test_eingaben_werden_geprueft(sven):
    def sende(daten):
        return sven.post("/api/gaerten", json=daten, headers=sven.kopf)

    assert sende({"name": "", "flurstuecke": [FLURSTUECK]}).status_code == 422
    assert sende({"name": "Ohne Flurstück", "flurstuecke": []}).status_code == 422
    assert sende({"name": "Unbekannt", "flurstuecke": ["gibt-es-nicht"]}).status_code == 422
    assert sende({"name": "x" * 81, "flurstuecke": [FLURSTUECK]}).status_code == 422
    assert "Namen" in sende({"flurstuecke": [FLURSTUECK]}).get_json()["fehler"]


def test_ohne_csrf_wird_nichts_gespeichert(sven):
    antwort = sven.post("/api/gaerten", json={"name": "Test", "flurstuecke": [FLURSTUECK]})
    assert antwort.status_code == 400
    assert sven.get("/karte").headers["Location"] == "/garten/neu"


def test_ansicht_merken_und_zuruecksetzen(sven, garten):
    ansicht = {"lat": 52.2850, "lon": 9.3835, "zoom": 19.5}
    antwort = sven.put(f"/api/gaerten/{garten}/ansicht", json=ansicht, headers=sven.kopf)
    assert antwort.status_code == 200
    seite = sven.get("/karte").get_data(as_text=True)
    assert json.loads(seite.split('id="daten">')[1].split("</script>")[0])["garten"]["ansicht"] == ansicht

    assert sven.delete(f"/api/gaerten/{garten}/ansicht", headers=sven.kopf).status_code == 200
    seite = sven.get("/karte").get_data(as_text=True)
    assert json.loads(seite.split('id="daten">')[1].split("</script>")[0])["garten"]["ansicht"] is None


def test_ansicht_ausserhalb_von_feggendorf_wird_abgelehnt(sven, garten):
    for ansicht in ({"lat": 48.1, "lon": 11.5, "zoom": 18}, {"lat": 52.285, "lon": 9.38, "zoom": 40}, {"lat": "x"}):
        assert sven.put(f"/api/gaerten/{garten}/ansicht", json=ansicht, headers=sven.kopf).status_code == 422


def test_garten_aendern(sven, garten):
    sven.put(f"/api/gaerten/{garten}/ansicht", json={"lat": 52.285, "lon": 9.3835, "zoom": 19}, headers=sven.kopf)

    # Nur der Name ändert sich: die gemerkte Ansicht bleibt.
    antwort = sven.put(
        f"/api/gaerten/{garten}", json={"name": "Neuer Name", "flurstuecke": [FLURSTUECK]}, headers=sven.kopf
    )
    assert antwort.status_code == 200
    seite = sven.get("/karte").get_data(as_text=True)
    assert "Neuer Name" in seite
    assert '"zoom": 19' in seite or '"zoom":19' in seite

    # Andere Flurstücke: die alte Ansicht passt nicht mehr und wird verworfen.
    sven.put(f"/api/gaerten/{garten}", json={"name": "Neuer Name", "flurstuecke": [NACHBAR]}, headers=sven.kopf)
    seite = sven.get("/karte").get_data(as_text=True)
    assert json.loads(seite.split('id="daten">')[1].split("</script>")[0])["garten"]["ansicht"] is None
    assert "1.471 m²" in seite


def test_unbekannter_garten(sven):
    assert sven.put("/api/gaerten/99", json={"name": "x", "flurstuecke": [FLURSTUECK]}, headers=sven.kopf).status_code == 404
    assert sven.get("/garten/99/bearbeiten").status_code == 404


def test_beide_sehen_denselben_garten(app, sven, garten):
    johannes = app.test_client()
    assert melde_an(johannes, name="johannes").status_code == 303
    assert "Testgarten" in johannes.get("/karte").get_data(as_text=True)
    assert "Meister" in johannes.get("/mehr").get_data(as_text=True)


def test_alle_bereiche_oeffnen(sven, garten):
    for pfad in ("/heute", "/karte", "/bestand", "/mehr", f"/garten/{garten}/bearbeiten"):
        assert sven.get(pfad).status_code == 200, pfad
    assert sven.get("/").headers["Location"] == "/karte"
    assert sven.get("/gibt-es-nicht").status_code == 404
