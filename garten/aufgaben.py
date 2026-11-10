"""Pflegeaufgaben, Dringlichkeit, Anleitungen, Rundgang, Kalender und die Seite „Heute“."""

import secrets
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, Response, current_app, g, jsonify, redirect, render_template, request, url_for

from .anmeldung import nur_meister
from .db import hole_db
from .fehler import Eingabefehler
from .gaerten import aktueller_garten
from .geo import abstand_m
from .lexikon import erster_termin, plus_monate, zeitraum

bp = Blueprint("aufgaben", __name__)

STUFEN = {"jetzt": "Jetzt", "bald": "Bald", "spaeter": "Später"}
RUNDGANG_TAGE = 30  # nach so vielen Tagen gilt ein Zustand als veraltet
INTERVALLE = [(None, "Einmalig"), (1, "Jeden Monat"), (3, "Alle 3 Monate"), (6, "Alle 6 Monate"),
              (12, "Jedes Jahr"), (24, "Alle 2 Jahre"), (36, "Alle 3 Jahre")]


def heute() -> date:
    return current_app.config.get("HEUTE") or date.today()


def als_datum(text: str) -> date:
    return date.fromisoformat(text)


def schoen(tag: date | str) -> str:
    """15.02.2027"""
    if isinstance(tag, str):
        tag = als_datum(tag[:10])
    return tag.strftime("%d.%m.%Y")


# ---------- Dringlichkeit ----------


def dringlichkeit(faellig: date, zustand: int | None, fest: bool, stichtag: date) -> tuple[str, str]:
    """Ordnet eine Aufgabe in Jetzt, Bald oder Später ein und nennt den Grund im Klartext.

    Jetzt: fällig oder überfällig, oder fällig in 14 Tagen bei Zustand 1 oder 2, oder vom Meister festgelegt.
    Bald: fällig in den nächsten 30 Tagen. Später: alles andere.
    """
    tage = (faellig - stichtag).days
    if tage < -1:
        wann = f"überfällig seit {-tage} Tagen"
    elif tage == -1:
        wann = "überfällig seit gestern"
    elif tage == 0:
        wann = "heute fällig"
    elif tage == 1:
        wann = "morgen fällig"
    elif tage <= 60:
        wann = f"fällig in {tage} Tagen"
    else:
        wann = f"fällig am {schoen(faellig)}"

    schlecht = zustand in (1, 2)
    if fest or tage <= 0 or (tage <= 14 and schlecht):
        stufe = "jetzt"
    elif tage <= 30:
        stufe = "bald"
    else:
        stufe = "spaeter"

    gruende = [wann]
    if schlecht:
        gruende.append(f"Zustand {zustand}")
    if fest:
        gruende.append("vom Meister festgelegt")
    return stufe, ", ".join(gruende)


def naechste_faelligkeit(faellig: date, intervall_monate: int, erledigt: date) -> date:
    """Folgetermin einer wiederkehrenden Aufgabe. Er bleibt in der Jahreszeit des ursprünglichen Termins."""
    tag = plus_monate(faellig, intervall_monate)
    while tag <= erledigt:
        tag = plus_monate(tag, intervall_monate)
    return tag


def offene_aufgaben(db, garten_id: int, bestand_id: int | None = None) -> list[dict]:
    """Alle offenen Aufgaben, die dringendste zuerst."""
    zeilen = db.execute(
        "SELECT a.*, b.name AS bestand_name, b.zustand AS bestand_zustand,"
        " (SELECT vorschau FROM medien m WHERE m.bestand_id = b.id AND m.art = 'bild' ORDER BY m.id DESC LIMIT 1)"
        " AS bild"
        " FROM aufgaben a JOIN bestand b ON b.id = a.bestand_id"
        " WHERE a.garten_id = ? AND a.erledigt_am IS NULL AND b.archiviert = 0"
        + (" AND a.bestand_id = ?" if bestand_id else ""),
        (garten_id, bestand_id) if bestand_id else (garten_id,),
    ).fetchall()
    stichtag = heute()
    rang = {"jetzt": 0, "bald": 1, "spaeter": 2}
    liste = []
    for z in zeilen:
        stufe, grund = dringlichkeit(als_datum(z["faellig_am"]), z["bestand_zustand"], bool(z["fest_jetzt"]), stichtag)
        liste.append({**dict(z), "stufe": stufe, "grund": grund})
    liste.sort(key=lambda a: (rang[a["stufe"]], a["bestand_zustand"] or 3, a["faellig_am"], a["id"]))
    return liste


def erledige(db, aufgabe, tag: date, nutzer_id: int) -> None:
    """Hakt eine Aufgabe ab und legt bei einem Intervall den Folgetermin an."""
    db.execute(
        "UPDATE aufgaben SET erledigt_am = ?, erledigt_von = ? WHERE id = ?", (tag.isoformat(), nutzer_id, aufgabe["id"])
    )
    if aufgabe["intervall_monate"]:
        folgt = naechste_faelligkeit(als_datum(aufgabe["faellig_am"]), aufgabe["intervall_monate"], tag)
        db.execute(
            "INSERT INTO aufgaben (garten_id, bestand_id, anleitung_id, titel, hinweis, faellig_am, intervall_monate,"
            " erstellt_von) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (aufgabe["garten_id"], aufgabe["bestand_id"], aufgabe["anleitung_id"], aufgabe["titel"],
             aufgabe["hinweis"], folgt.isoformat(), aufgabe["intervall_monate"], nutzer_id),
        )


def lege_aus_anleitung_an(db, garten_id: int, bestand_id: int, schluessel: str, nutzer_id: int) -> None:
    """Legt für eine Pflanze aus dem Lexikon eine passende Pflegeaufgabe an."""
    anleitung = db.execute("SELECT * FROM anleitungen WHERE schluessel = ?", (schluessel,)).fetchone()
    if anleitung is None:
        return
    faellig = erster_termin(anleitung["monat_von"], anleitung["monat_bis"], heute())
    db.execute(
        "INSERT INTO aufgaben (garten_id, bestand_id, anleitung_id, titel, faellig_am, intervall_monate, erstellt_von)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (garten_id, bestand_id, anleitung["id"], anleitung["titel"], faellig.isoformat(),
         anleitung["intervall_monate"], nutzer_id),
    )


# ---------- Rundgang ----------


def rundgang_schlange(db, garten_id: int, ohne: set[int] = frozenset()) -> list:
    """Pflanzen, deren Zustand älter als 30 Tage ist, in sinnvoller Laufreihenfolge.

    Die nächste Pflanze ist immer die, die der zuletzt bewerteten am nächsten steht.
    """
    grenze = (heute() - timedelta(days=RUNDGANG_TAGE)).isoformat()
    zeilen = db.execute(
        "SELECT b.*, (SELECT MAX(e.datum) FROM eintraege e WHERE e.bestand_id = b.id AND e.zustand IS NOT NULL)"
        " AS zuletzt,"
        " (SELECT vorschau FROM medien m WHERE m.bestand_id = b.id AND m.art = 'bild' ORDER BY m.id DESC LIMIT 1)"
        " AS bild"
        " FROM bestand b WHERE b.garten_id = ? AND b.art = 'pflanze' AND b.archiviert = 0",
        (garten_id,),
    ).fetchall()
    offen = [z for z in zeilen if z["id"] not in ohne and (z["zuletzt"] is None or z["zuletzt"] <= grenze)]
    if not offen:
        return []
    letzte = db.execute(
        "SELECT b.lon, b.lat FROM eintraege e JOIN bestand b ON b.id = e.bestand_id"
        " WHERE e.garten_id = ? AND e.unterart = 'Rundgang' AND e.datum = ? ORDER BY e.id DESC LIMIT 1",
        (garten_id, heute().isoformat()),
    ).fetchone()
    ort = (letzte["lon"], letzte["lat"]) if letzte else (offen[0]["lon"], offen[0]["lat"])
    geordnet = []
    while offen:
        naechste = min(offen, key=lambda z: abstand_m(ort, (z["lon"], z["lat"])))
        offen.remove(naechste)
        geordnet.append(naechste)
        ort = (naechste["lon"], naechste["lat"])
    return geordnet


@bp.get("/rundgang")
def rundgang():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    try:
        ohne = {int(t) for t in request.args.get("ohne", "").split(",") if t}
    except ValueError:
        ohne = set()
    db = hole_db()
    schlange = rundgang_schlange(db, garten["id"], ohne)
    gesamt = db.execute(
        "SELECT COUNT(*) FROM bestand WHERE garten_id = ? AND art = 'pflanze' AND archiviert = 0", (garten["id"],)
    ).fetchone()[0]
    aktuell = schlange[0] if schlange else None
    return render_template(
        "rundgang.html",
        garten=garten,
        pflanze=aktuell,
        rest=len(schlange),
        gesamt=gesamt,
        ueberspringen=",".join(str(i) for i in sorted(ohne | {aktuell["id"]})) if aktuell else "",
        zurueck_zum_rundgang=url_for("aufgaben.rundgang", ohne=request.args.get("ohne") or None),
        tag=heute().isoformat(),
    )


# ---------- Heute ----------


@bp.get("/heute")
def heute_seite():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    db = hole_db()
    aufgaben = offene_aufgaben(db, garten["id"])
    gruppen = {stufe: [a for a in aufgaben if a["stufe"] == stufe] for stufe in STUFEN}
    ich = g.nutzer["id"]
    fragen = db.execute(
        "SELECT e.*, b.name AS bestand_name, n.anzeigename AS von,"
        " (SELECT vorschau FROM medien m WHERE m.eintrag_id = e.id AND m.art = 'bild' LIMIT 1) AS bild"
        " FROM eintraege e JOIN bestand b ON b.id = e.bestand_id JOIN nutzer n ON n.id = e.erstellt_von"
        " WHERE e.garten_id = ? AND e.typ = 'frage' AND e.offen = 1 AND e.erstellt_von != ? AND b.archiviert = 0"
        " ORDER BY e.id",
        (garten["id"], ich),
    ).fetchall()
    seit = (heute() - timedelta(days=14)).isoformat()
    antworten = db.execute(
        "SELECT a.*, b.name AS bestand_name, n.anzeigename AS von, f.text AS frage"
        " FROM eintraege a JOIN eintraege f ON f.id = a.antwort_auf JOIN bestand b ON b.id = a.bestand_id"
        " JOIN nutzer n ON n.id = a.erstellt_von"
        " WHERE a.garten_id = ? AND a.typ = 'antwort' AND f.erstellt_von = ? AND a.datum >= ? AND b.archiviert = 0"
        " ORDER BY a.id DESC LIMIT 5",
        (garten["id"], ich, seit),
    ).fetchall()
    anzahl = db.execute(
        "SELECT COUNT(*) FROM bestand WHERE garten_id = ? AND archiviert = 0", (garten["id"],)
    ).fetchone()[0]
    return render_template(
        "heute.html",
        garten=garten,
        gruppen=gruppen,
        stufen=STUFEN,
        fragen=fragen,
        antworten=antworten,
        rundgang_offen=len(rundgang_schlange(db, garten["id"])),
        bestand_anzahl=anzahl,
        tag=heute(),
    )


# ---------- Aufgaben ----------


def _hole_aufgabe(aufgabe_id: int):
    garten = aktueller_garten()
    zeile = hole_db().execute(
        "SELECT a.*, b.name AS bestand_name, b.zustand AS bestand_zustand FROM aufgaben a"
        " JOIN bestand b ON b.id = a.bestand_id WHERE a.id = ? AND a.garten_id = ?",
        (aufgabe_id, garten["id"] if garten else 0),
    ).fetchone()
    if zeile is None:
        raise Eingabefehler("Diese Aufgabe gibt es nicht.", 404)
    return zeile


def _anleitungen(db):
    return db.execute("SELECT * FROM anleitungen ORDER BY titel COLLATE NOCASE").fetchall()


@bp.get("/aufgabe/<int:aufgabe_id>")
def aufgabe(aufgabe_id: int):
    db = hole_db()
    a = _hole_aufgabe(aufgabe_id)
    stufe, grund = dringlichkeit(als_datum(a["faellig_am"]), a["bestand_zustand"], bool(a["fest_jetzt"]), heute())
    anleitung = None
    if a["anleitung_id"]:
        anleitung = db.execute("SELECT * FROM anleitungen WHERE id = ?", (a["anleitung_id"],)).fetchone()
    vorher = db.execute(
        "SELECT * FROM medien WHERE aufgabe_id = ? AND eintrag_id IS NULL ORDER BY id", (aufgabe_id,)
    ).fetchall()
    return render_template(
        "aufgabe.html", a=a, stufe=stufe, stufe_wort=STUFEN[stufe], grund=grund, anleitung=anleitung, vorher=vorher,
        intervall=dict(INTERVALLE).get(a["intervall_monate"]),
    )


@bp.get("/aufgabe/neu")
def aufgabe_neu():
    db = hole_db()
    garten = aktueller_garten()
    bestand = db.execute(
        "SELECT * FROM bestand WHERE id = ? AND garten_id = ?",
        (request.args.get("bestand", type=int), garten["id"] if garten else 0),
    ).fetchone()
    if bestand is None:
        return redirect(url_for("bestand.liste"))
    return render_template(
        "aufgabe_form.html", a=None, bestand=bestand, anleitungen=_anleitungen(db), intervalle=INTERVALLE,
        vorschlag=(heute() + timedelta(days=14)).isoformat(), ziel=url_for("aufgaben.anlegen"),
    )


@bp.get("/aufgabe/<int:aufgabe_id>/bearbeiten")
def aufgabe_bearbeiten(aufgabe_id: int):
    db = hole_db()
    a = _hole_aufgabe(aufgabe_id)
    bestand = db.execute("SELECT * FROM bestand WHERE id = ?", (a["bestand_id"],)).fetchone()
    return render_template(
        "aufgabe_form.html", a=a, bestand=bestand, anleitungen=_anleitungen(db), intervalle=INTERVALLE,
        vorschlag=a["faellig_am"], ziel=url_for("aufgaben.aendern", aufgabe_id=aufgabe_id),
    )


def _lies_aufgabe(db):
    f = request.form
    titel = f.get("titel", "").strip()
    hinweis = f.get("hinweis", "").strip()
    if not titel:
        raise Eingabefehler("Bitte einen Titel für die Aufgabe eingeben.")
    if len(titel) > 120 or len(hinweis) > 2000:
        raise Eingabefehler("Titel oder Hinweis ist zu lang.")
    try:
        faellig = als_datum(f.get("faellig_am", ""))
    except ValueError:
        raise Eingabefehler("Bitte ein Datum für die Fälligkeit wählen.") from None
    intervall = f.get("intervall_monate", type=int)
    if intervall is not None and intervall not in {i for i, _ in INTERVALLE if i}:
        raise Eingabefehler("Dieses Intervall gibt es nicht.")
    anleitung_id = f.get("anleitung_id", type=int)
    if anleitung_id and db.execute("SELECT 1 FROM anleitungen WHERE id = ?", (anleitung_id,)).fetchone() is None:
        raise Eingabefehler("Diese Anleitung gibt es nicht.")
    # Nur der Meister legt fest, dass eine Aufgabe unabhängig vom Datum sofort dran ist.
    fest = 1 if f.get("fest_jetzt") == "1" and g.nutzer["rolle"] == "meister" else None
    return titel, hinweis, faellig.isoformat(), intervall, anleitung_id or None, fest


@bp.post("/api/aufgaben")
def anlegen():
    db = hole_db()
    garten = aktueller_garten()
    bestand = db.execute(
        "SELECT id FROM bestand WHERE id = ? AND garten_id = ?",
        (request.form.get("bestand_id", type=int), garten["id"] if garten else 0),
    ).fetchone()
    if bestand is None:
        raise Eingabefehler("Diese Pflanze gibt es nicht.", 404)
    titel, hinweis, faellig, intervall, anleitung_id, fest = _lies_aufgabe(db)
    cur = db.execute(
        "INSERT INTO aufgaben (garten_id, bestand_id, anleitung_id, titel, hinweis, faellig_am, intervall_monate,"
        " fest_jetzt, erstellt_von) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (garten["id"], bestand["id"], anleitung_id, titel, hinweis, faellig, intervall, fest or 0, g.nutzer["id"]),
    )
    db.commit()
    return jsonify(id=cur.lastrowid, weiter=url_for("aufgaben.aufgabe", aufgabe_id=cur.lastrowid)), 201


@bp.post("/api/aufgaben/<int:aufgabe_id>")
def aendern(aufgabe_id: int):
    db = hole_db()
    a = _hole_aufgabe(aufgabe_id)
    titel, hinweis, faellig, intervall, anleitung_id, fest = _lies_aufgabe(db)
    if g.nutzer["rolle"] != "meister":
        fest = a["fest_jetzt"]  # der Besitzer ändert die Festlegung des Meisters nicht
    db.execute(
        "UPDATE aufgaben SET titel = ?, hinweis = ?, faellig_am = ?, intervall_monate = ?, anleitung_id = ?,"
        " fest_jetzt = ? WHERE id = ?",
        (titel, hinweis, faellig, intervall, anleitung_id, fest or 0, aufgabe_id),
    )
    db.commit()
    return jsonify(weiter=url_for("aufgaben.aufgabe", aufgabe_id=aufgabe_id))


@bp.post("/api/aufgaben/<int:aufgabe_id>/verschieben")
def verschieben(aufgabe_id: int):
    a = _hole_aufgabe(aufgabe_id)
    tage = request.form.get("tage", type=int)
    if tage not in (7, 14, 30):
        raise Eingabefehler("Verschieben geht um 7, 14 oder 30 Tage.")
    neu = max(als_datum(a["faellig_am"]), heute()) + timedelta(days=tage)
    db = hole_db()
    db.execute("UPDATE aufgaben SET faellig_am = ? WHERE id = ?", (neu.isoformat(), aufgabe_id))
    db.commit()
    return jsonify(weiter=url_for("aufgaben.heute_seite"), faellig_am=neu.isoformat())


@bp.post("/api/aufgaben/<int:aufgabe_id>/fest")
@nur_meister
def festlegen(aufgabe_id: int):
    _hole_aufgabe(aufgabe_id)
    db = hole_db()
    db.execute(
        "UPDATE aufgaben SET fest_jetzt = ? WHERE id = ?", (1 if request.form.get("fest") == "1" else 0, aufgabe_id)
    )
    db.commit()
    return jsonify(weiter=url_for("aufgaben.aufgabe", aufgabe_id=aufgabe_id))


@bp.post("/api/aufgaben/<int:aufgabe_id>/loeschen")
def loeschen(aufgabe_id: int):
    a = _hole_aufgabe(aufgabe_id)
    db = hole_db()
    db.execute("DELETE FROM aufgaben WHERE id = ?", (aufgabe_id,))
    db.commit()
    return jsonify(weiter=url_for("bestand.detail", bestand_id=a["bestand_id"]))


# ---------- Anleitungen ----------


@bp.get("/anleitungen")
def anleitungen():
    return render_template("anleitungen.html", anleitungen=_anleitungen(hole_db()), zeitraum=zeitraum)


def _hole_anleitung(anleitung_id: int):
    zeile = hole_db().execute("SELECT * FROM anleitungen WHERE id = ?", (anleitung_id,)).fetchone()
    if zeile is None:
        raise Eingabefehler("Diese Anleitung gibt es nicht.", 404)
    return zeile


@bp.get("/anleitung/<int:anleitung_id>")
def anleitung(anleitung_id: int):
    a = _hole_anleitung(anleitung_id)
    return render_template(
        "anleitung.html", a=a, zeitraum=zeitraum(a["monat_von"], a["monat_bis"]),
        intervall=dict(INTERVALLE).get(a["intervall_monate"]),
    )


@bp.get("/anleitung/neu")
@nur_meister
def anleitung_neu():
    return render_template("anleitung_form.html", a=None, intervalle=INTERVALLE,
                           ziel=url_for("aufgaben.anleitung_anlegen"))


@bp.get("/anleitung/<int:anleitung_id>/bearbeiten")
@nur_meister
def anleitung_bearbeiten(anleitung_id: int):
    return render_template(
        "anleitung_form.html", a=_hole_anleitung(anleitung_id), intervalle=INTERVALLE,
        ziel=url_for("aufgaben.anleitung_aendern", anleitung_id=anleitung_id),
    )


def _lies_anleitung():
    f = request.form
    titel = f.get("titel", "").strip()
    schritte = "\n".join(z.strip() for z in f.get("schritte", "").splitlines() if z.strip())
    if not titel:
        raise Eingabefehler("Bitte einen Titel eingeben.")
    if not schritte:
        raise Eingabefehler("Bitte mindestens einen Schritt eingeben.")
    if len(titel) > 120 or len(schritte) > 6000:
        raise Eingabefehler("Titel oder Schritte sind zu lang.")
    von, bis = f.get("monat_von", type=int), f.get("monat_bis", type=int)
    if von is not None and not 1 <= von <= 12 or bis is not None and not 1 <= bis <= 12:
        raise Eingabefehler("Der Zeitraum passt nicht.")
    intervall = f.get("intervall_monate", type=int)
    return (titel, schritte, f.get("werkzeug", "").strip()[:300], f.get("sicherheit", "").strip()[:600], von,
            bis if von else None, intervall)


@bp.post("/api/anleitungen")
@nur_meister
def anleitung_anlegen():
    werte = _lies_anleitung()
    db = hole_db()
    cur = db.execute(
        "INSERT INTO anleitungen (titel, schritte, werkzeug, sicherheit, monat_von, monat_bis, intervall_monate,"
        " geaendert_von, geaendert_am) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (*werte, g.nutzer["id"]),
    )
    db.commit()
    return jsonify(weiter=url_for("aufgaben.anleitung", anleitung_id=cur.lastrowid)), 201


@bp.post("/api/anleitungen/<int:anleitung_id>")
@nur_meister
def anleitung_aendern(anleitung_id: int):
    _hole_anleitung(anleitung_id)
    werte = _lies_anleitung()
    db = hole_db()
    db.execute(
        "UPDATE anleitungen SET titel = ?, schritte = ?, werkzeug = ?, sicherheit = ?, monat_von = ?, monat_bis = ?,"
        " intervall_monate = ?, geaendert_von = ?, geaendert_am = datetime('now') WHERE id = ?",
        (*werte, g.nutzer["id"], anleitung_id),
    )
    db.commit()
    return jsonify(weiter=url_for("aufgaben.anleitung", anleitung_id=anleitung_id))


# ---------- Kalender ----------


def _ics_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_zeile(zeile: str) -> str:
    """Lange Zeilen müssen laut Kalenderformat nach 75 Bytes umbrochen werden."""
    teile = []
    roh = zeile.encode("utf-8")
    while len(roh) > 75:
        schnitt = 75 if not teile else 74
        while (roh[schnitt] & 0xC0) == 0x80:  # nicht mitten in einem Umlaut trennen
            schnitt -= 1
        teile.append(roh[:schnitt].decode("utf-8"))
        roh = roh[schnitt:]
    teile.append(roh.decode("utf-8"))
    return "\r\n ".join(teile)


def kalender_text(db, garten) -> str:
    """Alle offenen Pflegetermine als Kalenderdatei. Jeder Termin erinnert einen Tag und eine Stunde vorher."""
    stempel = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Garten-Kartierung//DE",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_text(garten['name'])}",
    ]
    aufgaben = db.execute(
        "SELECT a.*, b.name AS bestand_name, an.schritte, an.werkzeug FROM aufgaben a"
        " JOIN bestand b ON b.id = a.bestand_id LEFT JOIN anleitungen an ON an.id = a.anleitung_id"
        " WHERE a.garten_id = ? AND a.erledigt_am IS NULL AND b.archiviert = 0 ORDER BY a.faellig_am",
        (garten["id"],),
    ).fetchall()
    for a in aufgaben:
        tag = a["faellig_am"].replace("-", "")
        text = []
        if a["hinweis"]:
            text.append(a["hinweis"])
        if a["schritte"]:
            text += [f"{nr}. {schritt}" for nr, schritt in enumerate(a["schritte"].splitlines(), start=1)]
        if a["werkzeug"]:
            text.append(f"Werkzeug: {a['werkzeug']}")
        zeilen += [
            "BEGIN:VEVENT",
            f"UID:aufgabe-{a['id']}@garten-kartierung",
            f"DTSTAMP:{stempel}",
            # Ohne Zeitzone: 9 Uhr nach der Uhr des Handys.
            f"DTSTART:{tag}T090000",
            f"DTEND:{tag}T100000",
            f"SUMMARY:{_ics_text(a['titel'] + ' · ' + a['bestand_name'])}",
            f"DESCRIPTION:{_ics_text(chr(10).join(text))}",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_text('Morgen: ' + a['titel'])}",
            "TRIGGER:-P1D",
            "END:VALARM",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_text('In einer Stunde: ' + a['titel'])}",
            "TRIGGER:-PT1H",
            "END:VALARM",
            "END:VEVENT",
        ]
    zeilen.append("END:VCALENDAR")
    return "\r\n".join(_ics_zeile(z) for z in zeilen) + "\r\n"


def _kalender_token(db, garten) -> str:
    if garten["kalender_token"]:
        return garten["kalender_token"]
    token = secrets.token_urlsafe(24)
    db.execute("UPDATE gaerten SET kalender_token = ? WHERE id = ?", (token, garten["id"]))
    db.commit()
    return token


@bp.get("/kalender")
def kalender():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    db = hole_db()
    token = _kalender_token(db, garten)
    adresse = url_for("aufgaben.kalender_datei", token=token, _external=True)
    anzahl = db.execute(
        "SELECT COUNT(*) FROM aufgaben WHERE garten_id = ? AND erledigt_am IS NULL", (garten["id"],)
    ).fetchone()[0]
    return render_template(
        "kalender.html", garten=garten, adresse=adresse, abo=adresse.replace("https://", "webcal://", 1)
        .replace("http://", "webcal://", 1), anzahl=anzahl,
    )


@bp.get("/kalender/<token>.ics")
def kalender_datei(token: str):
    """Ohne Anmeldung erreichbar, damit Kalender-Apps den Kalender abonnieren können. Der Schlüssel in der
    Adresse ist das Geheimnis."""
    db = hole_db()
    garten = db.execute("SELECT * FROM gaerten WHERE kalender_token = ?", (token,)).fetchone()
    if garten is None or not secrets.compare_digest(garten["kalender_token"], token):
        return jsonify(fehler="Diesen Kalender gibt es nicht."), 404
    antwort = Response(kalender_text(db, garten), mimetype="text/calendar")
    antwort.headers["Content-Disposition"] = 'attachment; filename="garten.ics"'
    return antwort
