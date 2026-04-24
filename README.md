# DT-Verwaltung v1.3.2

Web-based management solution for secure data-carrier storage.
Built for service providers who store, manage, and document the return of data carriers (HDDs, SSDs, tapes, USB drives, etc.) on behalf of their customers.

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
- **Multi-company support:** optional billing recipient (Company B pays for Company A) and media owner selectable per customer record
- Volume discounts: up to 5 customer-specific price tiers
- Contract history / audit trail

### Media (Datenträger)
- Registration with type, serial number, **internal number**, unit price, discount
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
- Last and next maintenance date, maintenance contract upload (PDF)

### Templates & Letter Layouts
- Logo upload and accent colour for all documents
- Templates for: invoice, handover, incoming report, contract
- Live preview while editing, placeholder system

### Admin Panel
- Company data, user management, roles & permissions
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
3. Deploy the Stack — open `http://<server-ip>:5000`

### Updating

Portainer → Stack → **Pull and Redeploy**
(GitHub Actions builds automatically on every push to `main`)

---

## Local Development

```bash
git clone https://github.com/Caps3n/dt-verwaltung.git
cd dt-verwaltung
pip install flask flask-cors gunicorn pysaml2 cryptography
python app/server.py
```

Open: `http://localhost:5000` — default login: `admin` / value of `ADMIN_PASSWORD`

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

## License

MIT License — © 2025 Marcel Capelan · [capelan.de](https://capelan.de)
