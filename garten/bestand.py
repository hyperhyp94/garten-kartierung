"""Pflanzen und Objekte des Gartens: erfassen, Liste, Detailseite, Lexikon und Vermessung."""

import json

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, url_for

from .aufgaben import lege_aus_anleitung_an, offene_aufgaben
from .db import hole_db
from .eintraege import PHASEN, TYPEN, lege_eintrag_an, speichere_medien
from .fehler import Eingabefehler
from .gaerten import aktueller_garten, karten_daten
from .geo import lade_flurstuecke, pruefe_geometrie
from .lexikon import lade_lexikon

bp = Blueprint("bestand", __name__)

KATEGORIEN = {
    "pflanze": ["Baum", "Obst", "Strauch", "Hecke", "Staude", "Kletterpflanze", "Kräuter", "Gemüse", "Rasen",
                "Sonstiges"],
    "objekt": ["Beet", "Weg", "Zaun", "Teich", "Terrasse", "Gebäude", "Sonstiges"],
}
# Womit die Karte beim Erfassen startet. Ändern lässt es sich immer.
FORM_VORSCHLAG = {"Weg": "linie", "Zaun": "linie", "Beet": "flaeche", "Teich": "flaeche", "Terrasse": "flaeche",
                  "Gebäude": "flaeche"}
ZUSTAND = {1: "kritisch", 2: "schlecht", 3: "mittel", 4: "gut", 5: "sehr gut"}

BILD = ("(SELECT vorschau FROM medien m WHERE m.bestand_id = b.id AND m.art = 'bild' ORDER BY m.id DESC LIMIT 1)"
        " AS bild")


def lade_bestand(db, garten_id: int):
    return db.execute(
        f"SELECT b.*, {BILD}, (SELECT COUNT(*) FROM aufgaben a WHERE a.bestand_id = b.id AND a.erledigt_am IS NULL)"
        " AS offen FROM bestand b WHERE b.garten_id = ? AND b.archiviert = 0 ORDER BY b.name COLLATE NOCASE",
        (garten_id,),
    ).fetchall()




def _hole(bestand_id: int):
    garten = aktueller_garten()
    zeile = hole_db().execute(
        f"SELECT b.*, {BILD} FROM bestand b WHERE b.id = ? AND b.garten_id = ? AND b.archiviert = 0",
        (bestand_id, garten["id"] if garten else 0),
    ).fetchone()
    if zeile is None:
        raise Eingabefehler("Diese Pflanze gibt es nicht.", 404)
    return zeile


# ---------- Seiten ----------


@bp.get("/bestand")
def liste():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    return render_template("bestand.html", garten=garten, bestand=lade_bestand(hole_db(), garten["id"]))


@bp.get("/bestand/neu")
def neu():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    art = "objekt" if request.args.get("art") == "objekt" else "pflanze"
    lexikon = lade_lexikon()
    vorwahl = lexikon.get(request.args.get("lexikon", ""))
    start = None
    if request.args.get("lat", type=float) and request.args.get("lon", type=float):
        start = {"lat": request.args.get("lat", type=float), "lon": request.args.get("lon", type=float),
                 "zoom": request.args.get("zoom", 20, type=float)}
    return render_template(
        "bestand_form.html", garten=garten, b=None, art=art, kategorien=KATEGORIEN[art], lexikon=lexikon.values(),
        vorwahl=vorwahl, formen=FORM_VORSCHLAG, zustand_worte=ZUSTAND, ziel=url_for("bestand.anlegen"),
        daten={**karten_daten(garten), "start": start, "geometrie": None, "form": "punkt"},
    )


@bp.get("/bestand/<int:bestand_id>/bearbeiten")
def bearbeiten(bestand_id: int):
    b = _hole(bestand_id)
    garten = aktueller_garten()
    return render_template(
        "bestand_form.html", garten=garten, b=b, art=b["art"], kategorien=KATEGORIEN[b["art"]], lexikon=[],
        vorwahl=None, formen=FORM_VORSCHLAG, zustand_worte=ZUSTAND,
        ziel=url_for("bestand.aendern", bestand_id=bestand_id),
        daten={**karten_daten(garten), "start": None, "geometrie": json.loads(b["geometrie"]), "form": b["form"]},
    )


def _verlauf(db, bestand_id: int):
    """Alle Einträge einer Pflanze, die neuesten zuerst, mit Fotos und Antworten."""
    zeilen = db.execute(
        "SELECT e.*, n.anzeigename AS von FROM eintraege e LEFT JOIN nutzer n ON n.id = e.erstellt_von"
        " WHERE e.bestand_id = ? ORDER BY e.datum DESC, e.id DESC",
        (bestand_id,),
    ).fetchall()
    medien: dict[int, list] = {}
    for m in db.execute("SELECT * FROM medien WHERE bestand_id = ? AND eintrag_id IS NOT NULL ORDER BY id",
                        (bestand_id,)):
        medien.setdefault(m["eintrag_id"], []).append(m)
    eintraege = [{**dict(z), "medien": medien.get(z["id"], []), "antworten": []} for z in zeilen]
    nach_id = {e["id"]: e for e in eintraege}
    oben = []
    for e in eintraege:
        if e["typ"] == "antwort" and e["antwort_auf"] in nach_id:
            nach_id[e["antwort_auf"]]["antworten"].insert(0, e)
        else:
            oben.append(e)
    return oben


def _zustandsverlauf(eintraege) -> dict | None:
    """Punkte für die kleine Verlaufsgrafik: links der älteste, rechts der neueste Zustand."""
    werte = sorted(
        [(e["datum"], e["id"], e["zustand"]) for gruppe in eintraege for e in [gruppe, *gruppe["antworten"]]
         if e["zustand"]],
    )
    if len(werte) < 2:
        return None
    breite, hoehe, rand = 300, 96, 12
    schritt = (breite - 2 * rand) / (len(werte) - 1)
    punkte = [
        {"x": round(rand + nr * schritt, 1), "y": round(hoehe - rand - (z - 1) * (hoehe - 2 * rand) / 4, 1),
         "zustand": z, "datum": datum}
        for nr, (datum, _, z) in enumerate(werte)
    ]
    return {"punkte": punkte, "linie": " ".join(f"{p['x']},{p['y']}" for p in punkte), "breite": breite,
            "hoehe": hoehe, "von": werte[0][0], "bis": werte[-1][0]}


def _jahresvergleich(eintraege) -> dict | None:
    """Für jede Phase das früheste Datum pro Jahr, damit sich Jahre vergleichen lassen."""
    tabelle: dict[str, dict[str, str]] = {}
    jahre = set()
    for e in eintraege:
        if e["typ"] == "beobachtung" and e["unterart"] in PHASEN:
            jahr = e["datum"][:4]
            jahre.add(jahr)
            alt = tabelle.setdefault(e["unterart"], {}).get(jahr)
            if alt is None or e["datum"] < alt:
                tabelle[e["unterart"]][jahr] = e["datum"]
    if not tabelle:
        return None
    return {"jahre": sorted(jahre)[-4:], "phasen": [(p, tabelle[p]) for p in PHASEN if p in tabelle]}


@bp.get("/bestand/<int:bestand_id>")
def detail(bestand_id: int):
    b = _hole(bestand_id)
    db = hole_db()
    eintraege = _verlauf(db, bestand_id)
    bilder = db.execute(
        "SELECT * FROM medien WHERE bestand_id = ? AND art = 'bild' ORDER BY id DESC LIMIT 30", (bestand_id,)
    ).fetchall()
    return render_template(
        "bestand_detail.html", b=b, garten=aktueller_garten(), lexikon=lade_lexikon().get(b["lexikon_id"] or ""),
        aufgaben=offene_aufgaben(db, b["garten_id"], bestand_id), eintraege=eintraege, bilder=bilder, typen=TYPEN,
        wissen=[e for e in eintraege if e["typ"] == "wissen"], verlauf=_zustandsverlauf(eintraege),
        vergleich=_jahresvergleich(eintraege), zustand_worte=ZUSTAND,
    )


@bp.get("/lexikon")
def lexikon():
    return render_template("lexikon.html", lexikon=lade_lexikon().values())


@bp.get("/lexikon/<lexikon_id>")
def lexikon_eintrag(lexikon_id: str):
    eintrag = lade_lexikon().get(lexikon_id)
    if eintrag is None:
        raise Eingabefehler("Diesen Eintrag gibt es im Lexikon nicht.", 404)
    db = hole_db()
    marken = ",".join("?" * len(eintrag["aufgaben"]))
    anleitungen = db.execute(
        f"SELECT * FROM anleitungen WHERE schluessel IN ({marken}) ORDER BY monat_von", eintrag["aufgaben"]
    ).fetchall() if eintrag["aufgaben"] else []
    return render_template("lexikon_eintrag.html", e=eintrag, anleitungen=anleitungen)


@bp.get("/messen")
def messen():
    garten = aktueller_garten()
    if garten is None:
        return redirect(url_for("gaerten.neu"))
    return render_template(
        "messen.html", garten=garten,
        daten={**karten_daten(garten), "start": None, "geometrie": None, "form": "linie"},
    )


# ---------- Speichern ----------


def _lies(art: str) -> dict:
    f = request.form
    name = f.get("name", "").strip()
    kategorie = f.get("kategorie", "")
    notiz = f.get("standort_notiz", "").strip()
    if not name:
        raise Eingabefehler("Bitte einen Namen eingeben oder eine Pflanze aus dem Lexikon wählen.")
    if len(name) > 80 or len(notiz) > 500:
        raise Eingabefehler("Name oder Notiz ist zu lang.")
    if kategorie not in KATEGORIEN[art]:
        raise Eingabefehler("Bitte eine Kategorie wählen.")
    try:
        geometrie = pruefe_geometrie(
            json.loads(f.get("geometrie", "")), lade_flurstuecke(current_app.config["FLURSTUECKE"]).rahmen
        )
    except (ValueError, TypeError):
        raise Eingabefehler("Bitte die Lage auf der Karte festlegen. Linien brauchen zwei, Flächen drei Punkte."
                            ) from None
    return {"name": name, "kategorie": kategorie, "notiz": notiz, **geometrie}


@bp.post("/api/bestand")
def anlegen():
    garten = aktueller_garten()
    if garten is None:
        raise Eingabefehler("Bitte zuerst einen Garten anlegen.", 409)
    f = request.form
    art = "objekt" if f.get("art") == "objekt" else "pflanze"
    w = _lies(art)
    zustand = f.get("zustand", type=int)
    if zustand is not None and not 1 <= zustand <= 5:
        raise Eingabefehler("Der Zustand geht von 1 bis 5.")
    lexikon_id = f.get("lexikon_id") or None
    eintrag = lade_lexikon().get(lexikon_id or "")
    if lexikon_id and eintrag is None:
        raise Eingabefehler("Diesen Eintrag gibt es im Lexikon nicht.")

    db = hole_db()
    cur = db.execute(
        "INSERT INTO bestand (garten_id, art, kategorie, name, lexikon_id, form, geometrie, lat, lon, mass,"
        " standort_notiz, erstellt_von) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (garten["id"], art, w["kategorie"], w["name"], lexikon_id, w["form"], json.dumps(w["geometrie"]), w["lat"],
         w["lon"], w["mass"], w["notiz"], g.nutzer["id"]),
    )
    bestand = db.execute("SELECT * FROM bestand WHERE id = ?", (cur.lastrowid,)).fetchone()
    # Der erste Eintrag im Verlauf: wann erfasst, mit welchem Zustand und welchem Foto.
    eintrag_id = lege_eintrag_an(db, bestand, "zustand", unterart="", titel="Erfasst", zustand=zustand)
    speichere_medien(db, bestand["id"], eintrag_id)
    if eintrag and f.get("aufgaben_anlegen") == "1":
        for schluessel in eintrag["aufgaben"]:
            lege_aus_anleitung_an(db, garten["id"], bestand["id"], schluessel, g.nutzer["id"])
    db.commit()
    return jsonify(id=bestand["id"], weiter=url_for("bestand.detail", bestand_id=bestand["id"])), 201


@bp.post("/api/bestand/<int:bestand_id>")
def aendern(bestand_id: int):
    b = _hole(bestand_id)
    w = _lies(b["art"])
    db = hole_db()
    db.execute(
        "UPDATE bestand SET name = ?, kategorie = ?, standort_notiz = ?, form = ?, geometrie = ?, lat = ?, lon = ?,"
        " mass = ?, geaendert_am = datetime('now') WHERE id = ?",
        (w["name"], w["kategorie"], w["notiz"], w["form"], json.dumps(w["geometrie"]), w["lat"], w["lon"],
         w["mass"], bestand_id),
    )
    db.commit()
    return jsonify(weiter=url_for("bestand.detail", bestand_id=bestand_id))


@bp.post("/api/bestand/<int:bestand_id>/entfernen")
def entfernen(bestand_id: int):
    """Nimmt eine Pflanze aus dem Garten. Verlauf und Fotos bleiben in der Datenbank erhalten."""
    _hole(bestand_id)
    db = hole_db()
    db.execute("UPDATE bestand SET archiviert = 1, geaendert_am = datetime('now') WHERE id = ?", (bestand_id,))
    db.commit()
    return jsonify(weiter=url_for("bestand.liste"))
