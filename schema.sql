PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT
);

CREATE TABLE IF NOT EXISTS gardens (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    adresse TEXT,
    gemarkung TEXT,
    flurstuecke TEXT,           -- JSON-Liste der Flurstück-Kennzeichen
    polygon TEXT,               -- GeoJSON
    flaeche_m2 REAL,
    umfang_m REAL,
    notizen TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS garden_members (
    garden_id INTEGER NOT NULL REFERENCES gardens(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'meister')),
    PRIMARY KEY (garden_id, user_id)
);

CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY,
    garden_id INTEGER NOT NULL REFERENCES gardens(id) ON DELETE CASCADE,
    typ TEXT NOT NULL CHECK (typ IN ('pflanze', 'objekt')),
    kategorie TEXT,
    name TEXT NOT NULL,
    lexikon_key TEXT,
    geometrie TEXT,             -- GeoJSON Point/Polygon/LineString
    zustand INTEGER CHECK (zustand BETWEEN 1 AND 5),
    standort_notiz TEXT,
    pflanzdatum TEXT,
    created_by INTEGER REFERENCES users(id),
    updated_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    titel TEXT NOT NULL,
    text TEXT,
    kategorie TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    object_id INTEGER REFERENCES objects(id) ON DELETE CASCADE,
    garden_id INTEGER REFERENCES gardens(id) ON DELETE CASCADE,
    datum TEXT NOT NULL,
    typ TEXT NOT NULL,
    beschreibung TEXT,
    zustand_nach INTEGER CHECK (zustand_nach IS NULL OR zustand_nach BETWEEN 1 AND 5),
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    datum TEXT NOT NULL,
    phase TEXT NOT NULL,
    notiz TEXT,
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    object_id INTEGER REFERENCES objects(id) ON DELETE CASCADE,
    event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
    observation_id INTEGER REFERENCES observations(id) ON DELETE CASCADE,
    art TEXT NOT NULL CHECK (art IN ('bild', 'video')),
    pfad TEXT NOT NULL,
    thumb_pfad TEXT,
    original_name TEXT,
    groesse_bytes INTEGER,
    aufnahme_datum TEXT,
    gps_lat REAL,
    gps_lon REAL,
    typ_tag TEXT CHECK (typ_tag IS NULL OR typ_tag IN ('vorher', 'nachher', 'allgemein')),
    paar_id TEXT,
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_templates (
    id INTEGER PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    kategorie TEXT,
    intervall_monate INTEGER,
    saison TEXT,
    werkzeuge TEXT,
    sicherheit TEXT,
    anleitung TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    garden_id INTEGER NOT NULL REFERENCES gardens(id) ON DELETE CASCADE,
    object_id INTEGER REFERENCES objects(id) ON DELETE CASCADE,
    template_id INTEGER REFERENCES task_templates(id) ON DELETE SET NULL,
    titel TEXT NOT NULL,
    anleitung TEXT,
    intervall_monate INTEGER,
    faellig_am TEXT,
    zuletzt_erledigt_am TEXT,
    prioritaet INTEGER CHECK (prioritaet IS NULL OR prioritaet BETWEEN 1 AND 3),
    prio_manuell INTEGER CHECK (prio_manuell IS NULL OR prio_manuell BETWEEN 1 AND 3),
    saison TEXT,
    status TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'erledigt', 'verschoben')),
    created_by INTEGER REFERENCES users(id),
    updated_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    target_typ TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_objects_garden ON objects(garden_id);
CREATE INDEX IF NOT EXISTS idx_tasks_garden ON tasks(garden_id, status, faellig_am);
CREATE INDEX IF NOT EXISTS idx_events_object ON events(object_id, datum);
CREATE INDEX IF NOT EXISTS idx_obs_object ON observations(object_id, datum);
