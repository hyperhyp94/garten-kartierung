import io

from garten.db import verbinden

from .conftest import JPEG, foto, sende


def zeilen(app, sql, *werte):
    con = verbinden(app.config["DATENBANK"])
    try:
        return con.execute(sql, werte).fetchall()
    finally:
        con.close()


def eintrag(client, pflanze, **werte):
    return sende(client, "/api/eintraege", {"bestand_id": pflanze, **werte})


def test_beobachtung_mit_foto_und_zustand(app, sven, pflanze):
    antwort = eintrag(sven, pflanze, typ="beobachtung", unterart="Blüte", text="Volle Blüte", zustand="4",
                      bild=foto(), vorschau=foto("v.jpg"))
    assert antwort.status_code == 201
    assert antwort.get_json()["weiter"] == f"/bestand/{pflanze}"
    assert zeilen(app, "SELECT zustand FROM bestand WHERE id = ?", pflanze)[0]["zustand"] == 4

    medium = zeilen(app, "SELECT * FROM medien WHERE eintrag_id = ?", antwort.get_json()["id"])[0]
    assert medium["datei"] != "foto.jpg" and medium["datei"].endswith(".jpg")  # nie der Name vom Handy
    assert medium["vorschau"] != medium["datei"]
    bild = sven.get(f"/medien/{medium['datei']}")
    assert bild.data == JPEG and "immutable" in bild.headers["Cache-Control"]
    bild.close()

    seite = sven.get(f"/bestand/{pflanze}").get_data(as_text=True)
    assert "Blüte" in seite and "Volle Blüte" in seite and "Jahresvergleich" in seite


def test_fotos_nur_fuer_angemeldete(app, sven, pflanze):
    eintrag(sven, pflanze, typ="beobachtung", bild=foto(), vorschau=foto())
    datei = zeilen(app, "SELECT datei FROM medien")[0]["datei"]
    fremder = app.test_client()
    assert fremder.get(f"/medien/{datei}").status_code == 302
    assert sven.get("/medien/../garten.db").status_code == 404


def test_leere_und_falsche_eintraege_werden_abgelehnt(sven, pflanze):
    faelle = [
        dict(typ="beobachtung"),  # nichts drin
        dict(typ="massnahme"),
        dict(typ="frage"),  # ohne Text
        dict(typ="wissen", titel="Nur Titel"),
        dict(typ="zustand"),  # ohne Zustand
        dict(typ="beobachtung", unterart="Mondphase"),
        dict(typ="beobachtung", text="x", zustand="7"),
        dict(typ="beobachtung", text="x", datum="2030-01-01"),  # Zukunft
        dict(typ="beobachtung", text="x", datum="gestern"),
        dict(typ="gedicht", text="x"),
    ]
    for fall in faelle:
        assert eintrag(sven, pflanze, **fall).status_code == 422, fall
    assert sende(sven, "/api/eintraege", {"bestand_id": 999, "typ": "beobachtung", "text": "x"}).status_code == 404


def test_upload_wird_geprueft(app, sven, pflanze):
    kein_bild = eintrag(sven, pflanze, typ="beobachtung", bild=(io.BytesIO(b"<html>"), "boese.jpg"))
    assert kein_bild.status_code == 422

    zu_gross = eintrag(sven, pflanze, typ="beobachtung",
                       bild=(io.BytesIO(JPEG + b"\x00" * (10 * 1024 * 1024)), "riesig.jpg"))
    assert zu_gross.status_code == 413
    assert "10 MB" in zu_gross.get_json()["fehler"]

    kein_video = eintrag(sven, pflanze, typ="beobachtung", video=(io.BytesIO(b"MZ" + b"\x00" * 50), "virus.mp4"))
    assert kein_video.status_code == 422

    # Nach abgelehnten Uploads liegt nichts herum und es gibt keinen halben Eintrag.
    assert zeilen(app, "SELECT 1 FROM medien") == []
    assert zeilen(app, "SELECT 1 FROM eintraege WHERE typ = 'beobachtung'") == []
    assert list((app.config["DATEN"] / "uploads").glob("*")) == []


def test_video_wird_gespeichert(app, sven, pflanze):
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
    antwort = eintrag(sven, pflanze, typ="wissen", titel="Schnitt erklärt", text="Siehe Video",
                      video=(io.BytesIO(mp4), "film.mp4"))
    assert antwort.status_code == 201
    medium = zeilen(app, "SELECT * FROM medien")[0]
    assert medium["art"] == "video" and medium["datei"].endswith(".mp4")
    teil = sven.get(f"/medien/{medium['datei']}", headers={"Range": "bytes=0-9"})
    assert teil.status_code == 206 and len(teil.data) == 10  # Videos lassen sich in Stücken abrufen
    teil.close()


def test_frage_und_antwort(app, sven, johannes, pflanze):
    frage = eintrag(sven, pflanze, typ="frage", text="Wo soll ich schneiden?", bild=foto(), vorschau=foto())
    assert frage.status_code == 201
    frage_id = frage.get_json()["id"]

    # Johannes sieht die offene Frage auf seiner Startseite. Sven sieht dort seine eigene Frage nicht.
    assert "Wo soll ich schneiden?" in johannes.get("/heute").get_data(as_text=True)
    assert "Fragen an dich" not in sven.get("/heute").get_data(as_text=True)
    formular = johannes.get(f"/eintrag/neu?typ=antwort&antwort_auf={frage_id}").get_data(as_text=True)
    assert "Ins Bild zeichnen" in formular

    antwort = eintrag(johannes, pflanze, typ="antwort", antwort_auf=frage_id, text="Direkt am Astring.",
                      bild=foto("gezeichnet.jpg"), vorschau=foto())
    assert antwort.status_code == 201
    assert zeilen(app, "SELECT offen FROM eintraege WHERE id = ?", frage_id)[0]["offen"] == 0
    assert "Fragen an dich" not in johannes.get("/heute").get_data(as_text=True)
    heute = sven.get("/heute").get_data(as_text=True)
    assert "Neue Antworten" in heute and "Direkt am Astring." in heute
    assert "Direkt am Astring." in sven.get(f"/bestand/{pflanze}").get_data(as_text=True)

    # Eine Antwort ohne Inhalt oder auf eine fremde Frage gibt es nicht.
    assert eintrag(johannes, pflanze, typ="antwort", antwort_auf=frage_id).status_code == 422
    assert eintrag(johannes, pflanze, typ="antwort", antwort_auf=999, text="x").status_code == 404

    # Wird die Antwort gelöscht, ist die Frage wieder offen.
    assert sende(johannes, f"/api/eintraege/{antwort.get_json()['id']}/loeschen").status_code == 200
    assert zeilen(app, "SELECT offen FROM eintraege WHERE id = ?", frage_id)[0]["offen"] == 1


def test_loeschen_darf_nur_wer_geschrieben_hat_oder_der_meister(app, sven, johannes, pflanze):
    von_johannes = eintrag(johannes, pflanze, typ="wissen", titel="Sorte", text="Boskoop").get_json()["id"]
    von_sven = eintrag(sven, pflanze, typ="beobachtung", unterart="Knospe", zustand="5", bild=foto(),
                       vorschau=foto()).get_json()["id"]

    assert sende(sven, f"/api/eintraege/{von_johannes}/loeschen").status_code == 403
    assert len(list((app.config["DATEN"] / "uploads").glob("*"))) == 2
    assert sende(johannes, f"/api/eintraege/{von_sven}/loeschen").status_code == 200
    # Fotos sind weg, und der Zustand der Pflanze fällt auf den letzten verbliebenen zurück.
    assert list((app.config["DATEN"] / "uploads").glob("*")) == []
    assert zeilen(app, "SELECT zustand FROM bestand WHERE id = ?", pflanze)[0]["zustand"] is None
    assert sende(johannes, "/api/eintraege/999/loeschen").status_code == 404


def test_formulare_oeffnen(sven, pflanze):
    for typ in ("beobachtung", "massnahme", "wissen", "frage"):
        assert sven.get(f"/eintrag/neu?typ={typ}&bestand={pflanze}").status_code == 200, typ
    # Ohne Pflanze fragt die Seite zuerst, zu welcher der Eintrag gehört.
    assert "Zu welcher Pflanze?" in sven.get("/eintrag/neu?typ=massnahme").get_data(as_text=True)


def test_doppelt_gesendetes_formular_legt_nur_einen_eintrag_an(app, sven, pflanze):
    daten = dict(typ="beobachtung", unterart="Knospe", _schluessel="b6c1d7f0-1111-4222-8333-444455556666")
    erste = eintrag(sven, pflanze, **daten, bild=foto(), vorschau=foto())
    zweite = eintrag(sven, pflanze, **daten, bild=foto(), vorschau=foto())  # Handy sendet nach Funkloch noch einmal
    assert erste.status_code == 201 and zweite.status_code == 200
    assert zweite.get_json() == erste.get_json()
    assert len(zeilen(app, "SELECT 1 FROM eintraege WHERE unterart = 'Knospe'")) == 1
    assert len(zeilen(app, "SELECT 1 FROM medien")) == 1
    # Ein abgelehntes Formular wird nicht gemerkt und darf korrigiert noch einmal kommen.
    assert eintrag(sven, pflanze, typ="frage", _schluessel="korrektur-123456").status_code == 422
    assert eintrag(sven, pflanze, typ="frage", text="Jetzt mit Text", _schluessel="korrektur-123456").status_code == 201
