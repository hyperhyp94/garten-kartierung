from datetime import date

from garten.aufgaben import dringlichkeit, naechste_faelligkeit
from garten.db import verbinden
from garten.lexikon import erster_termin, plus_monate

from .conftest import HEUTE, foto, lege_pflanze_an, sende


def zeilen(app, sql, *werte):
    con = verbinden(app.config["DATENBANK"])
    try:
        return con.execute(sql, werte).fetchall()
    finally:
        con.close()


def aufgabe(client, pflanze, **werte):
    daten = {"bestand_id": pflanze, "titel": "Totholz entfernen", "faellig_am": "2027-01-20", **werte}
    antwort = sende(client, "/api/aufgaben", daten)
    assert antwort.status_code == 201, antwort.get_json()
    return antwort.get_json()["id"]


def test_dringlichkeit():
    def stufe(tag, zustand=None, fest=False):
        return dringlichkeit(tag, zustand, fest, HEUTE)

    assert stufe(date(2027, 1, 3)) == ("jetzt", "überfällig seit 12 Tagen")
    assert stufe(date(2027, 1, 14)) == ("jetzt", "überfällig seit gestern")
    assert stufe(HEUTE) == ("jetzt", "heute fällig")
    # In 10 Tagen fällig: bei gutem Zustand „Bald“, bei schlechtem „Jetzt“.
    assert stufe(date(2027, 1, 25), zustand=4) == ("bald", "fällig in 10 Tagen")
    assert stufe(date(2027, 1, 25), zustand=2) == ("jetzt", "fällig in 10 Tagen, Zustand 2")
    # Schlechter Zustand allein macht eine ferne Aufgabe nicht dringend.
    assert stufe(date(2027, 2, 10), zustand=1)[0] == "bald"
    assert stufe(date(2027, 2, 14))[0] == "bald"
    assert stufe(date(2027, 2, 15)) == ("spaeter", "fällig in 31 Tagen")
    assert stufe(date(2027, 6, 1)) == ("spaeter", "fällig am 01.06.2027")
    # Der Meister kann jede Aufgabe nach vorn holen.
    assert stufe(date(2027, 6, 1), fest=True) == ("jetzt", "fällig am 01.06.2027, vom Meister festgelegt")


def test_folgetermin_bleibt_in_der_jahreszeit():
    # Der Winterschnitt vom Februar wird erst im April erledigt: nächstes Mal wieder im Februar.
    assert naechste_faelligkeit(date(2027, 2, 1), 12, date(2027, 4, 10)) == date(2028, 2, 1)
    # Lange liegen geblieben: der Folgetermin liegt trotzdem in der Zukunft.
    assert naechste_faelligkeit(date(2025, 2, 1), 12, date(2027, 4, 10)) == date(2028, 2, 1)
    assert plus_monate(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert plus_monate(date(2027, 11, 15), 3) == date(2028, 2, 15)


def test_erster_termin_richtet_sich_nach_dem_zeitraum():
    assert erster_termin(2, 3, date(2027, 1, 15)) == date(2027, 2, 1)
    assert erster_termin(2, 3, date(2027, 2, 20)) == date(2027, 2, 27)  # läuft gerade: in einer Woche
    assert erster_termin(2, 3, date(2027, 5, 1)) == date(2028, 2, 1)
    assert erster_termin(11, 2, date(2027, 1, 10)) == date(2027, 1, 17)  # Zeitraum über den Jahreswechsel
    assert erster_termin(None, None, date(2027, 1, 15)) == date(2027, 2, 14)


def test_heute_sortiert_nach_dringlichkeit(app, sven, pflanze):
    kranke = lege_pflanze_an(sven, name="Kranke Rose", kategorie="Strauch", zustand="1")
    aufgabe(sven, pflanze, titel="Später dran", faellig_am="2027-06-01")
    aufgabe(sven, pflanze, titel="Bald dran", faellig_am="2027-01-25")
    aufgabe(sven, pflanze, titel="Überfällig", faellig_am="2027-01-03")
    aufgabe(sven, kranke, titel="Kranke zuerst", faellig_am="2027-01-25")

    seite = sven.get("/heute").get_data(as_text=True)
    stellen = [seite.index(t) for t in ("Kranke zuerst", "Überfällig", "Bald dran", "Später dran")]
    assert stellen == sorted(stellen)
    assert "überfällig seit 12 Tagen" in seite
    assert "fällig in 10 Tagen, Zustand 1" in seite


def test_erledigen_mit_vorher_nachher_und_folgetermin(app, sven, pflanze):
    nr = aufgabe(sven, pflanze, intervall_monate="12", anleitung_id="1")
    assert "Anleitung" in sven.get(f"/aufgabe/{nr}").get_data(as_text=True)

    # Vor der Arbeit: Vorher-Foto. Es hängt erst an der Aufgabe.
    assert sende(sven, f"/api/aufgaben/{nr}/vorher", {"bild": foto(), "vorschau": foto()}).status_code == 201
    assert zeilen(app, "SELECT kennzeichen, eintrag_id FROM medien")[0]["kennzeichen"] == "vorher"
    assert "Vorher" in sven.get(f"/eintrag/neu?aufgabe={nr}").get_data(as_text=True)

    antwort = sende(sven, "/api/eintraege", {
        "bestand_id": pflanze, "typ": "massnahme", "aufgabe_id": nr, "text": "Drei Äste entfernt", "zustand": "4",
        "bild": foto(), "vorschau": foto(), "kennzeichen": "nachher",
    })
    assert antwort.status_code == 201
    assert antwort.get_json()["weiter"] == "/heute"

    erledigt = zeilen(app, "SELECT * FROM aufgaben WHERE id = ?", nr)[0]
    assert erledigt["erledigt_am"] == HEUTE.isoformat()
    folge = zeilen(app, "SELECT * FROM aufgaben WHERE erledigt_am IS NULL")
    assert len(folge) == 1
    assert folge[0]["faellig_am"] == "2028-01-20" and folge[0]["titel"] == "Totholz entfernen"
    assert folge[0]["anleitung_id"] == 1 and folge[0]["intervall_monate"] == 12

    # Beide Fotos gehören jetzt zum Eintrag, der Zustand ist übernommen.
    marken = {m["kennzeichen"] for m in zeilen(app, "SELECT * FROM medien WHERE eintrag_id = ?",
                                              antwort.get_json()["id"])}
    assert marken == {"vorher", "nachher"}
    assert zeilen(app, "SELECT zustand FROM bestand WHERE id = ?", pflanze)[0]["zustand"] == 4
    # Zweimal erledigen geht nicht.
    doppelt = sende(sven, "/api/eintraege", {"bestand_id": pflanze, "typ": "massnahme", "aufgabe_id": nr})
    assert doppelt.status_code == 409


def test_einmalige_aufgabe_hat_keinen_folgetermin(app, sven, pflanze):
    nr = aufgabe(sven, pflanze)
    sende(sven, "/api/eintraege", {"bestand_id": pflanze, "typ": "massnahme", "aufgabe_id": nr})
    assert zeilen(app, "SELECT 1 FROM aufgaben WHERE erledigt_am IS NULL") == []


def test_verschieben_aendern_loeschen(app, sven, pflanze):
    nr = aufgabe(sven, pflanze, faellig_am="2027-01-03")
    # Eine überfällige Aufgabe wird ab heute verschoben, nicht ab dem alten Termin.
    assert sende(sven, f"/api/aufgaben/{nr}/verschieben", {"tage": "7"}).get_json()["faellig_am"] == "2027-01-22"
    assert sende(sven, f"/api/aufgaben/{nr}/verschieben", {"tage": "365"}).status_code == 422

    assert sende(sven, f"/api/aufgaben/{nr}", {"titel": "Neuer Titel", "faellig_am": "2027-03-01",
                                               "hinweis": "Vorsicht, Nest"}).status_code == 200
    seite = sven.get(f"/aufgabe/{nr}").get_data(as_text=True)
    assert "Neuer Titel" in seite and "Vorsicht, Nest" in seite
    for kaputt in ({"titel": ""}, {"faellig_am": "bald"}, {"intervall_monate": "5"}, {"anleitung_id": "999"}):
        daten = {"bestand_id": pflanze, "titel": "x", "faellig_am": "2027-03-01", **kaputt}
        assert sende(sven, "/api/aufgaben", daten).status_code == 422, kaputt

    assert sende(sven, f"/api/aufgaben/{nr}/loeschen").status_code == 200
    assert sven.get(f"/aufgabe/{nr}").status_code == 404


def test_nur_der_meister_legt_jetzt_fest(app, sven, johannes, pflanze):
    nr = aufgabe(sven, pflanze, faellig_am="2027-06-01", fest_jetzt="1")  # Sven versucht es beim Anlegen
    assert zeilen(app, "SELECT fest_jetzt FROM aufgaben WHERE id = ?", nr)[0]["fest_jetzt"] == 0
    assert sende(sven, f"/api/aufgaben/{nr}/fest", {"fest": "1"}).status_code == 403

    assert sende(johannes, f"/api/aufgaben/{nr}/fest", {"fest": "1"}).status_code == 200
    assert "vom Meister festgelegt" in sven.get("/heute").get_data(as_text=True)
    # Ändert Sven danach den Titel, bleibt die Festlegung des Meisters bestehen.
    sende(sven, f"/api/aufgaben/{nr}", {"titel": "Anders", "faellig_am": "2027-06-01"})
    assert zeilen(app, "SELECT fest_jetzt FROM aufgaben WHERE id = ?", nr)[0]["fest_jetzt"] == 1


def test_anleitungen_pflegt_nur_der_meister(app, sven, johannes):
    neu = {"titel": "Teich reinigen", "schritte": "Laub abfischen\n\nPumpe prüfen", "monat_von": "4"}
    assert sende(sven, "/api/anleitungen", neu).status_code == 403
    assert sven.get("/anleitung/neu").status_code == 403
    assert sven.get("/anleitung/1/bearbeiten").status_code == 403
    assert "Anleitung ändern" not in sven.get("/anleitung/1").get_data(as_text=True)

    antwort = sende(johannes, "/api/anleitungen", neu)
    assert antwort.status_code == 201
    seite = sven.get(antwort.get_json()["weiter"]).get_data(as_text=True)
    assert "Teich reinigen" in seite and "Pumpe prüfen" in seite and "April" in seite

    assert sende(johannes, "/api/anleitungen/1", {"titel": "Obstbaum, eigene Fassung", "schritte": "Nur ein Schritt"}
                 ).status_code == 200
    assert sende(johannes, "/api/anleitungen/1", {"titel": "", "schritte": "x"}).status_code == 422
    # Die geänderte Vorlage wird beim nächsten Start nicht überschrieben.
    from garten.lexikon import saee_anleitungen
    con = verbinden(app.config["DATENBANK"])
    saee_anleitungen(con)
    assert con.execute("SELECT titel FROM anleitungen WHERE id = 1").fetchone()[0] == "Obstbaum, eigene Fassung"
    assert con.execute("SELECT COUNT(*) FROM anleitungen").fetchone()[0] == 19
    con.close()


def test_rundgang_fuehrt_von_pflanze_zu_pflanze(app, sven, garten):
    import json
    nah = lege_pflanze_an(sven, name="Erste")
    fern = lege_pflanze_an(sven, name="Weit weg",
                           geometrie=json.dumps({"type": "Point", "coordinates": [9.3850, 52.2860]}))
    mitte = lege_pflanze_an(sven, name="Daneben",
                            geometrie=json.dumps({"type": "Point", "coordinates": [9.38352, 52.28501]}))
    # Frisch erfasste Pflanzen haben noch keinen Zustand und stehen deshalb alle an.
    assert "3 Pflanzen brauchen" in sven.get("/heute").get_data(as_text=True)
    seite = sven.get("/rundgang").get_data(as_text=True)
    assert "Noch 3 von 3" in seite and "<h2>Erste</h2>" in seite

    antwort = sende(sven, "/api/eintraege", {"bestand_id": nah, "typ": "zustand", "unterart": "Rundgang",
                                             "zustand": "4", "weiter": "/rundgang"})
    assert antwort.get_json()["weiter"] == "/rundgang"
    # Als Nächstes kommt die Pflanze direkt daneben, nicht die am anderen Ende.
    seite = sven.get("/rundgang").get_data(as_text=True)
    assert "Noch 2 von 3" in seite and "<h2>Daneben</h2>" in seite
    assert "<h2>Weit weg</h2>" in sven.get(f"/rundgang?ohne={mitte}").get_data(as_text=True)

    for nr in (mitte, fern):
        sende(sven, "/api/eintraege", {"bestand_id": nr, "typ": "zustand", "unterart": "Rundgang", "zustand": "3"})
    assert "Rundgang fertig" in sven.get("/rundgang").get_data(as_text=True)
    assert "Rundgang</strong>" not in sven.get("/heute").get_data(as_text=True)


def test_kalender_mit_zwei_erinnerungen(app, sven, pflanze):
    aufgabe(sven, pflanze, titel="Hecke schneiden; Vögel beachten", anleitung_id="3", faellig_am="2027-06-25")
    erledigte = aufgabe(sven, pflanze, titel="Schon erledigt")
    sende(sven, "/api/eintraege", {"bestand_id": pflanze, "typ": "massnahme", "aufgabe_id": erledigte})

    seite = sven.get("/kalender").get_data(as_text=True)
    token = zeilen(app, "SELECT kalender_token FROM gaerten")[0]["kalender_token"]
    assert f"/kalender/{token}.ics" in seite and "webcal://" in seite

    # Die Kalender-App ist nicht angemeldet. Der Schlüssel in der Adresse reicht, ein falscher nicht.
    fremd = app.test_client()
    datei = fremd.get(f"/kalender/{token}.ics")
    assert datei.status_code == 200 and datei.mimetype == "text/calendar"
    assert fremd.get("/kalender/falsch.ics").status_code == 404
    text = datei.get_data(as_text=True)

    assert text.count("BEGIN:VEVENT") == 1  # nur offene Aufgaben
    assert text.count("BEGIN:VALARM") == 2
    assert "TRIGGER:-P1D" in text and "TRIGGER:-PT1H" in text
    assert "DTSTART:20270625T090000" in text
    assert "SUMMARY:Hecke schneiden\\; Vögel beachten · Apfelbaum" in text
    assert "\r\n" in text and all(len(z.encode()) <= 75 for z in text.split("\r\n"))
    assert "Vogelnester" in text.replace("\r\n ", "")
