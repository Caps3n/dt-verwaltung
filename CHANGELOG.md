# Changelog

All notable changes to DT-Verwaltung are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

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
