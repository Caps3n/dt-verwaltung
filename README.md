# DT-Verwaltung v1.9.1

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-caps3n-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/caps3n)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue?style=for-the-badge&logo=docker)](https://ghcr.io/caps3n/dt-verwaltung)
[![Version](https://img.shields.io/badge/Version-1.9.1-2563eb?style=for-the-badge)](https://github.com/Caps3n/dt-verwaltung/releases)

Web-based management solution for secure data-carrier storage and software escrow. Built for service providers who store, manage, and document the return of data carriers (HDDs, SSDs, tapes, USB drives, etc.) on behalf of their customers — including full support for 3-party software-escrow arrangements.

Available in 🇩🇪 German and 🇬🇧 English — switchable at runtime via the language toggle in the top bar.

---

## What's New in v1.9.x

- **Animated login screen** — rotating concentric rings on a deep-navy canvas, glassmorphism login card with `backdrop-filter: blur`
- **Gradient accent bar** — animated blue gradient stripe at the top of every page
- **Page transitions** — smooth `fadeInUp` on every tab switch
- **KPI count-up animation** — dashboard numbers count up from zero on load with eased interpolation
- **Animated dashboard bars** — revenue bars slide in with a 900ms ease transition
- **Card hover lift** — cards subtly raise on hover
- **Modern design system** — Inter font, Slate-based colour palette, solid primary buttons, focus rings, subtle shadows (v1.8.1)
- **Automatic notification engine** — background scheduler for overdue invoice reminders, maintenance warnings, and weekly digest emails (v1.8.0)
- **Barcode scan → serial number** — 📷 button next to serial number field; supports Code128, Code39, EAN-13 in addition to QR (v1.8.0)
- **Admin Automatik-Tab** — toggle switches for all automated notification types (v1.8.0)

---

## Features

### Dashboard
- 6 KPI tiles with animated count-up — stored media, active customers, annual revenue, active contracts, expiring contracts (< 60 days), open invoices
- Chart.js interactive charts — monthly revenue bar chart (12 months, animated), DT-status donut chart, vault utilisation horizontal bar chart
- Quick-action buttons — one click to create a new media record, invoice, handover, or customer
- Upcoming appointments widget — maintenance dates, contract expirations, and overdue invoices colour-coded by urgency

### Storage Media (Datenträger)
- Registration with type, serial number, internal number, unit price, discount
- **Barcode / QR scan** — 📷 button opens camera scanner; result written directly into the serial number field. Supports `code_128`, `code_39`, `ean_13`, `ean_8`, `qr_code` via BarcodeDetector API (+ jsQR fallback)
- 3-party ownership per record: Auftraggeber, Haupt-Eigentümer, Neben-Eigentümer, Rechnungsempfänger
- High-resolution photo, notes tab, maintenance history tab
- Print-ready incoming inspection report
- Safe / cabinet assignment, CSV export, batch actions

### Invoices & Reminders
- Automatic invoice creation with volume discount, flat discount, and VAT
- Configurable reminders per customer (1st / 2nd / … / Final Notice)
- Send reminders by email directly from the history (📧 button)
- Payment status tracking per invoice

### Automated Notifications (🤖 Automatik)
- **Auto invoice reminders** — emails customers with overdue invoices; configurable threshold in days; deduplication prevents double-sends
- **Maintenance warnings** — notifies when media service is due or overdue; configurable lead time
- **Weekly digest** — summary email: open invoices, stored media count, contracts expiring within 30 days
- Runs as a background daemon thread (hourly); requires SMTP to be configured

### Security
- PBKDF2-HMAC-SHA256 (600k iterations) password hashing
- Session tokens in `sessionStorage`; every request verifies against the DB (multi-worker safe)
- Rate limiting via flask-limiter (brute-force protection on login)
- Granular permission roles (`read`, `write`, `delete`, `editTemplate`, `manageUsers`)
- All CRUD operations write to the audit log
- Server-side field length validation on all text inputs
- TOTP / 2FA via pyotp — setup and disable require current password
- SAML / SSO via pysaml2 (optional)
- Upload size limit: 10 MB per file; CSP + security headers

### Admin
- User management, role management with granular permission toggles
- SMTP configuration with Fernet-encrypted password storage
- Audit log viewer with CSV export
- SAML / SSO configuration
- **🤖 Automatik tab** — toggle switches for all notification types with configurable parameters
- DB backup download

### Design & UX
- **Inter font** with system-ui fallback; antialiased rendering
- **Slate-based colour palette** — `--txt: #0f172a`, `--mut: #64748b`, `--acc: #2563eb`
- Dark / light mode toggle — respects `prefers-color-scheme` by default
- Mobile-responsive with hamburger menu (≤ 1024px)
- Animated login screen with canvas background (60fps)
- Page transitions, card hover lift, KPI count-up, animated bar charts
- `prefers-reduced-motion` — all animations disabled for users who prefer it
- QR / barcode scanner (BarcodeDetector + jsQR fallback)

---

## Quick Start (Docker)

```bash
docker run -d \
  --name dtv-verwaltung \
  --restart unless-stopped \
  -p 8123:5000 \
  -v dtv-data:/data \
  -e ADMIN_PASSWORD=your-secure-password \
  ghcr.io/caps3n/dt-verwaltung:latest
```

Open `http://localhost:8123` and log in with `admin` / `your-secure-password`.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ADMIN_PASSWORD` | `admin123` | Admin password (synced on every start) |
| `ADMIN_PASSWORD_FILE` | — | Path to Docker secret file |
| `RESET_ADMIN_PASSWORD` | — | One-time password reset on next start |
| `DATA_DIR` | `/data` | SQLite database directory |
| `PORT` | `5000` | Internal app port |
| `ALLOWED_ORIGIN` | `*` | CORS allowed origin |
| `DB_KEY` | — | SQLCipher encryption key (fresh installs only) |

### Portainer Stack (recommended)

```yaml
services:
  dtv-app:
    image: ghcr.io/caps3n/dt-verwaltung:latest
    container_name: dtv-verwaltung
    restart: unless-stopped
    ports:
      - "${PORT:-8123}:5000"
    volumes:
      - dtv-data:/data
    environment:
      - DATA_DIR=/data
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-ChangeMe!}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/ping')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

volumes:
  dtv-data:
    driver: local
```

> **Note:** Use `/api/ping` (not `/api/health`) in the healthcheck. `/api/health` requires authentication and will cause a restart loop.

### Updating

```bash
docker pull ghcr.io/caps3n/dt-verwaltung:latest
docker restart dtv-verwaltung
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask 3.x, Gunicorn |
| Database | SQLite WAL — optional SQLCipher encryption |
| Frontend | Vanilla JS, Chart.js, Inter font |
| Auth | PBKDF2-HMAC-SHA256, pyotp (TOTP), pysaml2 (SAML) |
| Container | Docker, GitHub Actions CI/CD → ghcr.io |
| Config | `--workers 1 --threads 8` (optimal for SQLite WAL) |

---

## Architecture Notes

- **Single-file frontend** — all HTML, CSS, and JS in `app/static/index.html`. No build step.
- **SQLite WAL mode** — concurrent reads, single writer. 1 Gunicorn worker + 8 threads is optimal.
- **Session tokens** — `sessionStorage` on client; backed by `sessions` DB table. Logout invalidates the row; all workers verify on every request (multi-worker safe).
- **Background scheduler** — daemon thread, runs hourly checks; deduplication via `auto_notif_log`.

---

## License

MIT — see [LICENSE](LICENSE)

Built by [Marcel Capelan](https://capelan.de) · [info@capelan.de](mailto:info@capelan.de)
