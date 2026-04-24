# Changelog

All notable changes to DT-Verwaltung are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.3.0] – 2026-04-24

### Added
- **Übergabe-Archiv** — abgeschlossene Übergaben direkt im Tab mit Protokollnummer, Firma, Datum, Anzahl DT, Grund und PDF-Button
- **Offene Übergaben löschen** — 🗑-Button pro Eintrag; löscht Übergabe + Positionen aus der Datenbank
- **„Im Bestand lassen"** — neue Schaltfläche beim Abschließen: Übergabe wird abgeschlossen, DTs bleiben als `eingelagert` (für Fälle wo Kunde DTs vorübergehend mitnimmt aber weiterzahlt)
- **Dokument-Upload optional** — Übergabe kann ohne hochgeladenes Dokument abgeschlossen werden (Bestätigungsdialog)
- **Interne Nummer für Datenträger** — Freitextfeld `Interne Nr.` beim Anlegen/Bearbeiten, sichtbar in der DT-Liste und im CSV-Export
- **Multi-Firmen-Logik** — optionaler Rechnungsempfänger und Eigentümer pro Kundeneintrag wählbar: Firma A lagert ein, Firma B ist Eigentümer, Firma C zahlt die Rechnung
- **Hilfe-Layout** — Inhalt nutzt jetzt volle Breite (kein `max-width`-Limit mehr)
- **Mobile Ansicht** — Tab-Leiste scrollt horizontal ohne Umbruch, Tabellen horizontal scrollbar auf kleinen Screens, kompakteres Padding auf < 600 px

### Fixed
- **Übergabe Empfänger-Bug** — Empfänger-Feld wurde mit falschem JS-Schlüssel (`Empfänger`) gesendet und landete leer in der DB; jetzt korrekt (`empfaenger`)
- **DB-Migrationen** — neue Spalten (`weiter_im_bestand`, `interne_nr`, `rechnungsempfaenger_id`, `eigentuemer_id`) werden beim nächsten Start automatisch zur bestehenden DB ergänzt

### Changed
- Übergabe-Button zeigt Bestätigungsdialog wenn kein Dokument vorhanden statt Blockierung
- Abgeschlossene Übergaben erscheinen sofort im Archiv ohne Seitenreload

---

## [1.2.0] – 2026-04-20

### Added
- DT Archiv als Sub-Tab (Datenträger → Erfassen / Archiv)
- Kunden & Verträge als ein Tab mit Sub-Navigation
- Rechnungen & Historie als ein Tab mit Sub-Navigation
- Tresor Detail-Ansicht mit Klick auf Tresor-Name
- Anrede-Feld (Herr / Frau / Dr. / Prof. / Divers) für Ansprechpartner
- Unternehmensdaten im Admin-Bereich statt im Templates-Bereich
- PDF-Button pro Rechnung in der Rechnungshistorie
- Mahnungen pro Rechnung in der Rechnungshistorie mit Druck-Button

### Fixed
- Tresor-Dropdown beim DT-Bearbeiten war leer
- Übergabe-Abschluss nach Dokument-Download lief in Fehler
- Veraltete Tab-Berechtigungen aus Rollenverwaltung entfernt
- Responsive Design: Tab-Leiste umbrechend statt scrollend

---

## [1.1.1] – 2026-04-20

### Added
- Tresor-Tab Berechtigung: Rollen können Tresore-Tab ein-/ausblenden
- Responsive Design für Tablet und Mobile

### Fixed
- Tresor speichern/löschen löste unbeabsichtigten Logout aus (`localStorage` vs `sessionStorage`)

---

## [1.1.0] – 2026-04-20

### Added
- Tresorverwaltung (🔒 Tresore) — vollständiges CRUD mit Standort, Kaufdaten, Wartungsterminen, Wartungsvertrag-Upload
- Tresor-Zuweisung bei Datenträger-Einlagerung
- Dashboard: Wartungswarnungen für Tresore (60-Tage-Vorschau)
- CSV-Export erweitert um Tresor-Standort-Spalten
- Optionale SQLite-Verschlüsselung via `DB_KEY` (SQLCipher AES-256)

### Changed
- Kontakt-E-Mail: `marcel.capelan@tuv.com` → `info@capelan.de`

---

## [1.0.0] – 2025-04-19

### 🎉 Erste öffentliche Version

- Dashboard mit KPIs, Ablaufwarnungen und Wartungshinweisen
- Kundenverwaltung mit Verträgen, Mengenrabatten und Vertragsverlauf
- Datenträger-Verwaltung: Einlagerung, Fotos, Eingangsprotokoll
- Übergabe-Workflow mit druckfertigem Übergabeprotokoll
- Rechnungsstellung mit Rabattstufen, MwSt., Mahnungsfunktion
- Archiv aller zurückgegebenen Datenträger
- Briefvorlagen-Editor (Rechnung, Übergabe, Eingang, Vertrag)
- Admin-Bereich: Benutzerverwaltung, Rollen & Berechtigungen
- SAML 2.0 / SSO (Azure AD, Okta, Keycloak)
- PBKDF2-Passwortsicherheit, tokenbasierte Sessions, Docker Swarm

---

*© 2025 Marcel Capelan — [capelan.de](https://capelan.de)*
