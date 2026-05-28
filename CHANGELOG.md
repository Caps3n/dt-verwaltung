# Changelog

All notable changes to DT-Verwaltung are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [v1.8.0] – 2026-05-28

### Added
- **`/api/ping` endpoint** – Unauthenticated liveness probe (`GET /api/ping` → `{"ok":true}`). Dockerfile, docker-compose, and portainer-stack healthchecks migrated to `/api/ping`; the old `/api/health` (which requires auth) no longer causes container restart loops.
- **Automatik-Tab in Admin panel** – New 🤖 sub-tab with toggle switches for: auto invoice reminders (configurable overdue threshold in days), maintenance warnings (configurable lead time in days), and a weekly status digest (configurable recipient, weekday, and hour).
- **Background scheduler** – Daemon thread that wakes hourly: sends overdue-invoice reminders, maintenance warnings (via customer email), and the weekly digest; deduplication via `auto_notif_log` prevents double-sends within the same day/week.
- **Barcode scan → serial number** – 📷 button added next to the serial number field in both the DT create form and the edit overlay. Triggers the camera scanner in barcode mode; BarcodeDetector now includes `code_128`, `code_39`, `ean_13`, `ean_8` in addition to `qr_code`. Scan result is written directly into the field without opening a result panel.
- **`.dockerignore`** – Excludes `.git`, `*.md`, `docker-compose.yml`, `portainer-stack.yml`, `.github/`, and Python build artefacts from the image layer.
- **GitHub Actions build cache + version tags** – Workflow now uses `docker/setup-buildx-action`, `docker/metadata-action` (semver tags `v*.*.*` + `latest`), and `cache-from/to: type=gha` for faster CI rebuilds.
- **`portainer-stack.yml` fixed** – Now pulls from `ghcr.io/caps3n/dt-verwaltung:latest` instead of slow source-build from GitHub URL.
- **DB tables** – `notif_settings` (notification config) and `auto_notif_log` (deduplication log) added via zero-downtime migration in `init_db()`.

### Fixed
- **Docker HEALTHCHECK crash loop** – `HEALTHCHECK CMD` now calls `/api/ping` instead of `/api/health` (which was protected by `@require_auth` since v1.7.29).

## [v1.7.31] – 2026-05-28

### Fixed
- **Revenue chart** (`/api/stats/charts`) – Was grouping by `erstellt` (DB insert timestamp) instead of `dat` (invoice date `DD.MM.YYYY`). Now uses `dat` for correct monthly bucketing.
- **Email plain-text fallback** – `send_mail()` now attaches a `text/plain` part (HTML tags stripped) before the `text/html` part so mail clients that don't render HTML show readable content.

### Changed
- **Input length validation** – `_validate_lengths()` helper added; applied to `create_kunde`, `update_kunde`, `create_dt`, `update_dt`. Returns HTTP 400 if any text field exceeds its limit (e.g. firma: 200, serial: 200, beschreibung: 2000 chars).
- **Session token already in `sessionStorage`** – Confirmed: token storage was already migrated to `sessionStorage` in a prior release. `localStorage` is only used for non-sensitive preferences (language, theme).

## [v1.7.30] – 2026-05-28

### Changed
- **`update_dt` refactored** – Replaced 4 near-identical SQL branches with a single dynamic SQL builder. Blob columns (`bild`, `eingang_doc`) are appended only when present in the payload.
- **`clean_sessions()` rate-limited** – Added `_last_clean` monotonic timestamp; cleanup runs at most once per minute instead of on every login call.
- **SAML temp file leak fixed** – `build_saml_client_from_db()` now tracks all temp files in `_saml_tmp_registry`. On exception during build, created files are cleaned up immediately. On cache clear (settings save, cert regeneration), all tracked files are deleted.
- **Dead `saml_config` table removed** – `CREATE TABLE IF NOT EXISTS saml_config` and its initial insert were removed from `init_db()`; only `saml_settings` is queried.

## [v1.7.29] – 2026-05-28

### Security
- **`session_get()` multi-worker fix** – Session token is now always verified against the database, not only the in-memory dict. Logout on one Gunicorn worker now correctly invalidates the session on all workers.
- **`/api/health` hardened** – Endpoint now requires authentication (`read` permission) and no longer exposes the DB file path.
- **TOTP setup/disable require current password** – `POST /api/me/totp/setup` and `DELETE /api/me/totp` now demand `current_password` in the request body; both return HTTP 403 if the password is wrong.
- **Upload size limit (10 MB)** – New `_check_blob_size()` helper applied to all blob upload paths (DT bild, eingang_doc, Kunden vertrag_doc, Tresor wartungsvertrag_doc). Returns HTTP 413 if payload exceeds 10 MB.

### Fixed
- **DB connection leak in `get_mahnungen`** – Missing `db.close()` added to `GET /api/mahnungen/<rechnung_nr>`.

### Changed
- **Audit logging** – `log_audit()` calls added to all CRUD operations: Kunden (create/update/delete), Datenträger (create/update/delete), Tresore (create/update/delete), Übergaben (create/abschließen/delete), Rechnungen (create/delete). Every write now leaves an audit trail.

## [v1.7.28] – 2026-05-27

### Changed (Mobile UX)
- **DT-Tabelle ≤600px** – Spalten „Kunden-Nr" (`dt-col-kd`) und „Preis" (`dt-col-pr`) ausgeblendet; QR-Button und Eingangs-Button per `dt-btn-qr-mob` / `dt-btn-scan-mob` ausgeblendet → 5-Spalten-Ansicht ohne horizontales Scrollen.
- **Rechnungen-Tabelle ≤600px** – Spalten „Zeitraum" (`re-col-zr`) und „Datum" (`re-col-dat`) ausgeblendet → kompaktere 5-Spalten-Ansicht.
- **Tresore-Tabelle ≤600px** – Spalten „Standort" (`tr-col-loc`) und „Termin" (`tr-col-termin`) ausgeblendet → 4-Spalten-Ansicht.
- **DT Batch-Bar** – `flex-wrap:wrap` + kleinere Buttons auf ≤600px; passt sich umbrechen statt zu überfließen.
- **Template-Tabs** – `overflow-x:auto; flex-wrap:nowrap` auf ≤600px; Tabs scrollen horizontal statt umzubrechen.
- **Template Brief-Vorschau** – `<div class="brief-outer">` Wrapper um alle 4 Previews (Rechnung, Übergabe, Eingang, Vertrag); `.brief{min-width:540px}` bei ≤1024px → Vorschau scrollt horizontal statt zu quetschen.
- **`_thS()`** – Optionaler 5. Parameter `cls` für CSS-Klassen auf sortierbaren `<th>`-Elementen.

## [v1.7.27] – 2026-05-27

### Changed
- **DT-Thumbnail Lazy-Loading** – Vorschaubilder in der Datenträger-Liste werden nicht mehr beim Klick, sondern automatisch per `IntersectionObserver` geladen sobald die Zeile ins Viewport scrollt (rootMargin: 120px). Shimmer-Placeholder während des Ladens.

## [v1.7.26] – 2026-05-26

### Security
- **XSS-Fix `k.ansprechpartner`** – Kontaktnamen wurden an ~10 Stellen in Briefvorlagen und Detail-Kacheln ohne `esc()` in innerHTML eingesetzt. Alle Vorkommen jetzt konsequent mit `esc()` escaped. Die generische `dl()`-Hilfsfunktion escapet den Wert nun immer intern.
- **SAML One-Time-Code (OTC)** – Session-Token wird nicht mehr im URL-Fragment (`#saml_token=`) übergeben. Stattdessen erzeugt der Server einen kurzlebigen (30 s) Single-Use-Code, den das Frontend via `POST /api/saml/exchange` gegen den echten Token tauscht. Token erscheint nie mehr in Browser-History oder Netzwerk-Logs.
- **`document.write()` entfernt** – `loadAndOpenDoc()` nutzte `document.write()` um PDFs in einem Popup zu öffnen. Ersetzt durch sicheren Blob-URL-Ansatz (`URL.createObjectURL`). Kein DOM-Injection-Risiko mehr.
- **Emergency-Reset Rate-Limit** – `/api/emergency-pw-reset` hat jetzt `@_rate_limit("5 per hour")` und erzwingt Mindestlänge 8 Zeichen für das neue Passwort.
- **SMTP-Passwort verschlüsselt** – Passwort wird mit Fernet (AES-128-CBC) verschlüsselt in der DB gespeichert. Schlüssel auto-generiert in `/data/smtp.key` (600-Rechte). Bestehende Plaintext-Passwörter funktionieren weiterhin (automatische Erkennung am fehlenden `enc:`-Prefix). GET-Endpunkt gibt das Passwort weiterhin nicht zurück.
- **CORS-Warnung** – Startup-Log-Warning wenn `ALLOWED_ORIGIN=*` (Default). Produktiv `ALLOWED_ORIGIN=https://dein-domain.de` setzen.
- **flask-limiter Warnung verstärkt** – Wenn nicht installiert, erscheint jetzt `CRITICAL` im Log (vorher nur Hinweis).

## [v1.7.25] – 2026-05-26

### Fixed
- **Footer-Versionsnummer** – Die dynamisch via JS gerenderte Fußleiste (`updateSupportDisplay()`) zeigte noch `v1.7.21` statt der aktuellen Version. Beide Footer-Stellen (statisches HTML + JS-Render) zeigen nun korrekt `v1.7.25`.
- **KPI-Raster Mobile – Item 3 fehlender Trennstrich** – Bei 2-Spalten-Layout (≤600px) hatte Item 3 keinen rechten Rand, weil die 900px-Regel `border-right:none` setzte. Bei 2 Spalten ist Item 3 aber links in Zeile 2 und braucht seinen rechten Rand. Expliziter Reset ergänzt.
- **KPI-Wert Overflow** – `min-width:0` auf `.db-kpi` und `max-width:100%` auf `.db-kpi-val` für sauberes `text-overflow:ellipsis` bei langen Beträgen.
- **Quick-Action Buttons Mobile** – Text-Overflow für Button-Labels, Padding und Gap leicht komprimiert für bessere Darstellung auf schmalen Screens.
- **Chart-Höhen Mobile** – Revenue/Vault-Chart 130px statt 140px, Donut 150px/130px für bessere Proportionen auf 375px-Screens.

## [v1.7.24] – 2026-05-26

### Fixed
- **Dashboard Mobile-Layout** – KPI-Strip, Quick-Actions, Charts und Section-Cards optimiert für Bildschirme ≤ 600px:
  - KPI-Werte auf `font-size:17px` + `text-overflow:ellipsis` (kein Überlauf bei langen Beträgen)
  - KPI-Label auf `9px`, KPI-Padding kompakter (`11px 12px`)
  - `.db-section` Innen-Padding auf Mobile auf `12px 13px` reduziert
  - Quick-Action Buttons bleiben auch auf Mobile 2×2 (nicht 4×1) für bessere Nutzung des Platzes
  - Revenue- und Vault-Chart-Container: Höhe auf Mobile `140px` statt `180–200px`
  - Donut-Chart-Canvas auf Mobile auf `max 120×120px` begrenzt (war 160×160px, sah auf Vollbreite winzig und einsam aus)

## [v1.7.22] – 2026-05-26

### Added
- **Zeichnungsberechtigter (Signatur-Feld)** – Admin → Unternehmen enthält jetzt ein eigenes Feld „Zeichnungsberechtigter" (z.B. „Max Mustermann, Geschäftsführer"), das in allen Unterschriftszeilen der Dokumente (Übergabe, Eingang, Rechnungen) als Signatur der verwaltenden Gesellschaft erscheint. Vorher musste dieses Feld umständlich über den Template-Editor gesetzt werden.
- **Support-Kontakt in Unternehmen-Panel verschoben** – Der Support-Kontakt (Hilfe-Tab + Footer) ist jetzt direkt im Unternehmen-Panel sichtbar, klar getrennt vom „Bearbeiter" (Briefkopf-Kontakt) mit Hinweis, dass es sich um unterschiedliche Personen handelt.

### Fixed
- `sig`-Feld wird nun korrekt über alle Admin-Speichervorgänge persistiert (war vorher nur im Template-Editor zugänglich)

## [v1.7.21] – 2026-05-26

### Added
- **Chart.js Dashboard-Diagramme** – Das Dashboard zeigt nun drei interaktive Diagramme: Umsatz-Balkendiagramm (letzte 12 Monate via `/api/stats/charts`), DT-Status-Donut-Chart (Eingelagert/Übergeben) und Tresor-Auslastungs-Balkendiagramm (horizontal, Top-8-Tresore).
- **DT-Overlay: Foto-Tab** – Im „Datenträger bearbeiten"-Dialog gibt es jetzt 4 Tabs: Stammdaten, Foto, Notizen, Wartung. Im Foto-Tab kann ein Hochauflösungsfoto (max. 5 MB) hochgeladen, angezeigt und gelöscht werden (separates DB-Feld `foto_data`/`foto_type`).
- **DT-Overlay: Notizen-Tab** – Freitext-Notizen pro Datenträger: Liste aller Einträge (Autor, Timestamp) + Eingabefeld zum Hinzufügen und Löschen. Gespeichert in `dt_notizen`-Tabelle.
- **DT-Overlay: Wartungshistorie-Tab** – Chronologische Wartungseinträge mit Datum, Beschreibung und Techniker. Einträge können hinzugefügt und gelöscht werden (Tabelle `dt_wartungen`).
- **Batch-Auswahl in der DT-Liste** – Checkboxen in jeder Zeile + „Alle"-Checkbox im Tabellenkopf. Floating-Aktionsleiste beim Auswählen: Sammelaktion „Als eingelagert markieren" und „Auswahl löschen". Auswahl bleibt beim Seitenwechsel (Set-basiert) erhalten.
- **PWA / Progressive Web App** – `manifest.json` und `sw.js` (Service Worker) aktiviert. Die App kann jetzt auf iOS/Android zum Homescreen hinzugefügt werden. Der Service Worker cached statische Assets und ermöglicht Offline-Zugriff auf die Oberfläche.
- **Browser-Benachrichtigungen** – Nach dem Login wird einmalig die Notification-Permission angefragt. Bei genehmigter Erlaubnis erscheinen Push-Benachrichtigungen für bevorstehende Vertragsabläufe (max. 2 pro Session).
- **Swipe-Navigation (Mobile)** – Horizontale Touch-Swipe-Gesten wechseln zwischen den App-Tabs (60px+ Mindesthub, kein versehentliches Auslösen in Overlays oder beim vertikalen Scrollen).
- **Audit-Log CSV-Export** – Neuer Button „📋 Audit-Log als CSV" im Admin-Bereich → Datenbank-Bereich. Lädt alle Audit-Log-Einträge mit BOM-Zeichen (Excel-kompatibel) herunter.
- **Globale Suche: Archiv-DTs** – Die globale Suche findet jetzt auch bereits übergebene (archivierte) Datenträger. Archivierte Einträge sind als „(archiviert)" gekennzeichnet und navigieren automatisch in den Alle-Filter.

### Backend (bereits in v1.7.21-pre)
- **Neue DB-Spalten**: `foto_data BLOB`, `foto_type TEXT` auf `datentraeger` (Auto-Migration)
- **Neue DB-Tabellen**: `dt_notizen`, `dt_wartungen` (Auto-Migration)
- **Neue API-Endpunkte**: `GET/POST/DELETE /api/datentraeger/<id>/foto`, `GET/POST /api/datentraeger/<id>/notizen`, `DELETE /api/datentraeger/<id>/notizen/<nid>`, `GET/POST /api/datentraeger/<id>/wartungen`, `DELETE /api/datentraeger/<id>/wartungen/<wid>`, `GET /api/stats/charts` (120s TTL-Cache), `GET /api/admin/backup`, `GET /api/audit_log_csv`

---

## [v1.7.20] – 2026-05-25

### Added
- **QR-Scanner in der Suchleiste** – Kleines 📷-Icon rechts im globalen Suchfeld. Klick startet die Kamera, scannt den QR-Code und navigiert direkt zum Datenträger: Tab wechselt automatisch, Zeile wird hervorgehoben, Suchfeld wird mit der internen Nummer/Seriennummer befüllt.

### Fixed
- **BarcodeDetector.detect(vid → cvs)** – `BarcodeDetector.detect()` akzeptiert kein Video-Element, nur Canvas/ImageBitmap. Der Scanner übergab `vid` statt `cvs` → QR-Erkennung schlug immer fehl, jsQR-Fallback wurde nie korrekt getriggert.
- **showTab('dt') → showTab('datentraeger')** – Deep-Link-Handler und Scanner-Navigation riefen `showTab('dt')` auf, aber der Tab hat `data-tab="datentraeger"`. Die Navigation zum DT-Tab funktionierte gar nicht (stiller Fehler).
- **showTab(t, e) Parameter-Shadowing** – Der Parameter `t` überschrieb die globale `t()`-Übersetzungsfunktion. Dadurch warf `alert(t('msg_no_perm'))` einen TypeError statt die Meldung anzuzeigen. Parameter umbenannt zu `tab`.
- **`_origShowTab` undefined** – Toter Code-Stub wurde 3000 Zeilen vor der eigentlichen `showTab()`-Definition zugewiesen und war immer `undefined`. Entfernt.

---

## [v1.7.19] – 2026-05-25

### Changed
- **Hamburger-Menü Breakpoint: 640px → 1024px** – Das Hamburger-Menü greift jetzt auch auf Tablets und kleinen Laptops (bis 1024px Breite). Die horizontale Tab-Leiste mit 9 Einträgen war auf diesen Geräten zu eng.

---

## [v1.7.18] – 2026-05-25

### Added
- **Hamburger-Menü auf Mobilgeräten** – Ab Bildschirmbreite ≤640px wird die horizontale Tab-Leiste ausgeblendet und durch ein ☰-Symbol in der Topbar ersetzt. Klick öffnet ein animiertes Seitenmenü (Slide-in von links) mit allen Tabs, Benutzername, Rolle und Schnellzugriffen (Passwort, Sprache, Hell/Dunkel, Abmelden). Der aktive Tab wird farblich hervorgehoben. Schließen: Klick auf ✕, Tippen auf den abgedunkelten Hintergrund oder Wechsel zum Tab.
- **Mobile Layout-Anpassungen** – Auf Mobilgeräten: Grid-Layouts (2-, 3-, 4-spaltig) werden auf 1 Spalte reduziert, App-Padding verkleinert, Benutzername/Rolle in der Topbar ausgeblendet (erscheinen im Seitenmenü).

---

## [v1.7.17] – 2026-05-25

### Added
- **QR-Code als Deep-Link URL** – Der QR-Code eines Datenträgers kodiert jetzt eine direkte URL (`https://dtv.capelan.de/#dt=<id>`) statt nur des Beschriftungstexts. Wer den Code mit seinem Smartphone scannt, öffnet die App direkt bei dem betreffenden Datenträger. Zusätzlich: „🔗 Link kopieren"-Button im QR-Overlay sowie größeres QR-Bild (200×200).
- **In-App Kamera-Scanner** – Neuer „📷 Scannen"-Button im Datenträger-Panel. Öffnet ein Scanner-Modal mit Live-Kamerabild (bevorzugt Rückkamera). Nutzt `BarcodeDetector`-API (Chrome/Android) mit automatischem `jsQR`-Fallback für andere Browser. Erkennt sowohl Deep-Link-URLs (`#dt=<id>`) als auch ältere QR-Codes mit reiner Seriennummer/internen Nummer.
- **Mobile-optimiertes Scan-Ergebnis** – Nach erfolgreichem Scan zeigt ein strukturiertes Ergebnis-Panel: Bezeichnung, Interne Nr., Seriennummer, Kunde, Status-Badge. Über „🔍 In Liste anzeigen" wird direkt zum Datenträger navigiert, der Tab wechselt automatisch und die Zeile wird optisch hervorgehoben (Puls-Animation).
- **Deep-Link-Handler** – Beim App-Start wird der URL-Hash auf `#dt=<id>` geprüft. Nach dem Login navigiert die App automatisch zum entsprechenden Datenträger (Tab-Wechsel + Scroll + Highlight). Nützlich für per E-Mail oder Chat geteilte QR-Links.
- **jsQR Bibliothek** – `jsQR 1.4.0` via cdnjs als universeller QR-Decoder in Browser-Umgebungen ohne `BarcodeDetector`-Support.
- **`data-dtid` Attribut in DT-Tabellenzeilen** – Ermöglicht direktes Anspringen einer Zeile per JavaScript nach Scan oder Deep-Link.

---

## [v1.7.16] – 2026-05-25

### Fixed
- **DT-Liste: Übergeben-Items im Erfassen-Panel** – Datenträger mit Status `uebergeben` erschienen im „Eingelagerte Datenträger"-Panel, wenn „Alle" gewählt war. Die Liste filtert jetzt systematisch alle `uebergeben`-Einträge heraus – diese gehören ausschließlich ins Archiv-Tab. Der „📦 Übergeben"-Filter-Button wurde entfernt. Standard-Filter ist jetzt „Eingelagert".
- **Version-String im Footer** – Footer zeigte `v1.7.14` statt `v1.7.15` (zwei Stellen: statisches HTML + JS-generierter Footer).

### Security
- **E-Mail-Header-Injection** – `_send_email()` sanitisiert jetzt `to_addr` und `subject` (Zeilenumbrüche werden entfernt). Zusätzlich: Basis-Format-Validierung der E-Mail-Adresse (muss `@` enthalten, keine Leerzeichen).
- **Integer-Input-Safety** – `GET /api/audit_log?limit=&offset=` warf bisher einen unbehandelten `ValueError` → HTTP 500. Jetzt try/catch → HTTP 400 mit klarer Fehlermeldung.
- **SMTP-Port-Validierung** – `PUT /api/smtp_settings` validiert jetzt den Port-Wert (Integer, 1–65535). Ungültige Werte liefern HTTP 400.
- **Rate-Limit auf `/api/auth/refresh`** – Der Session-Verlängerungs-Endpunkt hatte bisher kein Rate-Limit. Jetzt: max. 20 Anfragen/Minute (via `flask-limiter`).

---

## [v1.7.15] – 2026-05-25

### Added
- **Rechnung per E-Mail senden** – Jede Rechnung in der Rechnungshistorie hat jetzt einen 📧-Button. Klick öffnet ein Modal mit vorausgefülltem Empfänger (aus Kundenstammdaten) und Betreff. Sendet die gespeicherte Rechnungs-HTML per SMTP. Neuer Backend-Endpunkt `POST /api/rechnungen/<id>/email`. Audit-Log-Eintrag `EMAIL_RECHNUNG` wird geschrieben.
- **Session-Timeout Warnung** – Ein gelbes Banner am Bildschirmrand erscheint automatisch, wenn die Sitzung in weniger als 10 Minuten abläuft (z. B. „Deine Sitzung läuft in 7 Minuten ab."). Über den Button „Sitzung verlängern" kann die Sitzung um weitere 8 Stunden verlängert werden (`POST /api/auth/refresh`). Die Ablaufzeit wird beim Login in `sessionStorage` gespeichert und alle 30 Sekunden geprüft.

---

## [v1.7.14] – 2026-05-25

### Fixed
- **3-Parteien-Vertrag: Fehlende Felder ergänzt** – Das Escrow-Formular hatte bisher deutlich weniger Felder als der 2-Parteien-Vertrag. Hinzugefügt: `Vertragsbeginn`, `Vertragsende (optional)`, `Laufzeit / Verlängerung`, `Kündigungsfrist`.
- **§ 2 Vertragslaufzeit im Escrow-Dokument** – Der gedruckte Escrow-Vertrag enthält jetzt einen eigenen `§ 2 Vertragslaufzeit`-Abschnitt mit Beginn, Ende, Laufzeit und Kündigungsfrist. Die bisherigen §§ 2–4 wurden zu §§ 3–5 verschoben.
- **Paragraphen-Nummerierung** – Freigabebedingungen: § 2 → § 3, Vergütung: § 3 → § 4, Haftung: § 4 → § 5.

---

## [v1.7.13] – 2026-05-25

### Changed
- **Dashboard-Redesign v2 (Typography-first)** – Zweite Iteration, nochmals minimaler:
  - **KPI-Strip** – Eigene `.db-kpis`-Klasse, 28 px fette Zahlen mit negativem Letter-Spacing, Hover-State pro KPI-Zelle. Responsive: 3-spaltig bei < 900 px, 2-spaltig bei < 600 px mit automatischen Top-Borders.
  - **Quick Actions** – Jetzt als kompakte horizontale Flex-Reihe (nicht mehr 4-Spalten-Grid). Icon + Text inline, flacher Look mit subtilen Borders, Lift-Effekt beim Hover (`translateY(-1px)`).
  - **Section-Header** – Neue `.db-sh-lbl`-Klasse: 10 px, uppercase, letter-spaced, mutedfarbe — cleaner als fette Titel. Emoji aus Überschriften entfernt.
  - **Kein Inline-Style mehr** im Dashboard-HTML — alles über dedizierte CSS-Klassen (`db-kpis`, `db-actions`, `db-grid2`, `db-section`, `db-sh`, `db-sh-lbl`).

---

## [v1.7.12] – 2026-05-25

### Changed
- **Dashboard-Redesign (modern & minimalist)** – Komplett überarbeitetes Dashboard-Layout:
  - **KPI-Strip** – Alle 6 KPIs (Eingelagerte DT, Kunden, Netto/Jahr, Aktive Verträge, Ablauf <60 Tage, Offene Rechnungen) jetzt in einem einzigen horizontalen Band mit vertikalen Trennlinien statt einzelner Karten.
  - **Quick Actions** – 4 Aktions-Buttons in sauberem 4-Spalten-Grid (Emoji + Text gestapelt), klares Hover-Feedback in Akzentfarbe.
  - **Logische Inhaltsblöcke** – Zwei 2-Spalten-Zeilen (Termine + Chart | Ablauf + Umsatz), gefolgt von Aktive Verträge (volle Breite), Wartungen (2-spaltig) und DT nach Typ (volle Breite).
  - **Section-Header** – Einheitliche `.db-sh` Klasse: Titel linksbündig, Badge rechtsbündig, klare Trennung vom Inhalt.
  - Responsive: KPI-Strip bricht bei <600 px auf 3×2 um, Quick Actions auf 2×2.

---

## [v1.7.11] – 2026-05-25

### Security
- **Rate-Limiting auf Login** – `/api/login` akzeptiert maximal 10 Versuche/Minute und 30/Stunde pro IP (`flask-limiter`). Bei Überschreitung: HTTP 429.
- **XSS-Schutz: `esc()` Helper** – Neue `esc()`-Funktion im Frontend escaped alle User-kontrollierten Felder (131 Stellen: `firma`, `bezeichnung`, `serial`, `name`, `username`, `nr`, `email`, `tel`, `vertragsnr`, u.a.) in `innerHTML`-Template-Literalen. Verhindert Stored-XSS-Angriffe.
- **HTTP Security-Headers** – Server sendet jetzt bei jeder Response: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy` und `Content-Security-Policy`.
- **Passwort-Mindestlänge** – Von 4 auf 8 Zeichen erhöht.
- **CORS konfigurierbar** – Erlaubter Origin kann per `ALLOWED_ORIGIN` Umgebungsvariable eingeschränkt werden (Standard: `*` für Rückwärtskompatibilität).

---

## [v1.7.10] – 2026-05-25

### Added
- **Tresore: Zwei separate Terminfelder** – Das Formular unterscheidet jetzt zwischen „Wartung fällig am" (`naechster_wartungstermin`, Fälligkeit laut Wartungsvertrag) und „Vereinbarter Termin (Wartungsfirma)" (`termin_wartungsfirma`, konkreter Termin mit der externen Wartungsfirma). Beide Felder sind unabhängig voneinander setzbar.
- **Tresore: Wartungs-Historie** – Neue Tabelle `tresor_wartungen` speichert alle abgeschlossenen Wartungseinsätze je Tresor (Datum, Notizen, optional PDF-Wartungsprotokoll). Beim Erfassen eines neuen Eintrags wird `letzter_wartungstermin` automatisch aktualisiert. Einträge können gelöscht und Protokolle als PDF heruntergeladen werden.
- **Tresor-Liste: Termin-Spalte** – Die Tresore-Tabelle zeigt jetzt zusätzlich zur Fälligkeitsspalte eine eigene „📅 Termin"-Spalte mit dem vereinbarten Wartungstermin (blauer Badge).
- **Anstehende Termine: Tresor-Termine** – Das Dashboard-Widget „Anstehende Termine" verwendet jetzt `termin_wartungsfirma` (explizit vereinbarter Termin) statt der allgemeinen Fälligkeitsdate — keine Phantom-Einträge mehr wenn nur eine Fälligkeit, aber kein konkreter Termin gesetzt ist.

### Changed
- **Tresor-Detailansicht** – Vollständig überarbeitet: zeigt beide Datumsfelder farblich kodiert (rot = überfällig, amber = bald, grün = OK), gefolgt von der Wartungs-Historie als sortierte Tabelle mit Inline-Formular zum Erfassen neuer Einträge und PDF-Upload.

---

## [v1.7.03] – 2026-05-24

### Changed
- **Tresor-Liste: Wartungsdatum Farbgebung** – Spalte „Nächste Wartung" im Tresore-Tab zeigt jetzt drei Zustände: grün (weit in der Zukunft), gelb/amber (innerhalb 60 Tage, Termin anstehend) und rot mit Tagesangabe (Termin überfällig/überzogen). Vorher wurde alles ≤60 Tage pauschal rot markiert.
- **Dashboard Tresor-Wartungstermine-Karte** – Überfällige Zeilen werden mit rotem Zeilenhintergrund und ⚠-Symbol hervorgehoben; anstehende (noch nicht überfällige) Termine bleiben gelb.

---

## [v1.7.02] – 2026-05-24

### Changed
- **Termin-Widget: Klare Trennung Termin vs. Überfällig** – Das „Anstehende Termine" Widget auf dem Dashboard unterscheidet jetzt sauber zwischen vereinbarten Terminen (gelber Rand, Countdown in Tagen) und überfälligen Terminen (roter Hintergrund, Abschnitt „🔴 Überfällig", Anzeige der Überschreitung in Tagen). Der Badge-Zähler wird bei überfälligen Einträgen selbst rot. Termine die noch in der Zukunft liegen erscheinen im Abschnitt „📅 Vereinbarte Termine".

---

## [v1.7.01] – 2026-05-24

### Fixed
- **Termin-Widget: Falsche Einträge** – Das "Anstehende Termine" Widget auf dem Dashboard zeigte fälschlicherweise offene Rechnungen (>30 Tage) als "Termine" an, obwohl keine Wartungs- oder Vertragstermine eingetragen waren. Rechnungen werden im Widget nicht mehr angezeigt — es zeigt nur noch explizit gesetzte Termine (Tresor-Wartungsdaten, Vertragsabläufe).

---

## [v1.7.0] – 2026-05-24

### Fixed
- **Übergabe: Umlaut-Bug** – Bestehende DB-Einträge mit "Rueckgabe auf Wunsch" werden per Migration auf "Rückgabe auf Wunsch" korrigiert. Select-Optionen erhalten explizite `value`-Attribute für korrekte zukünftige Speicherung.
- **Übergabe: Duplikate** – Frontend-Guard (`_weiterS2Running`-Flag + Button-Disable) verhindert Doppelklicks. Backend prüft zusätzlich ob eine identische offene Übergabe (gleiche Kunden-ID, gleiches Datum, gleiche DT-Liste) bereits existiert und gibt die bestehende zurück statt eine neue anzulegen. Task #27 damit geschlossen.

### Added
- **Dashboard Schnellzugriff** – Vier Buttons direkt auf dem Dashboard: "Neuer Datenträger", "Rechnung erstellen", "Übergabe starten", "Neuer Kunde". Navigieren mit einem Klick in den jeweiligen Tab.
- **Dashboard Termin-Widget** – Neues Widget "Anstehende Termine" zeigt alle fälligen Events der nächsten 60 Tage: Tresor-Wartungen, ablaufende Verträge und überfällige Rechnungen. Farblich nach Dringlichkeit (rot = überfällig, gelb = bald fällig).
- **Spalten-Sortierung** – Alle wichtigen Tabellen (Kundenliste, Datenträgerliste, Rechnungshistorie) sind durch Klick auf Spalten-Header sortierbar (▲/▼). Sortier-Zustand wird im Speicher gehalten.
- **Tresore: DT-Anzahl anklickbar** – Die DT-Zahl in der Tresore-Liste öffnet ein Modal mit allen eingelagerten Datenträgern des Tresors (Bezeichnung, Seriennummer, Firma, Status).
- **Hell-/Dunkel-Modus Umschalter** – 🌙/☀️-Button in der Navbar. Wechselt manuell zwischen Light und Dark Mode. Einstellung wird in localStorage gespeichert und bei jedem Seitenaufruf angewendet.
- **Pflichtfelder markiert** – Labels der Pflichtfelder in allen Formularen (Kunden, Datenträger, Übergabe, Tresor) erhalten ein rotes `*` über CSS-Klasse `.req`.

### Changed
- **Design: Aktiver Tab** – Aktiver Hauptnavigations-Tab hat jetzt einen blauen Hintergrund (`var(--i-bg)`) statt nur eines Unterstrichs — deutlich besser erkennbar.
- **Design: Admin-Logo-Background** – Logo-Upload-Zonen erhalten Klasse `.logo-zone`; `has-file`-State zeigt neutralen Hintergrund statt grünem Success-State.

---

## [v1.6.04] – 2026-05-24

### Fixed
- **Dashboard leer / Admin-Tabs reagieren nicht**: JavaScript-Hoisting-Bug in den Hook-Funktionen `renderDashboard` und `showAdminSub`. Beide waren mit `function`-Deklarationen implementiert — diese werden vom JS-Engine an den Anfang des Skripts gezogen (hoisted), weshalb `_origRenderDashboard` und `_origShowAdminSub` jeweils auf sich selbst zeigten → `RangeError: Maximum call stack size exceeded` → Dashboard-Crash + Admin-Navigation kaputt. Alle drei Hooks (`renderDashboard`, `showAdminSub`, `doLogin`) auf IIFE-Pattern umgestellt (`window.X = function(){...}` innerhalb einer IIFE), das zur Laufzeit ausgeführt wird und kein Hoisting-Problem hat.

---

## [v1.6.03] – 2026-05-23

### Fixed
- **Login "Verbindungsfehler"**: the 2FA login override called `_saveLogin()` which was never defined — replaced with the correct inline success path (`TOKEN`, `currentUser`, `sessionStorage`, `showApp()`). Login now completes correctly after the server returns a valid token.

---

## [v1.6.02] – 2026-05-23

### Fixed
- **Login crash**: `pysqlcipher3.dbapi2.Row` has no `.get()` method — converted the login query result to a plain `dict` before TOTP checks, so `user.get('totp_enabled')` and `user.get('totp_secret')` work correctly regardless of the SQLite driver in use.

---

## [v1.6.01] – 2026-05-23

### Fixed
- **Startup crash**: duplicate `GET /api/me` endpoint definition caused Flask to raise `AssertionError: View function mapping is overwriting an existing endpoint function: get_me` on boot. Merged `totp_enabled` field into the existing SAML-compatible endpoint and removed the redundant second definition added in v1.6.0.

---

## [1.6.0] – 2026-05-23

### Added
- **E-Mail-Versand (SMTP)**: SMTP-Konfiguration im Admin-Tab; Mahnungen können per 📧-Button direkt per E-Mail gesendet werden
- **Audit-Log**: neue DB-Tabelle `audit_log` protokolliert alle Änderungen (Benutzer, Aktion, Tabelle, Datensatz-ID); eigener Admin-Tab mit Suche und Pagination
- **Globale Suche**: Suchleiste in der Top-Navigation durchsucht Kunden, Datenträger und Rechnungen gleichzeitig
- **QR-Code je Datenträger**: QR-Button in der DT-Tabelle öffnet einen druckbaren QR-Code-Overlay (qrcode.js)
- **Status-Filter im DT-Tab**: Filterschaltflächen „Alle / ✅ Eingelagert / 📦 Übergeben"
- **Umsatz-Chart im Dashboard**: monatliches Umsatz-Balkendiagramm (SVG, letzte 12 Monate) via neuem API-Endpoint `/api/dashboard/umsatz_monat`
- **Datenträger-Wartungsintervall**: neue Felder `wartungsintervall_jahre` und `letzter_check_datum`; Dashboard-Widget zeigt fällige Wartungen
- **2FA / TOTP für lokale Benutzer**: Setup, Aktivierung und Deaktivierung im Passwort-Modal; Login prüft TOTP-Code wenn aktiviert
- **Pagination** in der DT-Liste: 25 Einträge pro Seite mit Blätter-Navigation
- **📧 E-Mail-Button in der Mahnungs-Historie**: direkte E-Mail-Zustellung aus der aufgeklappten Mahnungsliste
- DB-Migrationen: neue Spalten `totp_secret`, `totp_enabled` in `benutzer`; neue Tabellen `audit_log`, `smtp_settings`
- pyotp zur Dockerfile-Abhängigkeit hinzugefügt

### Changed
- DT-Bearbeiten-Overlay: Wartungsintervall-Felder hinzugefügt
- DT-Hinzufügen: übergibt `wartungsintervall_jahre` und `letzter_check_datum` an die API

---

## [1.5.1] – 2026-05-23

### Added
- **Zahlungsstatus** auf Rechnungen: Badge zeigt Offen / Bezahlt / Überfällig (>30 Tage)
- **„✓ Bezahlt"-Button** in der Rechnungshistorie — Klick setzt `bezahlt_am` Datum; ↩-Button macht es rückgängig
- **DB-Migration**: neue Spalte `bezahlt_am TEXT` in Tabelle `rechnungen`
- **API**: `PATCH /api/rechnungen/<id>/bezahlt` und `PATCH /api/rechnungen/<id>/unbezahlt`
- **Dashboard-Widget** „Offene Rechnungen" mit Anzahl und Gesamtsumme; Klick springt zur Historie
- Mahnungs-Button deaktiviert wenn Rechnung bereits als bezahlt markiert
- **Server-seitiger TTL-Cache** (30 s) für `GET /api/kunden` und `GET /api/rechnungen` — reduziert DB-Last bei mehreren gleichzeitigen Nutzern
- Cache-Invalidierung bei jedem Schreib-/Löschvorgang auf kunden und rechnungen

### Changed
- `GET /api/rechnungen` liefert jetzt `bezahlt_am` Feld mit
- Beim Upsert einer Rechnung (selbe RE-Nr.) bleibt `bezahlt_am` erhalten

---

## [1.5.0] – 2026-05-15

### Added
- Kundenformular: neue Felder „Max. Mahnungen" und „Mahngebühr (€)" — pro Kunde konfigurierbar je nach Vertragsverhandlung
- DB-Migration: neue Spalten `max_mahnungen` (Default 3) und `mahngebuehr` (Default 5.00) in Tabelle `kunden`
- Mahnungslogik: Mahnung-Button zeigt nächste Stufe an (1. Mahnung / 2. Mahnung / Letzte Mahnung)
- Mahnungslogik: Button wird deaktiviert wenn die max. Anzahl für diesen Kunden erreicht ist
- Archiv: Mahnungsanzeige zeigt jetzt „X/Y" (aktuell/max) statt nur der Anzahl
- Mahnung-Dokument: Betreff lautet „Letzte Mahnung" bei der finalen Mahnstufe

### Changed
- Mahngebühr kommt jetzt aus dem Kundendatensatz statt fest auf 5,00 € codiert

---

## [1.4.9] – 2026-05-02

### Added
- Rechnungshistorie & Mahnungen jetzt server-seitig (SQLite): neue Tabellen `rechnungen` + `mahnungen`
- API-Endpoints: `GET/POST/DELETE /api/rechnungen`, `GET/POST/DELETE /api/mahnungen`, `GET /api/re_nr`, `GET /api/mahnungen_by_id/<id>`
- Rechnungsnummer (`RE-JJJJ-NNN`) wird aus der Datenbank ermittelt – kein Browser-localStorage mehr nötig

### Changed
- Frontend: `rechnungSpeichern`, `renderRechnungHistoriePage`, `rechnungLoeschen`, `rechnungMahnung`, `toggleMahnungenRow`, `nextReNr`, `rechnungExportieren` auf async/await + Backend-API umgestellt
- Alle localStorage-Zugriffe auf `dtv_re_hist`, `dtv_re_nr`, `dtv_mahnungen_*` wurden entfernt
- Rechnungshistorie ist jetzt browserübergreifend und überlebt Container-Neustarts

### Fixed
- Rechnungen wurden im Archiv nicht angezeigt wenn man den Browser wechselte (localStorage war browser-spezifisch)

---

## [1.4.8] – 2026-04-27

### Added
- Templates-Tab: 3-Parteien-Escrow-Vertrag Template-Editor mit Typ-Dropdown (§1–§4 editierbar, DE+EN)
- genVertragEscrowHtml: Verwendet jetzt TV.escrowPar1–4 / TV.escrowPar1_en–4_en aus Vertrag-Templates
- tplVTypChange() JS-Funktion zum Umschalten zwischen 2P- und 3P-Template-Panels

### Changed
- genVertragHtml §3: Datenträger-Tabelle entfernt – §3 zeigt immer „separate Anlage"-Platzhalter
- applyLang: Rebuild tpl-v-typ-select bei Sprachwechsel

## [1.4.7] – 2026-04-27

### Changed
- Contracts tab (Kunden → Verträge): merged 2-party and 3-party escrow contract forms into a single unified card with a type-selector dropdown — cleaner layout, one place for all contracts
- Contract preview backgrounds are now always white (`background:#fff; color:#000`), independent of the app's dark/light theme
- `vtTypChange()` JS function toggles between `vt-panel-2p` and `vt-panel-3p` panels on dropdown change
- `applyLang()` now rebuilds `vt-typ-select` options on language switch (DE/EN)
- Added TRANS keys: `lbl_vt_typ_2p` (2-Party Storage Contract), `lbl_vt_typ_3p` (3-Party Escrow Contract)

---

## [1.4.6] – 2026-04-27

### Added
- **Escrow-Vertragsvorlage (3 Parteien)** — new contract template form in the Verträge sub-tab: select Auftraggeber (Party 2), Haupt-Eigentümer (Party 3), optional Neben-Eigentümer (Party 3b), enter contract number and release conditions, live preview + print. Generates a bilingual 4-§ escrow contract with letterhead, party table, and signature blocks for all three parties. New function `genVertragEscrowHtml()` + `vtEscrowVorschauUpdate()` + `vtEscrowDrucken()`
- **Szenario B text corrected**: "3 Firmen" → "2 Firmen" (the two customer-side companies in the escrow: depositor + beneficiary)
- 36 new TRANS keys covering all newly translated strings

### Fixed
- **100 % DE/EN coverage — Tresor form**: all 15 labels and buttons in the safe/cabinet registration form (Bezeichnung/Name, Hersteller, Modell, Seriennummer, Kaufdatum, Kaufpreis, Letzter Wartungstermin, Standort, Stadt, Etage, Raum, Notizen, PDF hochladen, Abbrechen, Speichern) now carry `data-i18n`
- **Dashboard**: "🔒 Tresor-Wartungstermine" heading and "Keine anstehenden Wartungstermine" empty state now translated
- **Invoice template preview**: "Rechnung" heading + table column headers (Bezeichnung, Preis, Rabatt, Betrag) now `data-i18n`
- **Rechnung button**: "Drucken & Speichern" now uses `data-i18n="lbl_drucken_speichern"` (key already existed, attribute was missing)
- **Eingangsprotokoll preview**: "Protokoll-Nr.:", "Bezeichnung / Typ" row, "Unterschrift Kunde", "Unterschrift Bearbeiter" now `data-i18n`
- **Contract preview**: "Auftraggeber" placeholder now `data-i18n`
- **Admin tab**: "👤 Benutzer & Rollen" now `data-i18n`

---

## [1.4.5] – 2026-04-26

### Fixed
- **100 % DE/EN coverage — complete** — all remaining German strings found in final live verification are now translated:
  - Mengenrabatt info text + table headers ("Ab (Stück)", "Rabatt (%)", "Bezeichnung") now carry `data-i18n` using existing TRANS keys
  - Templates: "Fußzeile, Bankdaten und Steuerinformationen werden im Admin-Bereich verwaltet." → `lbl_tpl_fuss_info`
  - Templates: "Logo und Firmendaten werden vom Rechnungs-Template übernommen." (Übergabe + Eingang templates) → `lbl_tpl_logo_info` (also fixes typo "uebernommen")
  - Templates: "Logo und Firmendaten … Die §-Texte sind Vorlagen …" (Vertrag template) → `lbl_tpl_logo_info_v`
  - Template preview headings: "Übergabeprotokoll" and "Eingangsprotokoll – Datenträger-Einlagerung" → `data-i18n`
  - Contract preview: "§ 2 Vertragslaufzeit", "Kündigungsfrist", "§ 3 Eingelagerte Datenträger", "Liste wird beim Drucken aus den Kundendaten befüllt" → `data-i18n` spans
  - Signature labels in static contract preview: "Ort, Datum", "Unterschrift Lagerbetreiber", "Unterschrift Auftraggeber" → `data-i18n`
- **`genVertragHtml()` JS fully translated** — all §-headings (§ 1–§ 7), Laufzeit/Kündigungsfrist labels, DT table column headers, empty DT fallback text, and signature labels now use `_lang==='en'?...:...` ternaries
- 14 new TRANS keys added: `lbl_mg_info`, `lbl_tpl_fuss_info`, `lbl_tpl_logo_info`, `lbl_tpl_logo_info_v`, `lbl_ue_heading`, `lbl_ep_heading`, `lbl_vt_par2_heading`, `lbl_vt_par3_heading`, `lbl_vt_dt_info`, `lbl_ort_datum`, `lbl_sig_lager`, `lbl_sig_ag`, `lbl_vt_laufzeit_info`, `lbl_vt_kfrist_info`

---

## [1.4.4] – 2026-04-26

### Added
- **100 % DE/EN coverage — final strings** — all remaining German strings from live v1.4.3 verification translated:
  - Tresor form: "Wartungskosten jährlich", "Nächster Wartungstermin", "Gebäude"
  - Kunden tab: "📄 Verträge" sub-tab button; "Haupt-Eigentümer" / "Neben-Eigentümer" escrow field labels
  - DT form + edit overlay: "Firma" label, all three escrow labels (Haupt-/Neben-Eigentümer, Rechnungsempfänger) with hint spans
  - Static empty states: "Keine Datenträger", "Noch keine archivierten Datenträger", "Keine abgeschlossenen Übergaben" now carry `data-i18n`
  - Übergabe `u-kunden_id` initial option text corrected to use `opt_firma_waehlen`
  - Templates contract editor: "§ 2 Laufzeit & Kündigung", "§ 3 Entgelt", "Standardlaufzeit", "Kündigungsfrist" labels
- **JS string fixes** — `vt-v-kunden_id` option rebuild, Tresor detail view `dl()` labels (Wartungskosten, Wartungstermine), invoice "Keine Datenträger im Abrechnungszeitraum" all use `t()` / `ta()`
- **`applyLang()` additions** — escrow select empty options ("gleiche Firma" / "keiner") updated on language switch
- 22 new TRANS keys added

---

## [1.4.3] – 2026-04-26

### Added
- **100 % DE/EN coverage — final round** — all remaining German strings identified in live verification are now translated:
  - Übergabe tab: "Schritt 1" stitle, "Firma" label, "Vorschau" / "Formular" buttons, "Firma wählen" empty state, "Weiter zu Schritt 2" button, "Ausstehende Übergabe:" label
  - Rechnung tab: "Rabatt" section heading, "Vorschau" button and stitle, "Alle löschen" button (with bilingual confirm), static "Noch keine Rechnungen" empty state
  - Templates tab: all four "Vorschau" section headings and three "Zurück" buttons now carry `data-i18n`
  - Kunden/Contracts sub-tab: all vt-v form labels (Vertragsnummer, Vertragsbeginn, Vertragsende, Laufzeit/Verlängerung, Kündigungsfrist, Besondere Vereinbarungen, hint paragraph), "Vorschau" / "Vorlage drucken" buttons, "Vorlage" row-action button in contracts table
  - Admin tab: Abteilung, Bearbeiter, Kürzel, Adresse (oben links / Fußzeile), Ort (Datumszeile), Geschäftsführung, Handelsregister, "Fußzeile & Bank" stitle, info text, "Datenträger als CSV" / "Kunden als CSV" buttons, all "Zurücksetzen" / "Konfiguration speichern" buttons including SAML section
- **JS string fixes** — `renderUebergabeListe`, `formularVorschau`, `formularHerunterladen`, `rechnungVorschau`, `rechnungExportieren`, `vtVorschauUpdate`, and `tplReset` now use `t()` / `ta()` instead of hardcoded German strings
- **`applyLang()` additions** — `k-form-title`, `r-kunden_id` empty option, and `vt-v-kunden_id` empty option are now updated on language switch

---

## [1.4.2] – 2026-04-25

### Added
- **100 % DE/EN static HTML coverage** — all remaining German strings in static HTML now switch with the language toggle:
  - Dashboard KPI labels (Active Customers, Net/Year, Active Contracts, Contracts <60 Days)
  - Edit-mode banners (`Bearbeitungsmodus` / `Edit Mode`) in Tresor and Customer forms
  - All modal dialogs fully translated: DT Edit overlay, Change Password, Set Password, Edit User, New Contract, New Role
  - Admin section: New User labels, + New Role button, Support Contact card
  - Übergabe step-2 buttons (Back, Keep in Stock, Complete)
  - Templates and Admin Logo/Colour picker labels
  - Help page title, subtitle, and Contact & Support heading
  - SAML configuration hint text
  - Static footer app name now i18n-aware; version bumped to v1.4.2
- **Select option translation** — six select elements now rebuild their option text on language switch via `applyLang()`: salutation (k-anrede), contract status (k-vertragsstatus, vt-status, vt-v-status-filter), billing unit (dt-einheit, ov-dt-einheit), user status (ue-aktiv), role colour (rm-farbe)
- **JS textContent fixes** — upload zone reset messages and the "View" button in read-only customer list now use `t()` / `ta()`; Mahnung row label translated; `tresorAbbrechen()` uses translation keys

---

## [1.4.1] – 2026-04-25

### Added
- **100 % DE/EN UI coverage** — all remaining hardcoded German strings translated:
  - All `alert()` and `confirm()` messages in Auth, Customers, Media, Invoices, Handover, Safes, Admin, and tab navigation
  - All `textContent` assignments (form titles, button labels, save confirmation)
  - Table headers in Dashboard, Contracts, Safes, Users, Invoice History, and Handover Archive
  - Select options: "Select Company", "All Companies", "No Safe", "Same Company"
  - Permission/tab labels in role editor (`renderPermGrid`)
  - `dtUpdateZusammenfassung` summary labels
  - `renderArchiv` table headers and status badge
- **`ta(de, en)` helper** — thin inline function for alert/confirm/textContent strings; automatically uses active language
- **Full bilingual Help/FAQ** — all 8 categories and 26 Q&A pairs now have DE and EN versions; rendered dynamically on language switch
- **Footer version string fixed** — was hardcoded `v1.3.8`; now shows `v1.4.1` with dynamic `ta()` label

---

## [1.4.0] – 2026-04-25

### Added
- **Full DE/EN UI translation** — all dynamic render functions (`renderKunden`, `renderDT`, `renderArchiv`), form labels, sub-tab labels, step wizard labels, table headers, empty states, and button captions now switch with the 🇩🇪/🇬🇧 toggle. The `TRANS` object extended from ~50 to ~180 keys.
- **Bilingual template editor** — each of the four print templates (Übergabe, Eingang, Rechnung, Vertrag) now has a 🇩🇪/🇬🇧 toggle inside the "Texte" card. Staff can write German and English versions of introductions, body text, footers, and contract clauses independently. Print functions automatically use the language-matching template text, falling back to German if the English version is not filled in.
- **Translated Übergabe grund options** — the reason-for-handover dropdown is populated dynamically and switches with the UI language (Rueckgabe auf Wunsch / Return on Request, Vertragsende / Contract End, etc.).

---

## [1.3.9] – 2026-04-25

### Added
- **Escrow configuration at customer level** — the customer form now has a *Szenario A / Szenario B* radio toggle. In Szenario B, two new dropdowns appear: *Haupt-Eigentümer* (main owner / software developer) and *Neben-Eigentümer* (beneficiary / licensee). These are stored on the customer record (`szenario`, `escrow_haupt_id`, `escrow_neben_id` columns, auto-migrated). When creating a new media record, selecting an Auftraggeber with Szenario B pre-fills the DT form automatically.
- **Bilingual print documents** — all four document types follow the active UI language (🇩🇪 / 🇬🇧): Eingangsprotokoll / Incoming Inspection Report, Übergabeprotokoll / Handover Protocol, Einlagerungsvertrag / Storage Agreement (2-party), Dreiseitiger Einlagerungsvertrag / Three-Party Storage Agreement. Table headers, section headings, paragraph text, and signature labels are fully translated.

---

## [1.3.8] – 2026-04-25

### Added
- **DE / EN language toggle** — 🇩🇪 DE / 🇬🇧 EN button in the top bar switches the entire UI between German and English. Preference is stored in `localStorage` and survives page reloads. All static labels, tab names, status badges, section headings, button captions, and contract labels are translated. Dynamic content (rendered lists, modals) re-renders automatically on language switch via `renderAlles()`.

---

## [1.3.7] – 2026-04-25

### Added
- **2-party storage contract (Szenario A)** — "Vertrag (2 Parteien) drucken" button in Step 2 of the Übergabe form generates a print-ready storage contract between Firma 1 (operator) and the commissioning party. Sections: §1 Parties, §2 Subject & media table, §3 Return & termination, §4 Remuneration, §5 Special conditions (optional), §6 Liability. Two signature blocks.
- **3-party escrow contract (Szenario B)** — "Vertrag (3 Parteien) drucken" button generates a full software-escrow contract naming all three parties (operator, depositor / Haupt-Eigentümer, beneficiary / Neben-Eigentümer). Sections: §1–§7 covering parties, escrow purpose, release conditions, IP protection, remuneration, liability, and final provisions.
- **Freigabebedingungen / Besondere Bedingungen textarea** — free-text field below the contract buttons in Step 2. In Szenario A the label reads "Besondere Bedingungen"; in Szenario B it reads "Freigabebedingungen". Content is printed verbatim in §5 / §6 of the respective contract if filled in.
- **Contract button visibility** — "Vertrag (2 Parteien) drucken" is only shown in Szenario A; "Vertrag (3 Parteien) drucken" is only shown in Szenario B. Both are hidden in Szenario A without escrow parties.

---

## [1.3.6] – 2026-04-25

### Fixed
- **Übergabe-Archiv duplicate entry on completion** — `renderAbgeschlosseneUebergaben` now replaces an existing entry by index instead of pushing a new one, preventing a double row when the handover was already loaded at startup and then completed.

### Added
- **Eingangsprotokoll shows ownership details in Szenario B** — the print-ready incoming-inspection report now includes Haupt-Eigentümer and Auftraggeber / Neben-Eigentümer rows when the media record is configured in Szenario B (Escrow / 3-Firmen mode).
- **Rechnung per-line Eigentümer / Einlagerer** — invoice line items now include a sub-line showing the Eigentümer and Einlagerer for each DT when the record is in Szenario B.
- **"Vertrag (3 Parteien) drucken" button** — initial version of the 3-party escrow contract print function, subsequently updated in v1.3.7.

---

## [1.3.5] – 2026-04-24

### Fixed
- **Rechnung shows DTs for wrong company** — billing filter now uses `rechnungsempfaenger_id` (falling back to `kunden_id`) so each invoice only lists media records that the selected company actually pays for.
- **Completed handover appears twice in Übergabe tab** — the push after `uebergabeAbschliessen` now checks for duplicates before inserting, preventing double-display when the handover was already loaded at startup.
- **Archived DTs never appeared in Datenträger Archiv** — status string mismatch fixed: frontend sets `status='uebergeben'` (no umlaut) but the archive filter compared against `'übergeben'` (with umlaut). Both sides now use `'uebergeben'`.
- **Login completely broken after v1.3.4 deploy** — a patch was accidentally applied twice, producing a duplicate `const hatEscrow` declaration inside `dtBearbeiten`. JavaScript rejected the script entirely, causing `doLogin is not defined` and making the app unusable.
- **`ADMIN_PASSWORD` env var now synced to DB on every startup** — previously only applied on first run via `INSERT OR IGNORE`; a redeploy with `ADMIN_PASSWORD` set now always restores that password, enabling password recovery without manual DB access.

### Added
- **Szenario A / Szenario B toggle on DT form and edit overlay** — radio buttons let staff choose between *Eigene Einlagerung* (Szenario A: hides the three ownership dropdowns) and *Escrow / 3-Firmen* (Szenario B: reveals Haupt-Eigentümer, Neben-Eigentümer, Rechnungsempfänger). The toggle resets to *Eigene Einlagerung* after a new DT is saved, and auto-detects the correct mode when opening an existing DT for editing.

---

## [1.3.3] – 2026-04-24

### Added
- **3-party ownership on Datenträger level** — each media record now has three optional ownership fields:
  - **Haupt-Eigentümer** (main owner, e.g. the software developer / Firma 3)
  - **Neben-Eigentümer** (co-owner / commissioning party, e.g. Firma 2)
  - **Rechnungsempfänger** (billing recipient — whoever pays)
  - All three reference existing customer records and default to the commissioning party (Auftraggeber) when left blank.
  - Supports the full escrow scenario: Firma 2 commissions storage, Firma 3 owns the IP on the media, either may pay.

### Fixed
- **`else` branch of DT UPDATE was missing the `interne_nr` binding** — the SQL contained `interne_nr=?` but the values tuple only had `tresor_id, did`, causing a `ProgrammingError: Incorrect number of bindings` whenever a media record was updated without a new photo or scan document.
- **Duplicate `renderAbgeschlosseneUebergaben` function** — the second definition shadowed the first; only one is now present.

### Changed
- Ownership fields (Rechnungsempfänger, Eigentümer) moved from customer record to individual media record level, which matches the actual business requirement (each DT can have different owners).
- Customer form simplified: removed the kunden-level Rechnungsempfänger and Eigentümer dropdowns.

---

## [1.3.2] – 2026-04-24

### Fixed
- **`dt-interne_nr` field not visible** — patch anchor mismatch in v1.3.1 script (placeholder text differed); field now correctly added below Seriennummer.
- **Multi-company customer selects never appeared** — wrong anchor (`Anrede Ansprechpartner` vs actual `Ansprechpartner`); now correctly inserted.
- **Logo missing in Übergabe preview** — `logoData` was only populated when the Templates tab was visited; startup now also fetches the logo.
- **Duplicate HTML/JS sections** — non-idempotent v1.3.0 patch anchor caused re-insertion on each script run; duplicates removed.

---

## [1.3.1] – 2026-04-24

### Fixed
- **Duplicate route crash** — `apply_and_push_v1.3.0` used a non-idempotent patch anchor for the `DELETE /api/uebergaben/<id>` route; re-running the script inserted a second identical route definition, causing Flask to raise `AssertionError: View function mapping is overwriting an existing endpoint function: delete_uebergabe` and the server to refuse to start. The duplicate has been removed.

---

## [1.3.0] – 2026-04-24

### Added
- **Handover archive** — completed handovers are shown directly in the tab with protocol number, company, date, media count, reason, mode badge, and PDF download button
- **Delete open handovers** — 🗑 button per pending entry; removes the handover and its positions from the database
- **"Keep in stock" mode** — new button when closing a handover: marks the handover as completed but leaves the media as `stored` (useful when a customer temporarily takes media but keeps paying)
- **Optional document upload** — a handover can now be closed without an uploaded document; a confirmation dialog is shown instead of a hard block
- **Internal number for media** — free-text `Internal No.` field when creating or editing a media record; visible in the list and included in CSV export
- **Multi-company logic** — optional billing recipient (Firma B pays for Firma A) and media owner selectable per customer record
- **Help tab full width** — removed the `max-width: 860px` constraint so the content fills the available space
- **Mobile view improvements** — tab bar scrolls horizontally without wrapping; tables are horizontally scrollable on small screens; more compact padding below 600 px

### Fixed
- **Handover recipient bug** — the recipient field was sent with the wrong JS key (`Empfänger` instead of `empfaenger`) and was always empty in the database; fixed on both client and server
- **DB migrations** — new columns (`weiter_im_bestand`, `interne_nr`, `rechnungsempfaenger_id`, `eigentuemer_id`) are added automatically on the next container start without manual schema changes

### Changed
- Closing a handover without a document now shows a confirmation dialog instead of blocking the action entirely
- Completed handovers appear in the archive immediately without a page reload

---

## [1.2.0] – 2026-04-20

### Added
- Media archive as a sub-tab (Media → Record / Archive)
- Customers & Contracts combined as one tab with sub-navigation
- Invoices & History combined as one tab with sub-navigation
- Safe detail view accessible by clicking the safe name
- Salutation field (Mr / Ms / Dr / Prof / Other) for contact persons
- Company data moved to the Admin section instead of the Templates section
- PDF button per invoice in the invoice history
- Reminder function per invoice in the invoice history with print button

### Fixed
- Safe dropdown was empty when editing a media record
- Handover completion after document download threw an error
- Removed outdated tab permissions from role management
- Responsive design: tab bar was wrapping instead of scrolling

---

## [1.1.1] – 2026-04-20

### Added
- Safe tab permission: roles can show/hide the Safes tab
- Responsive layout improvements for tablet and mobile

### Fixed
- Saving or deleting a safe triggered an unintended logout (`localStorage` vs `sessionStorage` mismatch)

---

## [1.1.0] – 2026-04-20

### Added
- Safe management (🔒 Safes) — full CRUD with location, purchase data, maintenance dates, and maintenance contract upload
- Safe assignment when registering a media record
- Dashboard: maintenance warnings for safes (60-day preview)
- CSV export extended with safe location columns
- Optional SQLite encryption via `DB_KEY` environment variable (SQLCipher AES-256)

### Changed
- Contact email updated: `marcel.capelan@tuv.com` → `info@capelan.de`

---

## [1.0.0] – 2025-04-19

### Initial public release

- Dashboard with KPIs, contract expiry warnings, and maintenance notices
- Customer management with contracts, volume discounts, and contract history
- Media management: registration, photos, incoming inspection report
- Handover workflow with print-ready handover protocol
- Invoice generation with discount tiers, VAT, and reminder function
- Archive of all returned media
- Letter template editor (invoice, handover, incoming, contract)
- Admin panel: user management, roles & permissions
- SAML 2.0 / SSO (Azure AD, Okta, Keycloak)
- PBKDF2 password security, token-based sessions, Docker Swarm support

---

*© 2025 Marcel Capelan — [capelan.de](https://capelan.de)*
