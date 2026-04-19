# Changelog

## v1.0.0 (2025)

### Erstveröffentlichung

**Kernfunktionen:**
- Kunden-Verwaltung mit Vertragsdaten und kundenspezifischem Mengenrabatt (5 Stufen)
- Datenträger-Einlagerung mit Foto, Seriennummer, Preis und Eingangsprotokoll
- Übergabe-Workflow mit druckfertigem Protokoll
- Rechnungserstellung mit automatischer Anteilsberechnung, Mengenrabatt und allg. Rabatt
- Rechnungshistorie mit Mahnungsfunktion
- DT-Archiv für übergebene Datenträger
- Vertrags-Übersicht mit Ablaufwarnungen
- Dashboard mit Kennzahlen und Umsatzübersicht

**Template-System:**
- Individuelle Briefvorlagen für Rechnung, Übergabe, Eingang und Vertrag
- Logo-Upload und Akzentfarbe
- Echtzeit-Vorschau beim Bearbeiten

**Benutzerverwaltung:**
- Token-basierte Authentifizierung
- Rollenbasierte Berechtigungen (Lesen, Schreiben, Löschen, Templates, Admin)
- Tab-Sichtbarkeit pro Rolle konfigurierbar
- Eigenes Passwort ändern
- SAML 2.0 / SSO-Unterstützung (optional)

**Technisch:**
- Flask 3 + SQLite (WAL) Backend
- Docker-ready, nicht-root Container
- Vollständig offline-fähig (kein CDN, keine externen Abhängigkeiten)
- Dark-Mode-Unterstützung (folgt Systempräferenz)
