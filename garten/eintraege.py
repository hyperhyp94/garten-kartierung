"""Einträge im Verlauf einer Pflanze und die Fotos und Videos dazu.

Maßnahme, Beobachtung, Wissen, Frage, Antwort und Zustand sind alle ein
Eintrag. Deshalb gibt es genau einen Weg, auf dem sie gespeichert werden.
"""

import uuid
from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, send_from_directory, url_for

from .aufgaben import erledige, heute
from .db import hole_db
from .fehler import Eingabefehler
from .gaerten import aktueller_garten

bp = Blueprint("eintraege", __name__)

MAX_BILD = 10 * 1024 * 1024
MAX_VIDEO = 200 * 1024 * 1024
MAX_DATEIEN = 12
EIN_JAHR = 365 * 24 * 3600

TYPEN = {
    "massnahme": {
        "wort": "Maßnahme",
        "frage": "Was hast du gemacht?",
        "arten": ["Schnitt", "Düngen", "Gießen", "Pflanzen", "Umpflanzen", "Pflanzenschutz", "Ernte", "Sonstiges"],
    },
    "beobachtung": {
        "wort": "Beobachtung",
        "frage": "Was siehst du?",
        "arten": ["Knospe", "Austrieb", "Blüte", "Fruchtansatz", "Ernte", "Laubfall", "Sonstiges"],
    },
    "wissen": {
        "wort": "Wissen",
        "frage": "Worum geht es?",
        "arten": ["Pflege", "Standort", "Krankheit", "Sorte", "Sonstiges"],
    },
    "frage": {"wort": "Frage", "frage": "", "arten": []},
    "antwort": {"wort": "Antwort", "frage": "", "arten": []},
    "zustand": {"wort": "Zustand", "frage": "", "arten": []},
}
# Phasen, die im Jahresvergleich der Beobachtungen stehen
PHASEN = ["Knospe", "Austrieb", "Blüte", "Fruchtansatz", "Ernte", "Laubfall"]


def ordner() -> Path:
    pfad = current_app.config["DATEN"] / "uploads"
    pfad.mkdir(exist_ok=True)
    return pfad


def _video_endung(anfang: bytes) -> str | None:
    if anfang[4:8] == b"ftyp":
        return "mov" if anfang[8:12] == b"qt  " else "mp4"
    if anfang[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    return None


def _schreibe(datei, ziel: Path, grenze: int, zu_gross: str) -> int:
    """Schreibt einen Upload auf die Platte und bricht ab, sobald er zu groß wird."""
    groesse = 0
    with ziel.open("wb") as f:
        while True:
            stueck = datei.stream.read(1024 * 1024)
            if not stueck:
                break
            groesse += len(stueck)
            if groesse > grenze:
                raise Eingabefehler(zu_gross, 413)
            f.write(stueck)
    return groesse


def speichere_medien(db, bestand_id: int, eintrag_id: int | None = None, aufgabe_id: int | None = None,
                     kennzeichen_fest: str | None = None) -> int:
    """Speichert die Fotos und Videos der aktuellen Anfrage und gibt ihre Anzahl zurück.

    Fotos kommen vom Handy schon verkleinert als JPEG, zusammen mit einem kleinen Vorschaubild.
    Dateien bekommen einen zufälligen Namen. Der Name vom Handy wird nie als Pfad benutzt.
    """
    bilder = request.files.getlist("bild")
    vorschauen = request.files.getlist("vorschau")
    kennzeichen = request.form.getlist("kennzeichen")
    videos = request.files.getlist("video")
    if len(bilder) + len(videos) > MAX_DATEIEN:
        raise Eingabefehler(f"Höchstens {MAX_DATEIEN} Dateien auf einmal.")
    ziel_ordner = ordner()
    geschrieben: list[Path] = []
    try:
        for nr, bild in enumerate(bilder):
            if bild.stream.read(3) != b"\xff\xd8\xff":
                raise Eingabefehler("Ein Foto konnte nicht gelesen werden. Bitte noch einmal aufnehmen.")
            bild.stream.seek(0)
            name = f"{uuid.uuid4().hex}.jpg"
            geschrieben.append(ziel_ordner / name)
            groesse = _schreibe(bild, geschrieben[-1], MAX_BILD, "Ein Foto ist größer als 10 MB.")
            vorschau_name = None
            if nr < len(vorschauen) and vorschauen[nr].stream.read(3) == b"\xff\xd8\xff":
                vorschauen[nr].stream.seek(0)
                vorschau_name = f"{uuid.uuid4().hex}.jpg"
                geschrieben.append(ziel_ordner / vorschau_name)
                _schreibe(vorschauen[nr], geschrieben[-1], MAX_BILD, "Ein Foto ist größer als 10 MB.")
            marke = kennzeichen_fest or (kennzeichen[nr] if nr < len(kennzeichen) else "")
            if marke not in ("", "vorher", "nachher"):
                marke = ""
            db.execute(
                "INSERT INTO medien (bestand_id, eintrag_id, aufgabe_id, art, datei, vorschau, kennzeichen, groesse,"
                " erstellt_von) VALUES (?, ?, ?, 'bild', ?, ?, ?, ?, ?)",
                (bestand_id, eintrag_id, aufgabe_id, name, vorschau_name or name, marke, groesse, g.nutzer["id"]),
            )
        for video in videos:
            endung = _video_endung(video.stream.read(12))
            if endung is None:
                raise Eingabefehler("Dieses Videoformat wird nicht unterstützt. Möglich sind MP4, MOV und WebM.")
            video.stream.seek(0)
            name = f"{uuid.uuid4().hex}.{endung}"
            geschrieben.append(ziel_ordner / name)
            groesse = _schreibe(video, geschrieben[-1], MAX_VIDEO, "Das Video ist größer als 200 MB.")
            db.execute(
                "INSERT INTO medien (bestand_id, eintrag_id, aufgabe_id, art, datei, groesse, erstellt_von)"
                " VALUES (?, ?, ?, 'video', ?, ?, ?)",
                (bestand_id, eintrag_id, aufgabe_id, name, groesse, g.nutzer["id"]),
            )
    except Exception:
        for pfad in geschrieben:
            pfad.unlink(missing_ok=True)
        raise
    return len(bilder) + len(videos)


def loesche_dateien(medien) -> None:
    for m in medien:
        for name in {m["datei"], m["vorschau"]} - {None}:
            (ordner() / name).unlink(missing_ok=True)


@bp.get("/medien/<datei>")
def datei(datei: str):
    antwort = send_from_directory(ordner(), datei, conditional=True)
    antwort.headers["Cache-Control"] = f"private, max-age={EIN_JAHR}, immutable"
    return antwort


def _sicheres_ziel(ziel: str | None, sonst: str) -> str:
    if ziel and ziel.startswith("/") and not ziel.startswith("//") and "\\" not in ziel:
        return ziel
    return sonst


def _hole_bestand(db, bestand_id):
    garten = aktueller_garten()
    zeile = db.execute(
        "SELECT * FROM bestand WHERE id = ? AND garten_id = ? AND archiviert = 0",
        (bestand_id, garten["id"] if garten else 0),
    ).fetchone()
    if zeile is None:
        raise Eingabefehler("Diese Pflanze gibt es nicht.", 404)
    return zeile


def lege_eintrag_an(db, bestand, typ: str, *, unterart="", titel="", text="", datum: date | None = None,
                    zustand: int | None = None, aufgabe=None, antwort_auf=None) -> int:
    """Der eine Weg, auf dem ein Eintrag entsteht. Hält Zustand, Fragen und Aufgaben mit aktuell."""
    tag = datum or heute()
    cur = db.execute(
        "INSERT INTO eintraege (garten_id, bestand_id, typ, unterart, titel, text, datum, zustand, aufgabe_id,"
        " antwort_auf, offen, erstellt_von) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (bestand["garten_id"], bestand["id"], typ, unterart, titel, text, tag.isoformat(), zustand,
         aufgabe["id"] if aufgabe else None, antwort_auf, 1 if typ == "frage" else 0, g.nutzer["id"]),
    )
    eintrag_id = cur.lastrowid
    if zustand:
        db.execute(
            "UPDATE bestand SET zustand = ?, geaendert_am = datetime('now') WHERE id = ?", (zustand, bestand["id"])
        )
    if antwort_auf:
        db.execute("UPDATE eintraege SET offen = 0 WHERE id = ?", (antwort_auf,))
    if aufgabe:
        # Vorher-Fotos, die vor der Arbeit aufgenommen wurden, gehören jetzt zu diesem Eintrag.
        db.execute(
            "UPDATE medien SET eintrag_id = ? WHERE aufgabe_id = ? AND eintrag_id IS NULL", (eintrag_id, aufgabe["id"])
        )
        erledige(db, aufgabe, tag, g.nutzer["id"])
    return eintrag_id


@bp.get("/eintrag/neu")
def neu():
    db = hole_db()
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    typ = request.args.get("typ", "beobachtung")
    if typ not in ("massnahme", "beobachtung", "wissen", "frage", "antwort"):
        typ = "beobachtung"

    aufgabe = frage = frage_bilder = None
    bestand_id = request.args.get("bestand", type=int)
    if request.args.get("aufgabe", type=int):
        aufgabe = db.execute(
            "SELECT * FROM aufgaben WHERE id = ? AND garten_id = ? AND erledigt_am IS NULL",
            (request.args.get("aufgabe", type=int), garten["id"]),
        ).fetchone()
        if aufgabe is None:
            return redirect(url_for("aufgaben.heute_seite"))
        typ, bestand_id = "massnahme", aufgabe["bestand_id"]
    if typ == "antwort":
        frage = db.execute(
            "SELECT e.*, n.anzeigename AS von FROM eintraege e JOIN nutzer n ON n.id = e.erstellt_von"
            " WHERE e.id = ? AND e.garten_id = ? AND e.typ = 'frage'",
            (request.args.get("antwort_auf", type=int), garten["id"]),
        ).fetchone()
        if frage is None:
            return redirect(url_for("aufgaben.heute_seite"))
        bestand_id = frage["bestand_id"]
        frage_bilder = db.execute(
            "SELECT * FROM medien WHERE eintrag_id = ? AND art = 'bild' ORDER BY id", (frage["id"],)
        ).fetchall()

    bestand = None
    auswahl = []
    if bestand_id:
        bestand = db.execute(
            "SELECT * FROM bestand WHERE id = ? AND garten_id = ? AND archiviert = 0", (bestand_id, garten["id"])
        ).fetchone()
    if bestand is None:
        auswahl = db.execute(
            "SELECT b.*, (SELECT vorschau FROM medien m WHERE m.bestand_id = b.id AND m.art = 'bild'"
            " ORDER BY m.id DESC LIMIT 1) AS bild FROM bestand b WHERE b.garten_id = ? AND b.archiviert = 0"
            " ORDER BY b.name COLLATE NOCASE",
            (garten["id"],),
        ).fetchall()
        if not auswahl:
            return redirect(url_for("bestand.neu"))
    vorher = []
    if aufgabe:
        vorher = db.execute(
            "SELECT * FROM medien WHERE aufgabe_id = ? AND eintrag_id IS NULL ORDER BY id", (aufgabe["id"],)
        ).fetchall()
    return render_template(
        "eintrag_form.html", typ=typ, info=TYPEN[typ], bestand=bestand, auswahl=auswahl, aufgabe=aufgabe,
        frage=frage, frage_bilder=frage_bilder, vorher=vorher, tag=heute().isoformat(),
        weiter=_sicheres_ziel(request.args.get("weiter"), ""),
    )


@bp.post("/api/eintraege")
def anlegen():
    db = hole_db()
    f = request.form
    bestand = _hole_bestand(db, f.get("bestand_id", type=int))
    typ = f.get("typ", "")
    if typ not in TYPEN:
        raise Eingabefehler("Diese Art von Eintrag gibt es nicht.")
    unterart = f.get("unterart", "").strip()
    if unterart and unterart != "Rundgang" and unterart not in TYPEN[typ]["arten"]:
        raise Eingabefehler("Diese Auswahl gibt es nicht.")
    titel = f.get("titel", "").strip()
    text = f.get("text", "").strip()
    if len(titel) > 120 or len(text) > 4000:
        raise Eingabefehler("Titel oder Text ist zu lang.")
    try:
        tag = date.fromisoformat(f["datum"]) if f.get("datum") else heute()
    except ValueError:
        raise Eingabefehler("Das Datum konnte nicht gelesen werden.") from None
    if tag > heute():
        raise Eingabefehler("Das Datum liegt in der Zukunft.")
    zustand = f.get("zustand", type=int)
    if zustand is not None and not 1 <= zustand <= 5:
        raise Eingabefehler("Der Zustand geht von 1 bis 5.")
    hat_dateien = bool(request.files.getlist("bild") or request.files.getlist("video"))

    if typ == "zustand" and zustand is None:
        raise Eingabefehler("Bitte einen Zustand von 1 bis 5 wählen.")
    if typ == "frage" and not text:
        raise Eingabefehler("Bitte schreib deine Frage dazu.")
    if typ == "wissen" and not (titel and text):
        raise Eingabefehler("Wissen braucht einen Titel und einen Text.")
    if typ == "massnahme" and not (unterart or text or f.get("aufgabe_id")):
        raise Eingabefehler("Bitte wähle aus, was du gemacht hast.")
    if typ == "beobachtung" and not (unterart or text or hat_dateien):
        raise Eingabefehler("Bitte ein Foto aufnehmen, eine Phase wählen oder eine Notiz schreiben.")

    antwort_auf = None
    if typ == "antwort":
        frage = db.execute(
            "SELECT id FROM eintraege WHERE id = ? AND bestand_id = ? AND typ = 'frage'",
            (f.get("antwort_auf", type=int), bestand["id"]),
        ).fetchone()
        if frage is None:
            raise Eingabefehler("Die Frage zu dieser Antwort gibt es nicht mehr.", 404)
        if not (text or hat_dateien):
            raise Eingabefehler("Bitte schreib eine Antwort oder zeichne ins Bild.")
        antwort_auf = frage["id"]

    aufgabe = None
    if f.get("aufgabe_id"):
        aufgabe = db.execute(
            "SELECT * FROM aufgaben WHERE id = ? AND bestand_id = ? AND erledigt_am IS NULL",
            (f.get("aufgabe_id", type=int), bestand["id"]),
        ).fetchone()
        if aufgabe is None:
            raise Eingabefehler("Diese Aufgabe ist schon erledigt oder gelöscht.", 409)
        titel = titel or aufgabe["titel"]

    eintrag_id = lege_eintrag_an(db, bestand, typ, unterart=unterart, titel=titel, text=text, datum=tag,
                                 zustand=zustand, aufgabe=aufgabe, antwort_auf=antwort_auf)
    speichere_medien(db, bestand["id"], eintrag_id)
    db.commit()

    sonst = url_for("aufgaben.heute_seite") if aufgabe else url_for("bestand.detail", bestand_id=bestand["id"])
    return jsonify(id=eintrag_id, weiter=_sicheres_ziel(f.get("weiter"), sonst)), 201


@bp.post("/api/eintraege/<int:eintrag_id>/loeschen")
def loeschen(eintrag_id: int):
    db = hole_db()
    garten = aktueller_garten()
    e = db.execute(
        "SELECT * FROM eintraege WHERE id = ? AND garten_id = ?", (eintrag_id, garten["id"] if garten else 0)
    ).fetchone()
    if e is None:
        raise Eingabefehler("Diesen Eintrag gibt es nicht mehr.", 404)
    if e["erstellt_von"] != g.nutzer["id"] and g.nutzer["rolle"] != "meister":
        raise Eingabefehler("Diesen Eintrag kann nur löschen, wer ihn geschrieben hat.", 403)
    medien = db.execute(
        "SELECT * FROM medien WHERE eintrag_id = ? OR eintrag_id IN (SELECT id FROM eintraege WHERE antwort_auf = ?)",
        (eintrag_id, eintrag_id),
    ).fetchall()
    db.execute("DELETE FROM eintraege WHERE id = ?", (eintrag_id,))
    if e["typ"] == "antwort":
        # Ohne Antwort ist die Frage wieder offen.
        rest = db.execute(
            "SELECT COUNT(*) FROM eintraege WHERE antwort_auf = ?", (e["antwort_auf"],)
        ).fetchone()[0]
        db.execute("UPDATE eintraege SET offen = ? WHERE id = ?", (0 if rest else 1, e["antwort_auf"]))
    if e["zustand"]:
        # Der Zustand der Pflanze ist der des jüngsten verbliebenen Eintrags.
        letzter = db.execute(
            "SELECT zustand FROM eintraege WHERE bestand_id = ? AND zustand IS NOT NULL ORDER BY datum DESC, id DESC"
            " LIMIT 1",
            (e["bestand_id"],),
        ).fetchone()
        db.execute("UPDATE bestand SET zustand = ? WHERE id = ?", (letzter["zustand"] if letzter else None,
                                                                 e["bestand_id"]))
    db.commit()
    loesche_dateien(medien)
    return jsonify(weiter=url_for("bestand.detail", bestand_id=e["bestand_id"]))


@bp.post("/api/aufgaben/<int:aufgabe_id>/vorher")
def vorher_foto(aufgabe_id: int):
    """Vorher-Foto, bevor die Arbeit beginnt. Es wandert beim Erledigen in den Eintrag."""
    db = hole_db()
    garten = aktueller_garten()
    a = db.execute(
        "SELECT * FROM aufgaben WHERE id = ? AND garten_id = ? AND erledigt_am IS NULL",
        (aufgabe_id, garten["id"] if garten else 0),
    ).fetchone()
    if a is None:
        raise Eingabefehler("Diese Aufgabe ist schon erledigt oder gelöscht.", 404)
    if not request.files.getlist("bild"):
        raise Eingabefehler("Es ist kein Foto angekommen.")
    speichere_medien(db, a["bestand_id"], None, aufgabe_id, kennzeichen_fest="vorher")
    db.commit()
    return jsonify(weiter=url_for("aufgaben.aufgabe", aufgabe_id=aufgabe_id)), 201
