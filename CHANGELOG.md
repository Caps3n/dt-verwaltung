# Changelog

All notable changes to DT-Verwaltung are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.1.1] – 2026-04-20

### Fixed
- **Tresor save/delete caused unintended logout** — `tresorSpeichern` and `tresorLoeschen` were reading the session token from `localStorage` instead of `sessionStorage` (where the app stores it). This sent `X-Token: null` to the server, which returned 401 and triggered a logout on every Tresor save or delete.

---

## [1.1.0] – 2026-04-20

### Added
- **Safe/Vault management (🔒 Tresore)** — new dedicated tab for managing physical safes and storage cabinets:
  - Full CRUD with name, manufacturer, model, serial number
  - Location tracking: Country / City / Building / Floor / Room
  - Purchase date and purchase cost
  - Annual maintenance cost
  - Last and next maintenance date
  - Maintenance contract upload (PDF)
  - Notes field
- **Tresor assignment on storage media** — when checking in a data carrier, optionally assign it to a safe/vault; location is shown in the DT list view and included in CSV exports
- **Dashboard: maintenance warnings** — upcoming or overdue safe maintenance appointments (within 60 days) shown as a dedicated card with color-coded badges
- **CSV export extended** — Datenträger export now includes all Tresor location columns (Tresor name, Country, City, Building, Floor, Room); exported via server-side endpoint for accuracy
- **Optional database encryption** — SQLite database can be encrypted with SQLCipher AES-256 by setting `DB_KEY` in `.env` before first start; plain SQLite remains the default

### Changed
- Contact email updated: `marcel.capelan@tuv.com` → `info@capelan.de` throughout all files

### Notes
- Tresor information is intentionally **not** included in printed documents (intake protocol, handover protocol) — only shown in the web interface and CSV exports
- `DB_KEY` must be set before first start; changing it on an existing database is not supported without a fresh installation

---

## [1.0.0] – 2025-04-19

### 🎉 Initial public release

#### Added
- **Dashboard** — KPIs (active contracts, stored media, monthly/annual revenue), expiry warnings
- **Customers** — full CRUD with contract data and contract history
- **Volume discounts** — customer-specific, configurable up to 5 pricing tiers
- **Storage media** — check-in, editing, photo upload, status tracking (stored / returned)
- **Intake protocol** — printable PDF receipt for incoming media
- **Handover workflow** — return process with printable handover protocol
- **Invoicing** — automatic billing with volume discount, general discount, and VAT
- **Invoice history** — archive with reprint and dunning notice function
- **DT Archive** — searchable list of all returned media
- **Templates** — letter/document templates with logo upload and accent color
- **Admin panel** — user management, roles & permissions with per-tab visibility control
- **SAML 2.0 / SSO** — optional integration with Azure AD, Okta, Keycloak and others
- **Help tab** — FAQ accordion with configurable support contact
- **Security** — PBKDF2-HMAC-SHA256 passwords (600,000 iterations, random salt), auto-upgrade from legacy SHA-256 hashes on login
- **Session management** — 64-character cryptographically random tokens, DB-backed, 8h TTL
- **Docker Swarm** — production-ready stack with `deploy:` sections, resource limits, and Docker secrets
- **Non-root container** — runs as UID 1000 for improved security
- **Health check** — `/api/health` endpoint with Docker `HEALTHCHECK` integration

#### Technical Stack
- Python 3.12, Flask 3.x, Gunicorn
- SQLite with WAL mode, persisted in Docker volume
- Vanilla JS single-page application (no framework)
- Token-based authentication (`X-Token` header)

---

*© 2025 Marcel Capelan — [capelan.de](https://capelan.de)*
