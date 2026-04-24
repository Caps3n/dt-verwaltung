# Changelog

All notable changes to DT-Verwaltung are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.3.0] – 2026-04-24

### Added
- **Übergabe-Archiv** — abgeschlossene Übergaben direkt im Tab mit PDF-Button und Protokollnummer
- **Offene Übergaben löschen** — 🗑-Button pro Eintrag; löscht Übergabe + Positionen aus DB
- **„Im Bestand lassen"** — Übergabe abschließen ohne DTs auf "übergeben" zu setzen
- **Dokument-Upload optional** — Abschließen auch ohne Scan (mit Bestätigungsdialog)
- **Interne Nummer für Datenträger** — Feld beim Anlegen/Bearbeiten, Spalte in Liste und CSV
- **Multi-Firmen** — Rechnungsempfänger + Eigentümer pro Kunde; Firma A lagert, Firma B zahlt
- **Hilfe-Layout** — volle Breite, kein `max-width`-Limit mehr
- **Mobile** — Tab-Leiste scrollt horizontal, Tabellen scrollbar auf kleinen Screens

### Fixed
- **Übergabe Empfänger-Bug** — Feld `Empfänger` (falsch) → `empfaenger` (korrekt)
- **DB-Migrationen** — neue Spalten werden automatisch beim Start ergänzt

---

## [1.2.0] – 2026-04-20

### Added
- DT Archiv als Sub-Tab, Kunden & Verträge merged, Rechnungen merged
- Tresor Detail-Ansicht, Anrede-Feld, Unternehmensdaten im Admin
- PDF-Button in Rechnungshistorie, Mahnungen in Rechnungshistorie

### Fixed
- Tresor-Dropdown beim DT-Bearbeiten, Übergabe-Abschluss nach Dokument-Download
- Berechtigungs-Cleanup (gemergete Tabs), Responsive Design

---

## [1.1.1] – 2026-04-20

### Fixed
- Tresor speichern/löschen löste unbeabsichtigten Logout aus (localStorage vs sessionStorage)

### Added
- Tresor-Tab Berechtigung in Rollenverwaltung, Responsive Design

---

## [1.1.0] – 2026-04-20

### Added
- Tresorverwaltung (🔒 Tresore) mit vollem CRUD, Standort, Wartungsdaten
- Tresor-Zuweisung auf Datenträger, Dashboard-Wartungswarnungen
- CSV-Export mit Tresor-Spalten, optionale DB-Verschlüsselung (SQLCipher)

---

## [1.0.0] – 2025-04-19

### 🎉 Initial public release

- Dashboard, Kunden, Mengenrabatte, Datenträger, Eingangsprotokoll
- Übergabe-Workflow, Rechnungen, Archiv, Templates, Admin, SAML 2.0
- PBKDF2-Sicherheit, Docker Swarm, Health-Check

---

*© 2025 Marcel Capelan — [capelan.de](https://capelan.de)*
