# Changelog

All notable changes to DT-Verwaltung are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.3.2] – 2026-04-24

### Fixed
- **Duplicate code from multiple patch runs** — running the v1.3.0/v1.3.1 scripts more than once caused non-idempotent string patches to insert duplicate HTML sections, JS functions, and buttons. Removed: 2× extra "Abgeschlossene Übergaben" card, 2× extra `deletePending` function, 1× extra `renderAbgeschlosseneUebergaben` function, 2× extra 🗑 trash buttons per pending entry
- **Multi-company fields missing** — the original patch used a wrong anchor (`<label>Anrede Ansprechpartner</label>`) that didn't match the actual HTML (`<label>Ansprechpartner</label>`); billing-recipient and owner selects were never inserted. Fixed with correct anchor.
- **Internal number (Interne Nr.) missing** — original patch anchor used placeholder `"z.B. SN-12345"` which didn't match the actual `"HDD-2024-001"`. Field now correctly added to both the registration form and the edit overlay.
- **Logo missing in handover preview** — `logoData` was only loaded when the user visited the Templates tab; the handover document preview showed a placeholder box instead. Templates (including logo, accent colour, `_T`, `_TU`) are now loaded at startup.
- **DB migrations missing for interne_nr, rechnungsempfaenger_id, eigentuemer_id** — columns were never added to the database because the migration patch used a wrong anchor. All four new columns now migrate correctly on container start.
- **interne_nr not persisted** — missing from all DT INSERT/UPDATE branches on the server.
- **rechnungsempfaenger_id / eigentuemer_id not persisted** — missing from kunden INSERT and UPDATE on the server.

---

## [1.3.1] – 2026-04-24

### Fixed
- **Duplicate route crash** — `apply_and_push_v1.3.0` used a non-idempotent patch anchor for the `DELETE /api/uebergaben/<id>` route; re-running the script inserted a second identical route definition, causing Flask to raise `AssertionError: View function mapping is overwriting an existing endpoint function: delete_uebergabe` and the server to refuse to start. The duplicate has been removed.

---

## [1.3.0] – 2026-04-24

### Added
- **Handover archive** — completed handovers are shown directly in the tab with protocol number, company, date, media count, reason, mode badge, and PDF download button
- **Delete open handovers** — 🗑 button per pending entry; removes the handover and its positions from the database
- **"Keep in stock" mode** — new button when closing a handover: marks the handover as completed but leaves the media as `stored`
- **Optional document upload** — a handover can now be closed without an uploaded document; a confirmation dialog is shown instead of a hard block
- **Internal number for media** — free-text `Internal No.` field when creating or editing a media record; visible in the list and included in CSV export
- **Multi-company logic** — optional billing recipient and media owner selectable per customer record
- **Help tab full width** — removed the `max-width: 860px` constraint
- **Mobile view improvements** — tab bar scrolls horizontally, tables scrollable on small screens

### Fixed
- **Handover recipient bug** — recipient field sent with wrong JS key and was always empty in DB
- **DB migrations** — new columns added automatically on container start

---

## [1.2.0] – 2026-04-20

### Added
- Media archive sub-tab, Customers & Contracts sub-navigation, Invoices & History sub-navigation
- Safe detail view, salutation field for contacts, company data in Admin section
- PDF button and reminder function per invoice

### Fixed
- Safe dropdown empty when editing media, handover completion error after doc download
- Removed outdated tab permissions, responsive tab bar wrapping

---

## [1.1.1] – 2026-04-20

### Fixed
- Safe tab permission toggle for roles
- Unintended logout when saving/deleting a safe (`localStorage` vs `sessionStorage`)

---

## [1.1.0] – 2026-04-20

### Added
- Safe management (🔒), safe assignment for media, dashboard maintenance warnings
- CSV export with safe location columns, optional SQLite encryption (SQLCipher AES-256)

---

## [1.0.0] – 2025-04-19

### Initial public release
- Dashboard, customer & contract management, media management, handover workflow
- Invoice generation with reminders, archive, letter templates, admin panel
- SAML 2.0 / SSO, PBKDF2 passwords, token sessions, Docker Swarm support

---

*© 2025 Marcel Capelan — [capelan.de](https://capelan.de)*
