"""Garten-Kartierung – Flask-App (Port 5113)."""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import secrets
import sqlite3
import uuid
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, g, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for, Response)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from priority import add_months, berechne_prioritaet, ics_kalender

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
DB_PATH = Path(os.environ.get("GARTEN_DB", DATA / "garten.db"))
MAX_IMAGE = 10 * 1024 * 1024
MAX_VIDEO = 200 * 1024 * 1024
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
TYPES_PFLANZE = ["Baum", "Strauch", "Staude", "Kletterpflanze", "Gemüse", "Rasen", "Beet", "Sonstiges"]
TYPES_OBJEKT = ["Weg", "Teich", "Zaun", "Gebäude", "Terrasse", "Sitzplatz", "Sonstiges"]
EVENT_TYPES = ["Schnitt", "Düngen", "Gießen", "Pflanzen", "Umpflanzen", "Pflanzenschutz",
               "Ernte", "Mulchen", "Mähen", "Beobachtung", "Sonstiges"]
PHASEN = ["Knospe", "Austrieb", "Blüte", "Fruchtansatz", "Ernte", "Laubfall", "Ruhe", "Sonstiges"]
USERS = {"sven": ("Sven", "owner"), "johannes": ("Johannes", "meister")}

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO + 1024 * 1024


def _secret_key() -> str:
    env = os.environ.get("GARTEN_SECRET")
    if env:
        return env
    p = DATA / "secret_key"
    DATA.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        os.chmod(p, 0o600)
    return p.read_text(encoding="utf-8").strip()


app.secret_key = _secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("GARTEN_HTTPS") == "1")


# ---------- Datenbank ----------

def db() -> sqlite3.Connection:
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def _close(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((BASE / "schema.sql").read_text(encoding="utf-8"))
    for uname, (display, role) in USERS.items():
        conn.execute("INSERT OR IGNORE INTO users(username, display_name, password_hash) VALUES(?,?,NULL)",
                     (uname, display))
    # Vorlagen aus data/vorlagen.json laden (idempotent über key)
    for v in json.loads((DATA / "vorlagen.json").read_text(encoding="utf-8")):
        conn.execute(
            """INSERT OR IGNORE INTO task_templates(key,name,kategorie,intervall_monate,saison,werkzeuge,sicherheit,anleitung)
               VALUES(?,?,?,?,?,?,?,?)""",
            (v["key"], v["name"], v["kategorie"], v["intervall_monate"], v["saison"],
             v["werkzeuge"], v["sicherheit"], v["anleitung"]))
    conn.commit()
    conn.close()


def seed_garden() -> None:
    """Ein Garten 'Garten Deisterstraße 40' mit owner sven und meister johannes, falls leer."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("SELECT COUNT(*) FROM gardens").fetchone()[0] == 0:
        sven = conn.execute("SELECT id FROM users WHERE username='sven'").fetchone()["id"]
        joh = conn.execute("SELECT id FROM users WHERE username='johannes'").fetchone()["id"]
        cur = conn.execute(
            "INSERT INTO gardens(name, adresse, gemarkung, flurstuecke, created_by) VALUES(?,?,?,?,?)",
            ("Garten Deisterstraße 40", "Deisterstraße 40, 31867 Lauenau (Feggendorf)",
             "Feggendorf", json.dumps(["56/7 Flur 001"]), sven))
        gid = cur.lastrowid
        conn.execute("INSERT INTO garden_members VALUES(?,?,?)", (gid, sven, "owner"))
        conn.execute("INSERT INTO garden_members VALUES(?,?,?)", (gid, joh, "meister"))
        conn.commit()
    conn.close()


def role_of(garden_id: int, user_id: int) -> str | None:
    row = db().execute("SELECT role FROM garden_members WHERE garden_id=? AND user_id=?",
                       (garden_id, user_id)).fetchone()
    return row["role"] if row else None


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return db().execute("SELECT id, username, display_name FROM users WHERE id=?", (uid,)).fetchone()


# ---------- Auth / CSRF ----------

def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify(error="Nicht angemeldet"), 401
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def garden_access(min_role: str | None = None):
    """Prüft, ob der Nutzer Zugriff auf den Garten hat. min_role: 'meister' = Meister oder Owner."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            gid = kw.get("gid", a[0] if a else None)
            u = current_user()
            if not u:
                return jsonify(error="Nicht angemeldet"), 401
            role = role_of(gid, u["id"])
            if role is None:
                return jsonify(error="Nicht gefunden"), 404  # fremde Gärten bleiben unsichtbar
            if min_role == "owner" and role != "owner":
                return jsonify(error="Nur der Besitzer darf das"), 403
            g.role = role
            return fn(*a, **kw)
        return wrapper
    return deco


def can_edit_plan(role: str) -> bool:
    """Meister und Owner dürfen planen (Aufgaben anlegen, Prio, Vorlagen)."""
    return role in ("owner", "meister")


@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = session.get("csrf")
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not token or not sent or not secrets.compare_digest(token, sent):
            if request.path.startswith("/api/"):
                return jsonify(error="CSRF-Token ungültig"), 403
            abort(403)


@app.context_processor
def inject_globals():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return {"csrf_token": session["csrf"], "user": current_user(), "PFLANZE": TYPES_PFLANZE,
            "OBJEKT": TYPES_OBJEKT, "EVENTS": EVENT_TYPES, "PHASEN": PHASEN}


@app.route("/health")
def health():
    try:
        db().execute("SELECT 1").fetchone()
        ok = True
    except Exception:
        ok = False
    return jsonify(status="ok" if ok else "error")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        uname = (request.form.get("username") or "").strip().lower()
        pw = request.form.get("password") or ""
        row = db().execute("SELECT id, password_hash FROM users WHERE username=?", (uname,)).fetchone()
        if not row or not row["password_hash"]:
            error = "Anmeldung nicht möglich. Passwort noch nicht gesetzt oder falsch."
        elif not check_password_hash(row["password_hash"], pw):
            error = "Benutzername oder Passwort falsch."
        else:
            session.clear()
            session["uid"] = row["id"]
            session["csrf"] = secrets.token_urlsafe(24)
            return redirect(request.args.get("next") or url_for("heute"))
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Seiten ----------

@app.route("/")
@login_required
def index():
    return redirect(url_for("heute"))


def _gardens_for(uid):
    return db().execute(
        """SELECT g.*, m.role FROM gardens g JOIN garden_members m ON m.garden_id=g.id
           WHERE m.user_id=? ORDER BY g.name""", (uid,)).fetchall()


@app.route("/heute")
@login_required
def heute():
    u = current_user()
    gardens = _gardens_for(u["id"])
    return render_template("heute.html", gardens=gardens)


@app.route("/gaerten")
@login_required
def gaerten():
    return render_template("gaerten.html", gardens=_gardens_for(current_user()["id"]))


@app.route("/gaerten/neu")
@login_required
def garten_neu():
    if current_user()["username"] != "sven":
        abort(403)
    return render_template("garten_neu.html")


@app.route("/gaerten/<int:gid>")
@login_required
def garten(gid):
    role = role_of(gid, current_user()["id"])
    if role is None:
        abort(404)
    garden = db().execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone()
    return render_template("garten.html", garden=garden, role=role)


@app.route("/gaerten/<int:gid>/aufgaben")
@login_required
def aufgaben_seite(gid):
    role = role_of(gid, current_user()["id"])
    if role is None:
        abort(404)
    garden = db().execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone()
    return render_template("aufgaben.html", garden=garden, role=role)


@app.route("/objekte/<int:oid>")
@login_required
def objekt_detail(oid):
    obj = db().execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
    if not obj:
        abort(404)
    role = role_of(obj["garden_id"], current_user()["id"])
    if role is None:
        abort(404)
    garden = db().execute("SELECT * FROM gardens WHERE id=?", (obj["garden_id"],)).fetchone()
    return render_template("objekt.html", obj=obj, garden=garden, role=role)


@app.route("/lexikon")
@login_required
def lexikon():
    return render_template("lexikon.html")


@app.route("/vorlagen")
@login_required
def vorlagen():
    rows = db().execute("SELECT * FROM task_templates ORDER BY kategorie, name").fetchall()
    return render_template("vorlagen.html", vorlagen=rows)


@app.route("/mehr")
@login_required
def mehr():
    return render_template("mehr.html", gardens=_gardens_for(current_user()["id"]))


@app.route("/uploads/<path:name>")
@login_required
def upload_file(name):
    # Zugriff nur, wenn Medium zu einem Garten gehört, auf den der Nutzer Zugriff hat
    row = db().execute(
        """SELECT m.id FROM media m
           LEFT JOIN objects o ON o.id = m.object_id
           LEFT JOIN observations ob ON ob.id = m.observation_id
           LEFT JOIN events e ON e.id = m.event_id
           WHERE m.pfad=? OR m.thumb_pfad=?""", (name, name)).fetchone()
    if not row:
        abort(404)
    gid = db().execute(
        """SELECT COALESCE(o.garden_id, ob_o.garden_id, e_o.garden_id) AS gid
           FROM media m
           LEFT JOIN objects o ON o.id = m.object_id
           LEFT JOIN observations ob ON ob.id = m.observation_id
           LEFT JOIN objects ob_o ON ob_o.id = ob.object_id
           LEFT JOIN events e ON e.id = m.event_id
           LEFT JOIN objects e_o ON e_o.id = e.object_id
           WHERE m.pfad=? OR m.thumb_pfad=?""", (name, name)).fetchone()["gid"]
    if role_of(gid, current_user()["id"]) is None:
        abort(404)
    return send_from_directory(UPLOADS, name)


# ---------- API: Gärten & Flurstücke ----------

@app.route("/api/flurstuecke")
@login_required
def api_flurstuecke():
    return send_file(DATA / "flurstuecke_feggendorf.geojson", mimetype="application/geo+json")


@app.route("/api/lexikon")
@login_required
def api_lexikon():
    return jsonify(json.loads((DATA / "lexikon.json").read_text(encoding="utf-8")))


@app.route("/api/gaerten", methods=["GET", "POST"])
@login_required
def api_gaerten():
    u = current_user()
    if request.method == "GET":
        rows = _gardens_for(u["id"])
        return jsonify([dict(r) for r in rows])
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="Name fehlt"), 400
    flst = data.get("flurstuecke") or []
    polygon = data.get("polygon")
    flaeche = _flaeche_m2(polygon) if polygon else data.get("flaeche_m2")
    umfang = _umfang_m(polygon) if polygon else None
    cur = db().execute(
        """INSERT INTO gardens(name, adresse, gemarkung, flurstuecke, polygon, flaeche_m2, umfang_m, notizen, created_by)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (name, data.get("adresse"), data.get("gemarkung") or "Feggendorf", json.dumps(flst),
         json.dumps(polygon) if polygon else None, flaeche, umfang, data.get("notizen"), u["id"]))
    gid = cur.lastrowid
    db().execute("INSERT INTO garden_members VALUES(?,?,?)", (gid, u["id"], "owner"))
    # Meister wird automatisch zugewiesen, sofern vorhanden
    joh = db().execute("SELECT id FROM users WHERE username='johannes'").fetchone()
    if joh and joh["id"] != u["id"]:
        db().execute("INSERT INTO garden_members VALUES(?,?,?)", (gid, joh["id"], "meister"))
    db().commit()
    return jsonify(id=gid), 201


@app.route("/api/gaerten/<int:gid>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_garten(gid):
    u = current_user()
    role = role_of(gid, u["id"])
    if role is None:
        return jsonify(error="Nicht gefunden"), 404
    if request.method == "GET":
        row = db().execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone()
        return jsonify(dict(row))
    if request.method == "DELETE":
        if role != "owner":
            return jsonify(error="Nur der Besitzer darf den Garten löschen"), 403
        db().execute("DELETE FROM gardens WHERE id=?", (gid,))
        db().commit()
        return jsonify(ok=True)
    if role != "owner":
        return jsonify(error="Nur der Besitzer darf den Garten ändern"), 403
    data = request.get_json(force=True, silent=True) or {}
    polygon = data.get("polygon")
    cur_row = db().execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone()
    db().execute(
        "UPDATE gardens SET name=?, adresse=?, flurstuecke=?, polygon=?, flaeche_m2=?, umfang_m=?, notizen=? WHERE id=?",
        ((data.get("name") or cur_row["name"]), data.get("adresse", cur_row["adresse"]),
         json.dumps(data.get("flurstuecke") or []),
         json.dumps(polygon) if polygon else None,
         _flaeche_m2(polygon) if polygon else data.get("flaeche_m2", cur_row["flaeche_m2"]),
         _umfang_m(polygon) if polygon else cur_row["umfang_m"], data.get("notizen", cur_row["notizen"]), gid))
    db().commit()
    return jsonify(ok=True)


def _ll_to_utm32(lat, lon):
    import math
    a = 6378137.0
    f = 1 / 298.257222101
    k0 = 0.9996
    lon0 = 9 * math.pi / 180
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    phi = math.radians(lat)
    lam = math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    T = math.tan(phi) ** 2
    C = ep2 * math.cos(phi) ** 2
    A = (lam - lon0) * math.cos(phi)
    M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
             - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * phi)
             + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * phi)
             - (35 * e2 ** 3 / 3072) * math.sin(6 * phi))
    E = 500000 + k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * A ** 5 / 120)
    return E, k0 * (M + N * math.tan(phi) * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24
                                            + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * A ** 6 / 720))


def _flaeche_m2(polygon) -> float | None:
    """Fläche in m² über UTM32N-Projektion (Shoelace). polygon: GeoJSON Polygon."""
    try:
        ring = polygon["coordinates"][0]
    except (KeyError, IndexError, TypeError):
        return None
    pts = [_ll_to_utm32(lat, lon) for lon, lat in ring]
    s = 0.0
    for i in range(len(pts) - 1):
        s += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return round(abs(s) / 2, 2)


def _umfang_m(polygon) -> float | None:
    try:
        ring = polygon["coordinates"][0]
    except (KeyError, IndexError, TypeError):
        return None
    pts = [_ll_to_utm32(lat, lon) for lon, lat in ring]
    import math
    return round(sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)), 2)


@app.route("/api/messen/flaeche", methods=["POST"])
@login_required
def api_messen_flaeche():
    data = request.get_json(force=True, silent=True) or {}
    poly = data.get("polygon")
    return jsonify(flaeche_m2=_flaeche_m2(poly), umfang_m=_umfang_m(poly))


@app.route("/api/messen/abstand", methods=["POST"])
@login_required
def api_messen_abstand():
    import math
    d = request.get_json(force=True, silent=True) or {}
    a, b = d.get("a"), d.get("b")
    if not a or not b:
        return jsonify(error="Zwei Punkte nötig"), 400
    ea, na = _ll_to_utm32(a["lat"], a["lon"])
    eb, nb = _ll_to_utm32(b["lat"], b["lon"])
    return jsonify(abstand_m=round(math.dist((ea, na), (eb, nb)), 2))


# ---------- API: Objekte ----------

@app.route("/api/gaerten/<int:gid>/objekte", methods=["GET", "POST"])
@login_required
@garden_access()
def api_objekte(gid):
    u = current_user()
    if request.method == "GET":
        rows = db().execute("SELECT * FROM objects WHERE garden_id=? ORDER BY name", (gid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="Name fehlt"), 400
    typ = data.get("typ") or "pflanze"
    if typ not in ("pflanze", "objekt"):
        return jsonify(error="Typ ungültig"), 400
    zust = data.get("zustand")
    if zust is not None and not (1 <= int(zust) <= 5):
        return jsonify(error="Zustand 1–5"), 400
    cur = db().execute(
        """INSERT INTO objects(garden_id, typ, kategorie, name, lexikon_key, geometrie, zustand,
           standort_notiz, pflanzdatum, created_by, updated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (gid, typ, data.get("kategorie"), name, data.get("lexikon_key"),
         json.dumps(data.get("geometrie")) if data.get("geometrie") else None,
         zust, data.get("standort_notiz"), data.get("pflanzdatum"), u["id"], u["id"]))
    oid = cur.lastrowid
    # Vorlagen-Aufgaben aus Lexikon-Eintrag ableiten (nur wenn Vorlagen-Keys gesetzt sind)
    for tkey in data.get("vorlagen") or []:
        t = db().execute("SELECT * FROM task_templates WHERE key=?", (tkey,)).fetchone()
        if t:
            _create_task_from_template(gid, oid, t, dt.date.today())
    db().commit()
    return jsonify(id=oid), 201


def _create_task_from_template(gid, oid, t, start: dt.date):
    faellig = start.isoformat()
    db().execute(
        """INSERT INTO tasks(garden_id, object_id, template_id, titel, anleitung, intervall_monate,
           faellig_am, saison, status, created_by, updated_by) VALUES(?,?,?,?,?,?,?,?, 'offen', NULL, NULL)""",
        (gid, oid, t["id"], t["name"], t["anleitung"], t["intervall_monate"], faellig, t["saison"]))


@app.route("/api/objekte/<int:oid>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_objekt(oid):
    obj = db().execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
    if not obj:
        return jsonify(error="Nicht gefunden"), 404
    role = role_of(obj["garden_id"], current_user()["id"])
    if role is None:
        return jsonify(error="Nicht gefunden"), 404
    if request.method == "GET":
        return jsonify(dict(obj))
    if request.method == "DELETE":
        if role != "owner":
            return jsonify(error="Nur der Besitzer darf löschen"), 403
        db().execute("DELETE FROM objects WHERE id=?", (oid,))
        db().commit()
        return jsonify(ok=True)
    data = request.get_json(force=True, silent=True) or {}
    zust = data.get("zustand", obj["zustand"])
    if zust is not None and not (1 <= int(zust) <= 5):
        return jsonify(error="Zustand 1–5"), 400
    db().execute(
        """UPDATE objects SET name=?, kategorie=?, standort_notiz=?, pflanzdatum=?, zustand=?, geometrie=?,
           updated_by=?, updated_at=datetime('now') WHERE id=?""",
        (data.get("name", obj["name"]), data.get("kategorie", obj["kategorie"]),
         data.get("standort_notiz", obj["standort_notiz"]), data.get("pflanzdatum", obj["pflanzdatum"]),
         zust, json.dumps(data["geometrie"]) if "geometrie" in data and data["geometrie"] else obj["geometrie"],
         current_user()["id"], oid))
    db().commit()
    return jsonify(ok=True)


# ---------- API: wissen, ereignisse, beobachtungen ----------

@app.route("/api/objekte/<int:oid>/wissen", methods=["GET", "POST"])
@login_required
def api_wissen(oid):
    obj = db().execute("SELECT garden_id FROM objects WHERE id=?", (oid,)).fetchone()
    if not obj or role_of(obj["garden_id"], current_user()["id"]) is None:
        return jsonify(error="Nicht gefunden"), 404
    if request.method == "GET":
        rows = db().execute("SELECT * FROM knowledge WHERE object_id=? ORDER BY created_at DESC", (oid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    d = request.get_json(force=True, silent=True) or {}
    if not (d.get("titel") or "").strip():
        return jsonify(error="Titel fehlt"), 400
    db().execute("INSERT INTO knowledge(object_id, titel, text, kategorie, created_by) VALUES(?,?,?,?,?)",
                 (oid, d["titel"].strip(), d.get("text"), d.get("kategorie"), current_user()["id"]))
    db().commit()
    return jsonify(ok=True), 201


@app.route("/api/objekte/<int:oid>/ereignisse", methods=["GET", "POST"])
@login_required
def api_ereignisse(oid):
    obj = db().execute("SELECT garden_id FROM objects WHERE id=?", (oid,)).fetchone()
    if not obj or role_of(obj["garden_id"], current_user()["id"]) is None:
        return jsonify(error="Nicht gefunden"), 404
    if request.method == "GET":
        rows = db().execute("SELECT * FROM events WHERE object_id=? ORDER BY datum DESC, id DESC", (oid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    d = request.get_json(force=True, silent=True) or {}
    typ = d.get("typ")
    if typ not in EVENT_TYPES:
        return jsonify(error="Art ungültig"), 400
    datum = d.get("datum") or dt.date.today().isoformat()
    zust = d.get("zustand_nach")
    if zust is not None and not (1 <= int(zust) <= 5):
        return jsonify(error="Zustand 1–5"), 400
    cur = db().execute(
        """INSERT INTO events(object_id, garden_id, datum, typ, beschreibung, zustand_nach, task_id, user_id)
           VALUES(?,?,?,?,?,?,?,?)""",
        (oid, obj["garden_id"], datum, typ, d.get("beschreibung"), zust, d.get("task_id"), current_user()["id"]))
    eid = cur.lastrowid
    if zust is not None:
        db().execute("UPDATE objects SET zustand=?, updated_at=datetime('now') WHERE id=?", (zust, oid))
    db().commit()
    return jsonify(id=eid), 201


@app.route("/api/objekte/<int:oid>/beobachtungen", methods=["GET", "POST"])
@login_required
def api_beobachtungen(oid):
    obj = db().execute("SELECT garden_id FROM objects WHERE id=?", (oid,)).fetchone()
    if not obj or role_of(obj["garden_id"], current_user()["id"]) is None:
        return jsonify(error="Nicht gefunden"), 404
    if request.method == "GET":
        rows = db().execute("SELECT * FROM observations WHERE object_id=? ORDER BY datum DESC", (oid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    d = request.get_json(force=True, silent=True) or {}
    phase = d.get("phase")
    if phase not in PHASEN:
        return jsonify(error="Phase ungültig"), 400
    cur = db().execute("INSERT INTO observations(object_id, datum, phase, notiz, user_id) VALUES(?,?,?,?,?)",
                       (oid, d.get("datum") or dt.date.today().isoformat(), phase, d.get("notiz"), current_user()["id"]))
    db().commit()
    return jsonify(id=cur.lastrowid), 201


# ---------- API: Aufgaben ----------

def _task_row(r):
    d = dict(r)
    heute = dt.date.today()
    fa = dt.date.fromisoformat(d["faellig_am"]) if d.get("faellig_am") else None
    obj = db().execute("SELECT zustand FROM objects WHERE id=?", (d["object_id"],)).fetchone() if d.get("object_id") else None
    zustand = obj["zustand"] if obj else None
    d["prioritaet"] = berechne_prioritaet(fa, heute, zustand, d.get("saison") or "",
                                          d.get("prio_manuell"))
    d["ueberfaellig"] = bool(fa and fa < heute and d["status"] == "offen")
    return d


@app.route("/api/gaerten/<int:gid>/aufgaben", methods=["GET", "POST"])
@login_required
@garden_access()
def api_aufgaben(gid):
    u = current_user()
    if request.method == "GET":
        rows = db().execute(
            "SELECT * FROM tasks WHERE garden_id=? ORDER BY faellig_am IS NULL, faellig_am", (gid,)).fetchall()
        out = [_task_row(r) for r in rows]
        out.sort(key=lambda t: (t["prioritaet"], t["faellig_am"] or "9999"))
        return jsonify(out)
    if not can_edit_plan(g.role):
        return jsonify(error="Nur Meister/Besitzer dürfen Aufgaben anlegen"), 403
    d = request.get_json(force=True, silent=True) or {}
    titel = (d.get("titel") or "").strip()
    if not titel:
        return jsonify(error="Titel fehlt"), 400
    cur = db().execute(
        """INSERT INTO tasks(garden_id, object_id, template_id, titel, anleitung, intervall_monate,
           faellig_am, saison, prio_manuell, created_by, updated_by)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (gid, d.get("object_id"), d.get("template_id"), titel, d.get("anleitung"),
         d.get("intervall_monate"), d.get("faellig_am") or dt.date.today().isoformat(),
         d.get("saison"), d.get("prio_manuell"), u["id"], u["id"]))
    db().commit()
    return jsonify(id=cur.lastrowid), 201


@app.route("/api/aufgaben/<int:tid>", methods=["GET", "PUT"])
@login_required
def api_aufgabe(tid):
    t = db().execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t:
        return jsonify(error="Nicht gefunden"), 404
    role = role_of(t["garden_id"], current_user()["id"])
    if role is None:
        return jsonify(error="Nicht gefunden"), 404
    if request.method == "GET":
        return jsonify(_task_row(t))
    if not can_edit_plan(role):
        return jsonify(error="Nur Meister/Besitzer dürfen Aufgaben ändern"), 403
    d = request.get_json(force=True, silent=True) or {}
    db().execute(
        """UPDATE tasks SET titel=?, anleitung=?, intervall_monate=?, faellig_am=?, saison=?,
           prio_manuell=?, updated_by=?, updated_at=datetime('now') WHERE id=?""",
        (d.get("titel", t["titel"]), d.get("anleitung", t["anleitung"]),
         d.get("intervall_monate", t["intervall_monate"]), d.get("faellig_am", t["faellig_am"]),
         d.get("saison", t["saison"]), d.get("prio_manuell", t["prio_manuell"]), current_user()["id"], tid))
    db().commit()
    return jsonify(ok=True)


@app.route("/api/aufgaben/<int:tid>/erledigen", methods=["POST"])
@login_required
def api_aufgabe_erledigen(tid):
    """Erledigt eine Aufgabe: Protokoll-Eintrag, Zustand, Folgetermin bei Intervall."""
    t = db().execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t or role_of(t["garden_id"], current_user()["id"]) is None:
        return jsonify(error="Nicht gefunden"), 404
    d = request.get_json(force=True, silent=True) or {}
    heute = dt.date.today()
    datum = d.get("datum") or heute.isoformat()
    zust = d.get("zustand_nach")
    if zust is not None and not (1 <= int(zust) <= 5):
        return jsonify(error="Zustand 1–5"), 400
    typ = d.get("typ") or (t["titel"].split(" ")[0] if t["titel"] else "Sonstiges")
    if typ not in EVENT_TYPES:
        typ = "Sonstiges"
    db().execute(
        """INSERT INTO events(object_id, garden_id, datum, typ, beschreibung, zustand_nach, task_id, user_id)
           VALUES(?,?,?,?,?,?,?,?)""",
        (t["object_id"], t["garden_id"], datum, typ, d.get("beschreibung") or f"Erledigt: {t['titel']}",
         zust, tid, current_user()["id"]))
    if zust is not None and t["object_id"]:
        db().execute("UPDATE objects SET zustand=?, updated_at=datetime('now') WHERE id=?", (zust, t["object_id"]))
    new_due = None
    if t["intervall_monate"]:
        new_due = add_months(dt.date.fromisoformat(datum), int(t["intervall_monate"])).isoformat()
        db().execute(
            """UPDATE tasks SET status='offen', zuletzt_erledigt_am=?, faellig_am=?, updated_at=datetime('now'),
               updated_by=? WHERE id=?""", (datum, new_due, current_user()["id"], tid))
    else:
        db().execute("UPDATE tasks SET status='erledigt', zuletzt_erledigt_am=?, updated_at=datetime('now'),"
                     " updated_by=? WHERE id=?", (datum, current_user()["id"], tid))
    db().commit()
    return jsonify(ok=True, neue_faelligkeit=new_due)


# ---------- API: Medien (Bilder/Videos) ----------

def _exif_gps(img):
    try:
        from PIL.ExifTags import GPSTAGS, TAGS
        exif = img.getexif()
        gps_ifd = exif.get_ifd(0x8825) if exif else None
        if not gps_ifd:
            return None, None
        gps = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}

        def conv(v):
            return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
        lat, lon = conv(gps["GPSLatitude"]), conv(gps["GPSLongitude"])
        if gps.get("GPSLatitudeRef") == "S":
            lat = -lat
        if gps.get("GPSLongitudeRef") == "W":
            lon = -lon
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


@app.route("/api/medien", methods=["POST"])
@login_required
def api_medien_upload():
    from PIL import Image, ImageOps
    f = request.files.get("datei")
    if not f or not f.filename:
        return jsonify(error="Keine Datei"), 400
    ext = Path(f.filename).suffix.lower()
    oid = request.form.get("object_id", type=int)
    eid = request.form.get("event_id", type=int)
    bid = request.form.get("observation_id", type=int)
    typ_tag = request.form.get("typ_tag") or "allgemein"
    if typ_tag not in ("vorher", "nachher", "allgemein"):
        return jsonify(error="typ_tag ungültig"), 400
    gid = None
    if oid:
        o = db().execute("SELECT garden_id FROM objects WHERE id=?", (oid,)).fetchone()
        gid = o["garden_id"] if o else None
    elif bid:
        o = db().execute("SELECT o.garden_id FROM observations b JOIN objects o ON o.id=b.object_id WHERE b.id=?", (bid,)).fetchone()
        gid = o["garden_id"] if o else None
    elif eid:
        o = db().execute("SELECT garden_id FROM events WHERE id=?", (eid,)).fetchone()
        gid = o["garden_id"] if o else None
    if not gid or role_of(gid, current_user()["id"]) is None:
        return jsonify(error="Ziel nicht gefunden"), 404
    uid = uuid.uuid4().hex
    UPLOADS.mkdir(parents=True, exist_ok=True)
    if ext in IMAGE_EXT:
        raw = f.read(MAX_IMAGE + 1)
        if len(raw) > MAX_IMAGE:
            return jsonify(error="Bild größer als 10 MB"), 413
        try:
            img = Image.open(io.BytesIO(raw))
        except Exception:
            return jsonify(error="Bild konnte nicht gelesen werden (HEIC bitte als JPEG exportieren)"), 400
        lat, lon = _exif_gps(img)
        aufnahme = None
        try:
            ex = img.getexif().get(36867)  # DateTimeOriginal
            if ex:
                aufnahme = dt.datetime.strptime(ex, "%Y:%m:%d %H:%M:%S").date().isoformat()
        except Exception:
            pass
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((2048, 2048))
        name = f"{uid}.jpg"
        img.save(UPLOADS / name, "JPEG", quality=85, optimize=True)
        thumb = img.copy()
        thumb.thumbnail((400, 400))
        tname = f"{uid}_thumb.jpg"
        thumb.save(UPLOADS / tname, "JPEG", quality=80)
        art = "bild"
    elif ext in VIDEO_EXT:
        raw = f.read(MAX_VIDEO + 1)
        if len(raw) > MAX_VIDEO:
            return jsonify(error="Video größer als 200 MB"), 413
        name = f"{uid}{ext}"
        (UPLOADS / name).write_bytes(raw)
        tname = None
        lat = lon = aufnahme = None
        art = "video"
    else:
        return jsonify(error="Dateityp nicht erlaubt"), 400
    cur = db().execute(
        """INSERT INTO media(object_id, event_id, observation_id, art, pfad, thumb_pfad, original_name,
           groesse_bytes, aufnahme_datum, gps_lat, gps_lon, typ_tag, user_id)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (oid, eid, bid, art, name, tname, secure_filename(f.filename), len(raw),
         aufnahme if art == "bild" else None, lat, lon, typ_tag, current_user()["id"]))
    db().commit()
    return jsonify(id=cur.lastrowid, pfad=name, thumb=tname, gps=[lat, lon]), 201


@app.route("/api/objekte/<int:oid>/medien")
@login_required
def api_objekt_medien(oid):
    obj = db().execute("SELECT garden_id FROM objects WHERE id=?", (oid,)).fetchone()
    if not obj or role_of(obj["garden_id"], current_user()["id"]) is None:
        return jsonify(error="Nicht gefunden"), 404
    rows = db().execute("SELECT * FROM media WHERE object_id=? ORDER BY created_at DESC", (oid,)).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------- API: Kalender & Export ----------

@app.route("/api/gaerten/<int:gid>/kalender.ics")
@login_required
@garden_access()
def api_kalender(gid):
    rows = db().execute("SELECT id, titel, faellig_am FROM tasks WHERE garden_id=? AND status='offen' AND faellig_am IS NOT NULL", (gid,)).fetchall()
    termine = [{"uid": f"task-{r['id']}", "titel": r["titel"],
                "datum": dt.date.fromisoformat(r["faellig_am"]),
                "beschreibung": "Garten-Kartierung Pflegeaufgabe"} for r in rows]
    ics = ics_kalender(termine, name="Garten-Pflege")
    return Response(ics, mimetype="text/calendar",
                    headers={"Content-Disposition": f"attachment; filename=garten-{gid}.ics"})


@app.route("/api/gaerten/<int:gid>/export")
@login_required
@garden_access()
def api_export(gid):
    out = {"garten": dict(db().execute("SELECT * FROM gardens WHERE id=?", (gid,)).fetchone())}
    for key, sql in [
        ("objekte", "SELECT * FROM objects WHERE garden_id=?"),
        ("aufgaben", "SELECT * FROM tasks WHERE garden_id=?"),
        ("ereignisse", "SELECT * FROM events WHERE garden_id=?"),
    ]:
        out[key] = [dict(r) for r in db().execute(sql, (gid,)).fetchall()]
    return jsonify(out)


# ---------- Startseite / Heute-Daten ----------

@app.route("/api/heute")
@login_required
def api_heute():
    u = current_user()
    gardens = _gardens_for(u["id"])
    ids = [g_["id"] for g_ in gardens]
    if not ids:
        return jsonify([])
    q = ",".join("?" * len(ids))
    rows = db().execute(f"SELECT * FROM tasks WHERE garden_id IN ({q}) AND status='offen'", ids).fetchall()
    out = [_task_row(r) for r in rows]
    out.sort(key=lambda t: (t["prioritaet"], t["faellig_am"] or "9999"))
    return jsonify(out)


# ---------- Start ----------

init_db()
seed_garden()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5113, debug=False)
