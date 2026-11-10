from garten.db import verbinden

from .conftest import PASSWORT, csrf, melde_an


def test_ohne_anmeldung_geht_es_zur_anmeldung(client):
    antwort = client.get("/karte")
    assert antwort.status_code == 302
    assert antwort.headers["Location"].startswith("/anmelden")
    assert client.get("/api/flurstuecke").status_code == 401
    assert client.get("/kacheln/luftbild/17/68955/43178.jpg").status_code == 401


def test_health_und_app_huelle_sind_offen(client):
    assert client.get("/health").get_json()["status"] == "ok"
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/offline").status_code == 200


def test_anmelden_und_abmelden(client):
    assert melde_an(client).status_code == 303
    assert client.get("/mehr", follow_redirects=True).status_code == 200
    antwort = client.post("/abmelden", data={"csrf": csrf(client, "/mehr")})
    assert antwort.status_code == 303
    assert client.get("/karte").status_code == 302


def test_falsches_passwort(client):
    antwort = melde_an(client, passwort="falsch")
    assert antwort.status_code == 401
    assert "stimmt nicht" in antwort.get_data(as_text=True)
    assert client.get("/karte").status_code == 302


def test_unbekannter_nutzer_bekommt_dieselbe_meldung(client):
    antwort = melde_an(client, name="fremder")
    assert antwort.status_code == 401
    assert "stimmt nicht" in antwort.get_data(as_text=True)


def test_ohne_csrf_keine_anmeldung(client):
    antwort = client.post("/anmelden", data={"benutzername": "sven", "passwort": PASSWORT})
    assert antwort.status_code == 400


def test_sperre_nach_fuenf_fehlversuchen(client):
    for _ in range(5):
        assert melde_an(client, passwort="falsch").status_code == 401
    antwort = melde_an(client)  # jetzt hilft auch das richtige Passwort nicht
    assert antwort.status_code == 401
    assert "Zu viele Fehlversuche" in antwort.get_data(as_text=True)
    # Johannes ist davon nicht betroffen.
    assert melde_an(client, name="johannes").status_code == 303


def test_sperre_laeuft_ab(app, client):
    for _ in range(5):
        melde_an(client, passwort="falsch")
    con = verbinden(app.config["DATENBANK"])
    con.execute("UPDATE nutzer SET gesperrt_bis = '2000-01-01T00:00:00+00:00' WHERE benutzername = 'sven'")
    con.commit()
    con.close()
    assert melde_an(client).status_code == 303


def test_konto_ohne_passwort_ist_gesperrt(app, client):
    con = verbinden(app.config["DATENBANK"])
    con.execute("UPDATE nutzer SET passwort_hash = NULL WHERE benutzername = 'sven'")
    con.commit()
    con.close()
    antwort = melde_an(client)
    assert antwort.status_code == 401
    assert "noch kein Passwort" in antwort.get_data(as_text=True)


def test_neues_passwort_beendet_alte_sitzungen(app, sven):
    assert sven.get("/mehr", follow_redirects=True).status_code == 200
    ergebnis = app.test_cli_runner().invoke(args=["passwort", "sven"], input="ganz-neues-passwort\n")
    assert ergebnis.exit_code == 0, ergebnis.output
    assert sven.get("/mehr").status_code == 302
    assert melde_an(sven, passwort="ganz-neues-passwort").status_code == 303


def test_zu_kurzes_passwort_wird_abgelehnt(app):
    ergebnis = app.test_cli_runner().invoke(args=["passwort", "sven"], input="kurz\n")
    assert ergebnis.exit_code != 0
    assert "mindestens" in ergebnis.output


def test_weiterleitung_bleibt_in_der_app(client):
    antwort = client.post(
        "/anmelden",
        data={"benutzername": "sven", "passwort": PASSWORT, "csrf": csrf(client), "weiter": "https://boese.example/"},
    )
    assert antwort.status_code == 303
    assert antwort.headers["Location"] == "/"
    client.post("/abmelden", data={"csrf": csrf(client, "/mehr")})
    antwort = client.post(
        "/anmelden",
        data={"benutzername": "sven", "passwort": PASSWORT, "csrf": csrf(client), "weiter": "/mehr"},
    )
    assert antwort.headers["Location"] == "/mehr"


def test_cookie_ist_nur_ueber_https_secure(client):
    antwort = client.get("/anmelden")
    assert "Secure" not in antwort.headers["Set-Cookie"]
    assert "HttpOnly" in antwort.headers["Set-Cookie"]
    hinter_tunnel = client.application.test_client()
    antwort = hinter_tunnel.get("/anmelden", headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in antwort.headers["Set-Cookie"]


def test_sicherheits_kopfzeilen(client):
    antwort = client.get("/anmelden")
    assert "frame-ancestors 'none'" in antwort.headers["Content-Security-Policy"]
    assert antwort.headers["X-Content-Type-Options"] == "nosniff"
    assert antwort.headers["Cache-Control"] == "no-store"


def test_ohne_anmeldung_kein_upload(client):
    import io
    gross = {"bestand_id": "1", "typ": "beobachtung", "bild": (io.BytesIO(b"\xff\xd8\xff" + b"0" * 200_000), "f.jpg")}
    # Die App am Handy muss „nicht angemeldet“ erfahren, damit sie den Eintrag behält und später sendet.
    antwort = client.post("/api/eintraege", data=gross, content_type="multipart/form-data")
    assert antwort.status_code == 401
    # Am Anmeldeformular selbst wird nichts Großes angenommen.
    gross["bild"] = (io.BytesIO(b"0" * 200_000), "f.jpg")
    assert client.post("/anmelden", data=gross, content_type="multipart/form-data").status_code == 413
