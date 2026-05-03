# DT-Verwaltung v1.4.9

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-caps3n-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/caps3n)

Web-based management solution for secure data-carrier storage and software escrow.
Built for service providers who store, manage, and document the return of data carriers (HDDs, SSDs, tapes, USB drives, etc.) on behalf of their customers — including full support for 3-party software-escrow arrangements.

Available in 🇩🇪 German and 🇬🇧 English — switchable at runtime via the language toggle in the top bar.

---

## Features

### Dashboard
- KPIs: active contracts, stored media, monthly and annual revenue
- Contract expiry warnings (60-day preview, colour-coded)
- Safe and cabinet maintenance warnings

### Customers & Contracts
- Full customer CRUD with contact person, address, and salutation
- Contract data: number, status, duration, notice period, notes
- Contract document upload (PDF) per customer
- Volume discounts: up to 5 customer-specific price tiers
- Contract history / audit trail

### Media (Datenträger)
- Registration with type, serial number, **internal number**, unit price, discount
- **3-party ownership per media record:**
  - **Auftraggeber** (commissioning party, required) — the customer who contracts the storage
  - **Haupt-Eigentümer** (main owner, optional) — the party whose IP is on the media (e.g. software developer)
  - **Neben-Eigentümer** (co-owner, optional) — usually the commissioning party in escrow scenarios
  - **Rechnungsempfänger** (billing recipient, optional) — whoever pays; defaults to Auftraggeber
- Photo upload per media record
- Print-ready incoming inspection report with letterhead
- Status tracking: `stored` / `handed over`
- Safe / cabinet assignment with location display
- CSV export with all columns including safe location and internal number

### Handover Workflow
- Step 1: select company, pick media, generate and print the handover protocol
- Step 2: upload the signed document (optional), close the handover
- **"Keep in stock" mode:** close a handover without marking media as handed over
- **Delete open handovers** with the 🗑 button
- **Archive of all completed handovers** with protocol number, mode badge, and PDF download

### Invoices
- Automatic invoice creation with volume discount, flat discount, and VAT
- Invoice history with per-invoice PDF regeneration
- Reminder function: 1st / 2nd / 3rd reminder per invoice with print button

### Safe Management (🔒)
- CRUD for physical safes and cabinets: name, manufacturer, model, serial number
- Location: country / city / building / floor / room
- Purchase date, purchase price, annual maintenance costs
- Last and next maintenance date
- Maintenance contract upload (PDF)
- Safe detail view accessible by clicking the safe name

### Templates & Letter Layouts
- Logo upload and accent colour for all documents
- Templates for: invoice, handover, incoming report, contract
- Live preview while editing
- Placeholder system (company, date, amounts, media list, etc.)

### Software Escrow (3-Party Mode)
- Toggle between **Szenario A** (2-party: operator + depositor) and **Szenario B** (3-party escrow)
- In Szenario B each media record stores: Auftraggeber (commissioning party), Haupt-Eigentümer (software owner / depositor), Neben-Eigentümer (beneficiary / licensee), and Rechnungsempfänger (billing recipient)
- Escrow use-case: software developer (Firma 2) deposits source code; licensee (Firma 3) receives it only if Firma 2 ceases to operate
- Eingangsprotokoll and invoices display the relevant party names in Szenario B

### Contract Printing
- **2-party storage contract** — generated from Step 2 of the handover workflow; covers parties, stored media list, return terms, remuneration, special conditions, and liability
- **3-party escrow contract** — covers all three parties with escrow-specific clauses: release conditions, IP protection, remuneration, and final provisions
- **Freigabebedingungen / Besondere Bedingungen** — optional free-text field printed verbatim in the contract
- Button visibility is context-aware: the 2-party button appears in Szenario A, the 3-party button in Szenario B

### Language / i18n
- 🇩🇪 DE / 🇬🇧 EN toggle button in the top bar
- All labels, tab names, headings, status badges, and button captions are translated
- Dynamic content re-renders automatically on language switch
- Preference is persisted in `localStorage`

### Admin Panel
- Company data: name, address, bank details, tax number, footer text
- User management: create users, reset passwords, assign roles
- Roles & permissions: fine-grained tab visibility per role
- SAML 2.0 / SSO: Azure AD, Okta, Keycloak, and other IdPs

### Security
- Passwords: PBKDF2-HMAC-SHA256 (600,000 iterations, random salt)
- Sessions: 64-character cryptographically secure tokens, DB-backed, 8 h TTL
- Optional SQLite encryption via SQLCipher AES-256 (`DB_KEY` env var)
- Runs as a non-root container (UID 1000)

---

## Deployment (Docker / Portainer)

### Portainer Stack (recommended)

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
      - ADMIN_PASSWORD=yourSecurePassword
      # - DB_KEY=encryptionKey   # set only on first install
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
2. Paste the stack, set `ADMIN_PASSWORD`
3. Deploy the Stack
4. Open: `http://<server-ip>:5000`

### Updating to a new version

Portainer → Stack → **Pull and Redeploy**
(GitHub Actions builds a new image automatically on every push to `main`)

---

## Local Development

```bash
git clone https://github.com/Caps3n/dt-verwaltung.git
cd dt-verwaltung
pip install flask flask-cors gunicorn pysaml2 cryptography
python app/server.py
```

Open: `http://localhost:5000`
Default login: `admin` / value of `ADMIN_PASSWORD` (default: `admin`)

---

## Database

SQLite database at `/data/dtv.db` (persistent Docker volume).
Migrations are applied automatically on start — no manual schema management required.

Optional encryption: set `DB_KEY` in the environment **before** the first start.
⚠️ Enabling encryption on an existing unencrypted database is not supported.

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.12, Flask 3.x, Gunicorn |
| Database | SQLite (WAL mode), optional SQLCipher |
| Frontend | Vanilla JS SPA (no framework), HTML5, CSS3 |
| Auth | Token-based (`X-Token` header), optional SAML 2.0 |
| Container | Docker, non-root (UID 1000), health check |
| CI/CD | GitHub Actions → ghcr.io |

---

## Support

If this project is useful to you, consider buying me a coffee ☕

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/caps3n)

---

## License

MIT License — © 2025 Marcel Capelan · [capelan.de](https://capelan.de)
