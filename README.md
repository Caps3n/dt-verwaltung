# 💾 DT-Verwaltung v1.0

**Web-based management software for stored data carriers (storage media)**  
Developed by [Marcel Capelan](https://capelan.de) · [info@capelan.de](mailto:info@capelan.de)

[![Docker](https://img.shields.io/badge/Docker-ready-blue?logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12-green?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📋 Features

| Module | Description |
|---|---|
| 📊 Dashboard | KPIs, active contracts, revenue overview, expiry warnings |
| 👥 Customers | Create & edit customers, contract data, customer-specific volume discounts |
| 📄 Contracts | Overview of all contracts, printable contract documents |
| 💾 Storage Media | Check-in, edit, photo upload, printable intake protocol |
| 🔄 Handover | Return workflow with printable handover protocol |
| 🧾 Invoice | Automatic billing, volume discounts, general discounts, VAT |
| 📋 Invoice History | Invoice archive, reprint, dunning notice |
| 🗄️ DT Archive | All returned media, search function |
| 🎨 Templates | Letter templates for all documents, logo, accent color |
| ⚙️ Admin | User management, roles & permissions, SAML/SSO |
| ❓ Help | FAQ documentation, contact |

---

## 🔒 Security

| Layer | Method | Status |
|---|---|---|
| Passwords | PBKDF2-HMAC-SHA256, 600,000 iterations, random salt | ✅ active |
| Transport | TLS 1.2/1.3 via your reverse proxy (nginx, Traefik, etc.) | ✅ recommended |
| Session tokens | 64-character cryptographically random, DB-backed, 8h TTL | ✅ active |

---

## 🚀 Quick Start (single host)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2

### Install

```bash
# 1. Clone the repository
git clone https://github.com/Caps3n/dt-verwaltung.git
cd dt-verwaltung

# 2. Create your configuration
cp .env.example .env
# Edit .env and set a strong ADMIN_PASSWORD

# 3. Start
docker compose up -d --build

# 4. Open in browser
http://localhost:8123
```

**Default login:**
```
Username: admin
Password: (as set in .env)
```

> ⚠️ Set `ADMIN_PASSWORD` in `.env` and change it in the Admin panel immediately after first login!

### Change the port

```bash
PORT=9000 docker compose up -d --build
```

---

## 🐝 Docker Swarm Stack (production)

DT-Verwaltung ships a Swarm-ready `docker-compose.yml` with `deploy:` sections,
resource limits, and Docker secrets support.

### 1. Create the admin-password secret

```bash
printf 'YourSecurePassword' | docker secret create dtv_admin_password -
```

### 2. Deploy the stack

```bash
docker stack deploy -c docker-compose.yml dtv
```

### 3. Verify

```bash
docker stack ps dtv
docker service logs dtv_app -f
```

### Update

```bash
# Pull the latest image
docker service update --image ghcr.io/caps3n/dt-verwaltung:latest dtv_app

# Or force a redeploy (e.g. after a config change)
docker service update --force dtv_app
```

### Remove

```bash
docker stack rm dtv
```

> **Data persistence:** The database lives in the `dtv-data` Docker volume and survives all updates and redeployments.

---

## ⬆️ Update (single host)

```bash
docker compose pull          # or rebuild: docker compose build
docker compose up -d
```

---

## 🔄 Restart / Stop

```bash
# Stop
docker compose down

# Start
docker compose up -d

# Logs
docker logs dtv-verwaltung -f
```

---

## 🗄️ Backup & Restore

```bash
# Create backup
docker run --rm -v dtv-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/dtv-backup-$(date +%Y%m%d).tar.gz /data

# Restore backup
docker run --rm -v dtv-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/dtv-backup-YYYYMMDD.tar.gz -C /
```

Alternatively, use the built-in **Admin → Export DB** button for a single-file `.db` download.

---

## 👤 Users & Roles

Three default roles are created automatically:

| Role | Read | Write | Delete | Templates | Users |
|---|:---:|:---:|:---:|:---:|:---:|
| **Admin** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **User** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Viewer** | ✅ | ❌ | ❌ | ❌ | ❌ |

Custom roles with individual tab visibility can be created in the Admin panel.

---

## 🔐 SAML / Single Sign-On (optional)

SAML 2.0 is supported (Azure AD, Okta, Keycloak, and others).  
Configure under **⚙️ Admin → SAML/SSO**.

---

## 🏗️ Technical Details

| Component | Technology |
|---|---|
| Backend | Python 3.12, Flask 3.x, Gunicorn |
| Database | SQLite (WAL mode, Docker volume) |
| Frontend | Vanilla JS, Single-Page App (no framework) |
| Container | Docker, non-root user (UID 1000) |
| Auth | Token-based (X-Token header), DB-backed sessions |

### Project structure

```
dt-verwaltung/
├── app/
│   ├── server.py          # Flask backend, all API routes
│   ├── saml_auth.py       # SAML 2.0 helpers (optional)
│   └── static/
│       └── index.html     # Frontend SPA
├── scripts/
│   └── generate-key.sh    # Utility scripts
├── Dockerfile
├── docker-compose.yml     # Compose / Swarm stack file
├── .env.example
├── install.sh
├── update.sh
├── CHANGELOG.md
├── LICENSE
└── README.md
```

### API Endpoints

```
GET/POST   /api/kunden
GET/PUT    /api/kunden/<id>
DELETE     /api/kunden/<id>

GET/POST   /api/datentraeger
GET/PUT    /api/datentraeger/<id>
DELETE     /api/datentraeger/<id>
GET        /api/datentraeger/<id>/bild

GET/POST   /api/uebergaben
GET        /api/uebergaben/<id>

GET/PUT    /api/templates
GET        /api/templates/logo

GET/POST   /api/rollen
PUT/DELETE /api/rollen/<id>

GET/POST   /api/benutzer
PUT        /api/benutzer/<id>
DELETE     /api/benutzer/<id>

POST       /api/login
POST       /api/logout
GET        /api/me
GET        /api/health
GET        /api/db/export
```

---

## 📄 License

MIT License — © 2025 [Marcel Capelan](https://capelan.de)

---

## 📞 Contact & Support

**Marcel Capelan**  
📧 [info@capelan.de](mailto:info@capelan.de)  
🌐 [capelan.de](https://capelan.de)
