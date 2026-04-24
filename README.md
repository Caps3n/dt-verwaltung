# DT-Verwaltung v1.3.0

Webbasierte Verwaltungslösung für die sichere Einlagerung von Datenträgern.
Entwickelt für Dienstleister, die Datenträger (HDDs, SSDs, Tapes, USB-Sticks u.ä.) im Auftrag von Kunden lagern, verwalten und dokumentiert zurückgeben.

---

## Features

### Übersicht / Dashboard
- KPIs: Aktive Verträge, eingelagerte Datenträger, Monats- und Jahresumsatz
- Ablaufwarnungen für auslaufende Verträge (60-Tage-Vorschau, farbkodiert)
- Wartungswarnungen für Tresore und Schränke

### Kunden & Verträge
- Vollständiges Kunden-CRUD mit Ansprechpartner, Adresse, Anrede
- Vertragsdaten: Vertragsnummer, Status, Laufzeit, Kündigungsfrist, Vertragsnotizen
- Vertragsdokument-Upload (PDF) pro Kunden
- **Multi-Firmen:** optionaler Rechnungsempfänger (Firma B zahlt für Firma A) und Eigentümer der DTs wählbar
- Mengenrabatte: bis zu 5 kundenspezifische Preisstaffeln
- Kundenverlauf / Vertragshistorie

### Datenträger (DTs)
- Einlagerung mit Typ, Seriennummer, **interner Nummer**, Preis/Einheit, Rabatt
- Foto-Upload pro Datenträger
- Eingangsprotokoll als druckfertiges PDF mit Briefkopf
- Statusverfolgung: `eingelagert` / `übergeben`
- Tresor-/Schrank-Zuweisung mit Standortanzeige
- CSV-Export mit allen Spalten inkl. Tresor-Standort und interner Nummer

### Übergabe-Workflow
- Schritt 1: Firma wählen, Datenträger auswählen, Übergabeprotokoll generieren und drucken
- Schritt 2: Unterschriebenes Dokument hochladen (optional), Übergabe abschließen
- **„Im Bestand lassen"**: Übergabe abschließen ohne DTs als übergeben zu markieren
- **Offene Übergaben löschen** mit 🗑-Button
- **Archiv aller abgeschlossenen Übergaben** mit Protokollnummer, Modus und PDF-Button

### Rechnungen
- Automatische Rechnungserstellung mit Mengenrabatt, Pauschalrabatt und MwSt.
- Rechnungshistorie mit PDF-Regenerierung pro Rechnung
- Mahnungsfunktion: 1./2./3. Mahnung pro Rechnung mit Druck-Button

### Tresorverwaltung (🔒)
- CRUD für physische Tresore/Schränke: Name, Hersteller, Modell, Seriennummer
- Standort: Land / Stadt / Gebäude / Etage / Raum
- Kaufdatum, Kaufpreis, jährliche Wartungskosten
- Letzter und nächster Wartungstermin
- Wartungsvertrag-Upload (PDF)
- Tresor-Detailansicht per Klick

### Templates & Briefvorlagen
- Logo-Upload, Akzentfarbe für alle Dokumente
- Vorlagen für: Rechnung, Übergabe, Eingangsprotokoll, Vertrag
- Live-Vorschau beim Bearbeiten
- Platzhalter-System (Firma, Datum, Beträge, DT-Liste etc.)

### Admin-Bereich
- Unternehmensdaten: Firmenname, Adresse, Bankverbindung, Steuernummer, Fußzeile
- Benutzerverwaltung: Anlegen, Passwort zurücksetzen, Rolle zuweisen
- Rollen & Berechtigungen: fein granulare Tab-Sichtbarkeit pro Rolle
- SAML 2.0 / SSO: Azure AD, Okta, Keycloak und andere IdPs

### Sicherheit
- Passwörter: PBKDF2-HMAC-SHA256 (600.000 Iterationen, zufälliger Salt)
- Sessions: 64-Zeichen kryptografisch sichere Tokens, DB-gesichert, 8h TTL
- Optionale SQLite-Verschlüsselung via SQLCipher AES-256 (`DB_KEY` in `.env`)
- Betrieb als Non-Root-Container (UID 1000)

---

## Deployment (Docker / Portainer)

### Portainer Stack (empfohlen)

```yaml
version: "3.8"
services:
  dtv:
    image: ghcr.io/caps3n/dt-verwaltung:latest
    ports:
      - "5000:5000"
    volumes:
      - dtv_data:/data
    environment:
      - ADMIN_PASSWORD=sicheresPasswort
      # - DB_KEY=verschlüsselungsSchlüssel   # nur bei Erstinstallation setzen
    restart: unless-stopped
    deploy:
      replicas: 1
      resources:
        limits:
          cpus: "1"
          memory: 512M

volumes:
  dtv_data:
```

1. Portainer → Stacks → Add Stack
2. Stack einfügen, `ADMIN_PASSWORD` setzen
3. Deploy the Stack
4. Öffnen: `http://<server-ip>:5000`

### Update auf neue Version

Portainer → Stack → **Pull and Redeploy**
(GitHub Actions baut automatisch bei jedem Push auf `main`)

---

## Lokale Entwicklung

```bash
git clone https://github.com/Caps3n/dt-verwaltung.git
cd dt-verwaltung
pip install flask flask-cors gunicorn pysaml2 cryptography
python app/server.py
```

Öffnen: `http://localhost:5000`
Standard-Login: `admin` / Passwort aus `ADMIN_PASSWORD` (Standard: `admin`)

---

## Datenbankstruktur

SQLite-Datenbank in `/data/dtv.db` (persistentes Docker-Volume).
Migrationen werden automatisch beim Start angewendet – kein manuelles Schema-Management nötig.

Optionale Verschlüsselung: `DB_KEY` in der Umgebung setzen **vor** dem ersten Start.
⚠️ Nachträgliches Aktivieren auf bestehender Datenbank wird nicht unterstützt.

---

## Technischer Stack

| Komponente | Technologie |
|---|---|
| Backend | Python 3.12, Flask 3.x, Gunicorn |
| Datenbank | SQLite (WAL-Modus), optional SQLCipher |
| Frontend | Vanilla JS SPA (kein Framework), HTML5, CSS3 |
| Authentifizierung | Token-basiert (`X-Token`-Header), optional SAML 2.0 |
| Container | Docker, non-root (UID 1000), Health-Check |
| CI/CD | GitHub Actions → ghcr.io |

---

## Lizenz

MIT License — © 2025 Marcel Capelan · [capelan.de](https://capelan.de)
