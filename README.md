# Garten-Kartierung

Web-App fürs Handy, um einen Garten zu kartieren und die Pflege über Jahre gemeinsam mit einem Fachmann zu planen. Sie läuft auf dem Raspberry Pi zu Hause.

1. Was die App können soll, steht in [ANFORDERUNGEN.md](ANFORDERUNGEN.md).
2. Wie und in welcher Reihenfolge sie gebaut wird, steht in [PLAN.md](PLAN.md).

## Stand

Stufe 1 von 5 ist fertig. Man kann sich anmelden, einen Garten anlegen, das Grundstück über Flurstücke auf dem Luftbild auswählen und die Karte mit Grenze öffnen. Der Kartenausschnitt lässt sich als Start merken, und die App lässt sich auf dem Startbildschirm installieren. Pflanzen, Aufgaben und alles Weitere folgen in den Stufen 2 bis 5.

## Auf dem Raspberry Pi einrichten

```bash
git clone https://github.com/hyperhyp94/garten-kartierung.git
cd garten-kartierung
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Passwörter setzen. Die Eingabe ist verdeckt, das Passwort braucht mindestens 10 Zeichen. Ohne Passwort ist ein Konto gesperrt.

```bash
.venv/bin/flask --app garten passwort sven
.venv/bin/flask --app garten passwort johannes
```

Zum Ausprobieren starten:

```bash
.venv/bin/gunicorn --workers 1 --threads 8 --bind 0.0.0.0:5113 "garten:create_app()"
```

Danach ist die App im WLAN unter `http://<Adresse des Pi>:5113` erreichbar.

Für den Dauerbetrieb liegt in `deploy/garten.service` ein Dienst, der die App beim Hochfahren startet. In `deploy/garten-sicherung.timer` liegt die nächtliche Sicherung der Datenbank. In beiden Dateien stehen oben die nötigen Befehle. Benutzer und Pfad müssen zum Pi passen.

## Von unterwegs und mit GPS: der Tunnel

Der Browser gibt den Standort nur über HTTPS frei, und von unterwegs ist der Pi ohne Tunnel nicht erreichbar. Zum schnellen Testen reicht ein Tunnel mit zufälliger Adresse:

```bash
cloudflared tunnel --url http://localhost:5113
```

Diese Adresse ändert sich bei jedem Start. Eine App auf dem Startbildschirm ist an ihre Adresse gebunden, deshalb braucht der Dauerbetrieb eine feste Adresse. Dafür gibt es bei Cloudflare benannte Tunnel mit eigener Domain:

```bash
cloudflared tunnel login
cloudflared tunnel create garten
cloudflared tunnel route dns garten garten.example.de
cloudflared tunnel run --url http://localhost:5113 garten
```

## Daten

Alles, was beim Betrieb entsteht, liegt im Ordner `instance/` und gehört nicht ins Repo.

| Datei | Inhalt |
|---|---|
| `instance/garten.db` | Die Datenbank |
| `instance/secret_key` | Schlüssel für die Anmeldung, wird beim ersten Start erzeugt |
| `instance/kacheln/` | Zwischengespeichertes Luftbild, darf jederzeit gelöscht werden |
| `instance/sicherung/` | Die letzten 14 Sicherungen der Datenbank |

Die Sicherung liegt auf derselben Speicherkarte wie die Datenbank. Sie schützt vor Fehlern, nicht vor einer kaputten Karte. Den Ordner `instance/` deshalb ab und zu auf ein anderes Gerät kopieren.

## Aktualisieren

```bash
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart garten
```

Die Datenbank bringt sich beim Start selbst auf den neuesten Stand.

## Entwickeln und Testen

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/flask --app garten run --debug --port 5113
```

| Ordner | Inhalt |
|---|---|
| `garten/` | Die App: Anmeldung, Gärten, Karte, Seiten |
| `garten/templates/` | Die Seiten |
| `garten/static/` | Gestaltung, JavaScript, Symbole und die Kartenbibliothek Leaflet |
| `data/` | Flurstücke der Gemarkung Feggendorf |
| `tests/` | Automatische Tests |
| `deploy/` | Dienste für den Raspberry Pi |

## Quellen

Luftbild und Flurstücke stammen vom Landesamt für Geoinformation und Landesvermessung Niedersachsen (LGLN) und stehen unter CC BY 4.0. Die Straßenkarte stammt von den OpenStreetMap-Mitwirkenden. Die Karte wird mit Leaflet angezeigt.
