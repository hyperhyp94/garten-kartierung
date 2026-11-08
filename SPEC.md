# Garten-Kartierung — Pflichtenheft

Web-App (Flask + SQLite + Leaflet), läuft auf dem Raspberry Pi unter `0.0.0.0:5113`.
Sprache der Oberfläche: Deutsch. Mobile-first (Sven benutzt Handy), Bedienung über große Buttons und eine Bottom-Navigation.

## 1. Zweck

Gärten kartieren, Pflanzen und Objekte erfassen, Wissen und Pflegehistorie speichern und Pflege über Jahre planen.
Zwei Rollen arbeiten gemeinsam an einem Garten:
- **Meister** (Johannes): Fachberater. Legt Pflanzen/Objekte an, pflegt Wissen und Anleitungen, legt Pflegeaufgaben an und setzt Prioritäten.
- **Lehrling / Gartenbesitzer** (Sven): führt Pflege aus, dokumentiert (Protokoll, Fotos, Videos), bestätigt Aufgaben.

Nutzer sind fest: `sven` und `johannes`. Keine Registrierung, keine weiteren Nutzer.

## 2. Rollen und Rechte (pro Garten)

Tabelle `garden_members(garden_id, user_id, role)`, role ∈ {`owner`, `meister`}.
- Sven ist `owner` seiner Gärten. Johannes ist `meister` derselben Gärten.
- Ein Garten kann mehrere Mitglieder haben, aber für v1 reichen diese beiden.
- `owner` und `meister` dürfen beide: Objekte, Wissen, Ereignisse, Fotos/Videos, Aufgaben, Kommentare.
- Nur `meister` darf Aufgaben-Priorität und Anleitungen ändern, Aufgaben anlegen und Vorlagen bearbeiten. Der `owner` darf Aufgaben abhaken und Ereignisse eintragen.
- Garten löschen und Mitglieder verwalten: nur `owner`.
- Jede Änderung wird mit Benutzer und Zeitstempel protokolliert (`audit`-Felder `created_by`, `updated_by`).

## 3. Login und Sicherheit

- Login mit Benutzername und Passwort (Werkzeug `generate_password_hash`).
- Passwörter werden NIE im Code, in Logs oder Chat gesetzt. Es gibt ein CLI-Skript `scripts/set_password.py <username>`, das das Passwort von **stdin** liest. Ohne Passwort ist der Login für den Nutzer gesperrt.
- Session-Cookie: HttpOnly, SameSite=Lax, `Secure` wenn Request über HTTPS (Header `X-Forwarded-Proto`).
- CSRF-Schutz für alle POST/PUT/DELETE (Token im Formular bzw. Header `X-CSRF-Token`).
- Upload-Pfade nur über generierte Dateinamen (UUID), nie Originalnamen als Pfad.
- Kein Passwort oder Secret im Frontend.

## 4. Datenmodell (SQLite, `data/garten.db`)

- **users**: id, username, display_name, password_hash
- **gardens**: id, name, adresse, gemarkung, flur, flurstuecke (JSON-Liste der Kennzeichen), polygon (GeoJSON), flaeche_m2, notizen, created_by, created_at
- **garden_members**: garden_id, user_id, role
- **objects**: id, garden_id, typ (`pflanze` | `objekt`), kategorie (Baum, Strauch, Staude, Gemüse, Rasen, Beet, Weg, Teich, Zaun, Gebäude, Sonstiges), name, lexikon_id (nullable), geometrie (GeoJSON Point oder Polygon), zustand (1–5, siehe §7), standort_notiz, pflanzdatum (nullable), created_by, updated_by, timestamps
- **knowledge**: id, object_id, titel, text (Markdown), kategorie (Pflege, Standort, Krankheit, Sorte, Sonstiges), created_by, timestamps
- **events** (Pflege-Protokoll): id, object_id oder garden_id, datum, typ (Schnitt, Düngen, Gießen, Pflanzen, Umpflanzen, Pflanzenschutz, Ernte, Beobachtung, Sonstiges), beschreibung, user_id, zustand_nach (optional, 1–5), aufgabe_id (nullable, verweist auf erledigte Aufgabe)
- **observations** (Watch-Kalender / Trieb-Beobachtung): id, object_id, datum, phase (Knospe, Austrieb, Blüte, Fruchtansatz, Ernte, Laubfall, Ruhe, Sonstiges), notiz, user_id
- **media**: id, object_id oder event_id oder observation_id, art (`bild` | `video`), pfad, thumb_pfad, aufnahme_datum, gps_lat, gps_lon, typ_tag (`vorher` | `nachher` | `allgemein`), paar_id (nullable, verbindet vorher/nachher), created_by
- **task_templates** (Pflege-Vorlagen mit Anleitung): id, name, kategorie, anleitung (Markdown), standard_intervall_monate, saison (z. B. "Feb–Mär"), werkzeuge, sicherheit
- **tasks** (Pflegeaufgaben am konkreten Objekt): id, garden_id, object_id, template_id (nullable), titel, anleitung (Markdown, überschreibt Vorlage), intervall_monate (nullable = einmalig), faellig_am, zuletzt_erledigt_am, prioritaet (1 hoch, 2 mittel, 3 niedrig), prio_auto (bool), status (`offen` | `erledigt` | `verschoben`), created_by, timestamps
- **comments**: id, target_typ, target_id, text, user_id, created_at
- **audit**: optional, nur wenn einfach umsetzbar

## 5. Karte und Flurstücke

- Karte mit Leaflet (lokal vendored unter `static/vendor/`, keine CDN-Abhängigkeit für die Kernfunktionen). Basiskarte: OpenStreetMap-Kacheln (nur zur Anzeige auf dem Handy).
- **Flurstücke:** Datei `data/flurstuecke_feggendorf.geojson` (bereits vorhanden, 663 Flurstücke Gemarkung Feggendorf, Eigenschaften: `flurstueck`, `flur`, `gemarkung`, `flaeche_m2`, `kennzeichen`). Die Datei ist die einzige Quelle. **Keine weiteren Gemarkungen, keine Live-Abfragen beim Betrieb.**
  - Flurstücke als Layer anzeigen (Umrisse, Beschriftung ab Zoom 17).
  - Beim Anlegen eines Gartens: Flurstücke antippen, um sie dem Garten zuzuordnen (Mehrfachauswahl). Gewählte Flurstücke werden in `flurstuecke` gespeichert.
- **Garten zeichnen:** Polygon auf der Karte zeichnen (leaflet-draw vendored), Punkte setzen, Fläche (m²) und Umfang (m) automatisch berechnen (Geodäsie: WGS84, Berechnung mit pyproj oder eigene Formel über UTM32N). Optional: Polygon aus Flurstück übernehmen.
- **Objekte** auf der Karte: Punkt (Pflanze), Polygon (Beet, Teich, Rasen, Gebäude) oder Linie (Weg, Zaun). Tippen auf Objekt öffnet Detail.
- Ebenen-Umschalter: Luftbild/OSM (nur Anzeige), Flurstücke ein/aus, Objekte ein/aus, Aufgaben-Marker ein/aus.

## 6. GPS / Vermessung (Handy-GPS im Browser)

- Browser-Geolocation (`navigator.geolocation.watchPosition`), benötigt HTTPS. Auf dem Pi läuft die App per Cloudflare-Tunnel mit HTTPS. Lokal im LAN funktioniert GPS nicht. Das ist dokumentiert im Hinweis auf der Seite.
- Funktionen:
  1. **„Ich bin hier“:** eigenen Standort anzeigen, mit einem Klick Pflanze/Objekt an dieser Stelle anlegen. Genauigkeit (m) anzeigen.
  2. **Punkt einmessen:** GPS-Mittelwert über ca. 10 Sekunden (Glättung), Genauigkeit angeben.
  3. **Begehung/Umgrenzung:** Gartenrand oder Beet abgehen, Track aufzeichnen, dann als Polygon speichern. Fläche und Umfang anzeigen.
  4. **Abstand messen:** zwei Punkte, Entfernung in m (Haversine).
- Hinweis in der App: „GPS-Vermessung ist eine Orientierungsmessung, keine amtliche Vermessung. Genauigkeit des Handys: ca. ±3–10 m.“
- Jede GPS-Messung speichert Genauigkeit und Zeitpunkt.

## 7. Zustand und Priorität (Kern der Planung)

- **Zustand** eines Objekts: 1 = kritisch, 2 = schlecht, 3 = mittel, 4 = gut, 5 = sehr gut. Wird bei jedem Ereignis mit `zustand_nach` oder manuell gesetzt. Die Historie bleibt in `events` erhalten, so dass sich die Entwicklung zeigen lässt (kleines Verlaufsdiagramm).
- **Priorität automatisch (`prio_auto`):** Score aus
  - Überfälligkeit (Tage über `faellig_am`),
  - Zustand des Objekts (niedriger = wichtiger),
  - Saison-Fenster (in der richtigen Saison = höher, außerhalb = niedriger),
  - manuelle Prio des Meisters (überschreibt die Automatik, `prio_auto=false`).
  - Ergebnis: Prio 1/2/3, sichtbar als Ampel. Die Berechnung ist eine reine, testbare Funktion `berechne_prioritaet(task, objekt, heute)`.
- **Prio-Liste:** Startseite zeigt die Aufgaben nach Priorität und Fälligkeit, gruppiert nach „Diese Woche“, „Dieser Monat“, „Später“, „Überfällig“.
- **Erledigen:** Aufgabe abhaken öffnet das Protokoll-Formular (Beschreibung, optional Foto/Video vorher/nachher, neuer Zustand). Wiederkehrende Aufgaben setzen `faellig_am = heute + intervall_monate` automatisch neu.

## 8. Pflege-Protokoll und Watch-Kalender

- **Protokoll pro Objekt:** Zeitstrahl aus `events`, `observations` und Medien. Filter nach Typ und Jahr.
- **Vorher/Nachher:** Ein Ereignis kann Fotos mit `typ_tag=vorher` und `nachher` haben. Die Ansicht zeigt beide nebeneinander (Schieberegler optional).
- **Watch-Kalender (Triebbeobachtung):** Beobachtungen mit Phase und Foto, z. B. „Knospe am 12.03.“, „Austrieb am 20.03.“. Die Übersicht zeigt pro Objekt eine Zeitleiste über das Jahr und Jahresvergleich („2025 Blüte am 14.04., 2026 am 10.04.“).
- **Export:** ICS-Datei (iCalendar) für Pflegeaufgaben und Beobachtungs-Erinnerungen. Jede Kalender-Erinnerung erhält **zwei** `VALARM` (1 Tag vorher und 1 Stunde vorher). Die Datei wird über einen Link heruntergeladen, nicht automatisch in iCloud geschrieben.

## 9. Lexikon (Startbibliothek)

- Datei `data/lexikon.json`, vorbefüllt mit typischen Pflanzen aus dem Raum Feggendorf/Lauenau/Deister (Mittelgebirgs- und Stadtrandklima, leicht lehmige bis sandige Böden):
  Hortensie, Rhododendron, Buchs, Apfel (Streuobst), Kirsche, Zwetschge, Walnuss, Haselnuss, Flieder, Forsythie, Rose, Lavendel, Sommerflieder, Hainbuche, Stieleiche, Rotbuche, Eibe, Thuja, Kirschlorbeer, Liguster, Weigelie, Clematis, Brombeere, Himbeere, Johannisbeere, Stachelbeere, Erdbeere, Salbei, Thymian, Pfingstrose, Funkie, Rasen, Gemüsebeet (Kartoffel, Tomate, Bohne, Kohl), Obstspalier.
- Pro Eintrag: Name, lateinischer Name, Typ, Standort (Sonne/Halbschatten/Schatten), Boden, Wuchshöhe, Blütezeit, Schnittzeitpunkt, Pflegehinweise, typische Krankheiten/Schädlinge, Lebenserwartung, Hinweise.
- **Wichtig:** Inhalte sind Richtwerte aus allgemeinem Gartenwissen und sollen im Feld geprüft werden. Im Eintrag steht „Richtwert, vor Ort prüfen“.
- Lexikon ist durchsuchbar. Beim Anlegen eines Objekts kann man einen Lexikon-Eintrag wählen, dann werden Standort und typische Pflegeaufgaben (Vorlagen) übernommen.
- Anleitungs-Vorlagen (`task_templates`): mindestens 15 Vorlagen (z. B. Obstbaum-Schnitt, Hecke schneiden, Rasen vertikutieren, Gießplan, Düngen, Mulchen, Winterschutz, Pflanzenschutz gegen Schädlinge). Jede mit Schritt-für-Schritt-Anleitung, Zeitpunkt und Sicherheitshinweisen.

## 10. Oberfläche (intuitiv, aber mit „Eindruck“)

- Farbschema grün-erdig, Karten mit klaren Symbolen, Ampeln für Prio und Zustand.
- Bottom-Navigation: **Karte · Heute · Objekte · Lexikon · Mehr**.
- Startseite „Heute“: Begrüßung, Wetter-Platzhalter (optional, nicht erforderlich), Prio-Liste, „Neue Beobachtung“-Button, „Ich bin hier“-Button.
- Großer Floating-Button „+“: Objekt anlegen, Ereignis, Beobachtung, Foto/Video.
- Objekt-Detail mit Tabs: Übersicht · Wissen · Protokoll · Beobachtungen · Bilder · Aufgaben.
- Leere Zustände mit kurzen Hilfetexten. Fehler verständlich auf Deutsch.
- Keine Tooltips als einzige Hilfe. Keine versteckten Gesten.

## 11. Medien

- Bilder: JPEG, PNG, HEIC (Konvertierung zu JPEG über Pillow mit `pillow-heif`, wenn verfügbar, sonst Hinweis). Max. **10 MB** pro Bild. Serverseitig auf max. 2048 px verkleinert, Thumbnail 400 px. EXIF-GPS wird ausgelesen und gespeichert, sonstige EXIF-Daten werden entfernt.
- Videos: MP4/MOV/WebM, max. **200 MB** pro Datei, keine Umkodierung (nur Speicherung). Vorschaubild optional.
- Speicherort: `data/uploads/` mit UUID-Dateinamen. Auslieferung über Flask `send_from_directory` mit Auth-Prüfung.

## 12. API und Seiten

- HTML-Seiten (Jinja2) für die Oberfläche, JSON-API unter `/api/...` für Karte und Aktionen (fetch).
- Mindestens: `/login`, `/logout`, `/`, `/heute`, `/gaerten`, `/gaerten/<id>` (Karte), `/objekte/<id>`, `/aufgaben`, `/lexikon`, `/lexikon/<id>`, `/vorlagen`, `/kalender.ics?garten=<id>`, `/health` (ohne Login, für Monitoring).
- API: CRUD für gardens, objects, knowledge, events, observations, media, tasks, comments; GET `/api/data/feggendorf-flurstuecke`.
- Alle Routen sind geschützt (außer `/login` und `/health`).

## 13. Technik und Betrieb

- Python 3.13, venv unter `.venv/`, `requirements.txt` (flask, pillow, pillow-heif optional, pyproj, python-dateutil, gunicorn optional, pytest).
- `app.py` mit `app.run(host='0.0.0.0', port=5113, debug=False)` für den Start. Gunicorn ist optional.
- Konfiguration über Umgebungsvariablen, Default-Pfade im Projekt. **Keine Secrets im Repo.** Ein `SECRET_KEY` wird beim ersten Start in `data/secret_key` erzeugt (Dateirechte 600).
- `.gitignore`: `data/garten.db`, `data/uploads/`, `data/secret_key`, `.venv/`, `__pycache__/`. Das GeoJSON und `data/lexikon.json` gehören ins Repo.
- Datenbank-Migration: Schema per `schema.sql` beim Start idempotent anlegen.
- Logging: nach stdout, keine Passwörter und keine Koordinaten im Log bei Fehlern.
- Export/Backup: Endpunkt `/api/export` liefert JSON aller Daten eines Gartens. Keine Binärdateien.

## 14. Tests (Pflicht)

- `pytest` mit mindestens:
  - Login/Rollen: Lehrling darf keine Vorlagen ändern, Meister schon. Fremder Garten ist nicht sichtbar.
  - Prioritätsfunktion: überfällig + niedriger Zustand = Prio 1; außerhalb der Saison niedriger.
  - Wiederkehrende Aufgabe: nach Erledigung neues Fälligkeitsdatum.
  - Upload: Bildgröße > 10 MB wird abgelehnt, Bild wird verkleinert, GPS aus EXIF gelesen.
  - ICS-Export enthält pro Erinnerung zwei VALARM.
  - Flurstück-Endpunkt liefert 663 Features.
  - Flächenberechnung eines bekannten Rechtecks (±1 %).
- Smoke-Test per curl: `/health` = 200, `/login` = 200, geschützte Route ohne Login = 302 oder 401.
- Vor Abschluss: App starten, Smoke-Test ausführen, Ergebnis im Abschlussbericht nennen (echter Output).

## 15. Startdaten (Seed)

- Garten **„Garten Deisterstraße 40“** (Feggendorf, Lauenau), Besitzer `sven`, Meister `johannes`, Flurstück 56/7 Flur 001 Gemarkung Feggendorf als Vorauswahl (nur Vorschlag, nicht zwingend).
- Keine Pflanzen oder Aufgaben vorab, außer den Vorlagen aus §9. Die Daten sollen Sven und Johannes selbst erfassen.

## 16. Abnahmekriterien

1. App läuft auf `http://192.168.1.134:5113` und ist im LAN erreichbar.
2. Login für `sven` und `johannes` funktioniert (Passwörter werden extern gesetzt, siehe §3).
3. Garten anlegen, Flurstück wählen, Polygon zeichnen, Fläche sichtbar.
4. Pflanze aus Lexikon anlegen, Foto hochladen, Wissen eintragen, Pflegeaufgabe mit Anleitung anlegen.
5. Aufgabe erledigen (mit Vorher/Nachher-Foto), Zustand ändern, Folgetermin entsteht.
6. Beobachtung „Knospe“ und „Austrieb“ erfassen, Zeitleiste zeigt beides.
7. ICS-Export lädt und enthält zwei Alarme pro Termin.
8. GPS-Funktionen sind im Code vorhanden und per Test beschrieben. Echte GPS-Messung wird von Sven am Handy geprüft (über Tunnel mit HTTPS).
9. `pytest` grün. Smoke-Test grün.

## 17. Was NICHT gebaut wird (v1)

- Keine amtliche Vermessung, keine Vermessungsbehörden-Schnittstelle.
- Keine Flurstücke außerhalb der Datei Feggendorf.
- Keine Registrierung weiterer Nutzer.
- Keine Cloud-Synchronisation, kein Offline-Modus mit Service Worker (v2).
- Kein Wetter-Dienst (Platzhalter erlaubt).
