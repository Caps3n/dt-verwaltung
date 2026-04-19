# 💾 DT-Verwaltung v1.0

**Webbasierte Verwaltungssoftware für eingelagerte Datenträger**  
Entwickelt von [Marcel Capelan](https://capelan.de) · [marcel.capelan@tuv.com](mailto:marcel.capelan@tuv.com)

[![Docker](https://img.shields.io/badge/Docker-ready-blue?logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12-green?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📋 Funktionsübersicht

| Bereich | Funktion |
|---|---|
| 📊 Dashboard | Kennzahlen, aktive Verträge, Umsatz-Übersicht, Ablaufwarnungen |
| 👥 Kunden | Anlegen, bearbeiten, Vertragsdaten, kundenspezifischer Mengenrabatt |
| 📄 Verträge | Übersicht aller Verträge, Druck mit Briefvorlage |
| 💾 Datenträger | Einlagern, bearbeiten, Foto, Eingangsprotokoll drucken |
| 🔄 Übergabe | Rückgabe-Workflow mit druckfertigem Übergabeprotokoll |
| 🧾 Rechnung | Automatische Abrechnung, Mengenrabatt, allg. Rabatt, MwSt. |
| 📋 Rechnungen | Rechnungshistorie, erneuter Druck, Mahnungsfunktion |
| 🗄️ DT Archiv | Alle übergebenen Datenträger, Suchfunktion |
| 🎨 Templates | Briefvorlagen für alle Dokumente, Logo, Akzentfarbe |
| ⚙️ Admin | Benutzerverwaltung, Rollen & Berechtigungen, SAML/SSO |
| ❓ Hilfe | FAQ-Dokumentation, Kontakt |

---

## 🚀 Installation

### Voraussetzungen

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2

### Schnellstart

```bash
# 1. Repository klonen
git clone https://github.com/DEIN-USER/dt-verwaltung.git
cd dt-verwaltung

# 2. Umgebungsvariablen anpassen (optional)
cp .env.example .env
nano .env

# 3. Starten
docker compose up -d --build

# 4. Browser öffnen
http://localhost:8123
```

**Standard-Login:**
```
Benutzername: admin
Passwort:     admin123
```
> ⚠️ Bitte das Passwort nach dem ersten Login ändern!

### Port anpassen

```bash
PORT=9000 docker compose up -d --build
```

---

## ⬆️ Update

```bash
docker rm -f dtv-verwaltung
docker compose up -d --build
```

Die Datenbank liegt in einem Docker-Volume (`dtv-data`) und **bleibt beim Update erhalten**.

---

## 🔄 Neustart / Stoppen

```bash
# Stoppen
docker compose down

# Starten
docker compose up -d

# Logs anzeigen
docker logs dtv-verwaltung -f
```

---

## 🗄️ Datensicherung

```bash
# Backup erstellen
docker run --rm -v dtv-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/dtv-backup-$(date +%Y%m%d).tar.gz /data

# Backup wiederherstellen
docker run --rm -v dtv-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/dtv-backup-DATUM.tar.gz -C /
```

---

## 👤 Benutzer & Rollen

Drei Standard-Rollen werden automatisch angelegt:

| Rolle | Lesen | Schreiben | Löschen | Templates | Benutzer |
|---|:---:|:---:|:---:|:---:|:---:|
| **Admin** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **User** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Viewer** | ✅ | ❌ | ❌ | ❌ | ❌ |

Eigene Rollen mit individuellen Tab-Sichtbarkeiten können im Admin-Bereich erstellt werden.

---

## 🔐 SAML / Single Sign-On (optional)

SAML 2.0 wird unterstützt (Azure AD, Okta, Keycloak, u.a.).  
Konfiguration unter **⚙️ Admin → SAML/SSO**.

---

## 🏗️ Technische Details

| Komponente | Technologie |
|---|---|
| Backend | Python 3.12, Flask 3.x, Gunicorn |
| Datenbank | SQLite (WAL-Modus, Docker-Volume) |
| Frontend | Vanilla JS, Single-Page-App (kein Framework) |
| Container | Docker, nicht-root User (UID 1000) |
| Auth | Token-basiert (X-Token Header), DB-backed Sessions |

### Projektstruktur

```
dt-verwaltung/
├── app/
│   ├── server.py          # Flask-Backend, alle API-Routen
│   ├── saml_auth.py       # SAML 2.0 Hilfsfunktionen (optional)
│   └── static/
│       └── index.html     # Frontend Single-Page-App
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

### API-Endpunkte (Übersicht)

```
GET/POST   /api/kunden
GET/PUT    /api/kunden/<id>
DELETE     /api/kunden/<id>

GET/POST   /api/datentraeger
GET/PUT    /api/datentraeger/<id>
DELETE     /api/datentraeger/<id>
GET        /api/datentraeger/<id>/bild

GET/POST   /api/uebergaben
GET        /api/uebergaben/<id>

GET/PUT    /api/template_settings
GET/PUT    /api/template_settings/logo

GET/POST   /api/rollen
PUT/DELETE /api/rollen/<id>

GET/POST   /api/benutzer
PUT        /api/benutzer/<id>
DELETE     /api/benutzer/<id>

POST       /api/login
POST       /api/logout
GET        /api/me
GET        /api/health
```

---

## 📄 Lizenz

MIT License — © 2025 [Marcel Capelan](https://capelan.de)

---

## 📞 Kontakt & Support

**Marcel Capelan**  
📧 [marcel.capelan@tuv.com](mailto:marcel.capelan@tuv.com)  
🌐 [capelan.de](https://capelan.de)
