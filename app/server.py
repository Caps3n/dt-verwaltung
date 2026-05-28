#!/usr/bin/env python3
"""DT-Verwaltung Backend – Flask + SQLite/SQLCipher (Docker-ready)"""
import json, hashlib, hmac, secrets, os, base64, sqlite3, time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False
    print("[2FA] pyotp not installed – TOTP disabled")
from flask import Flask, request, jsonify, send_from_directory, send_file, redirect
from flask_cors import CORS
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    print("[SEC] CRITICAL: flask-limiter not installed – rate limiting DISABLED. "
          "Install flask-limiter>=3.5 to enable brute-force protection.")

# ─── ENCRYPTION SETUP ────────────────────────────────────────────────────────
DB_KEY = os.environ.get('DB_KEY', '').strip()

_ENC_MOD = None
if DB_KEY:
    for _mod_name in ('pysqlcipher3.dbapi2', 'sqlcipher3.dbapi2'):
        try:
            import importlib
            _ENC_MOD = importlib.import_module(_mod_name)
            print(f"[CRYPTO] SQLCipher loaded via {_mod_name}")
            break
        except ImportError:
            continue
    if _ENC_MOD is None:
        print("[CRYPTO] WARNING: DB_KEY set but SQLCipher not available – running unencrypted!")
else:
    print("[CRYPTO] No DB_KEY – database unencrypted (set DB_KEY in .env to enable encryption on first start)")
try:
    from saml_auth import (is_saml_enabled, get_saml_login_url, process_saml_response,
                            map_groups_to_rolle, generate_sp_metadata, generate_self_signed_cert)
    SAML_AVAILABLE = True
except ImportError:
    SAML_AVAILABLE = False
    def is_saml_enabled(): return False

app = Flask(__name__, static_folder='static')

# ─── CORS: restrict to own domain (or allow all in dev mode) ─────────────────
_ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')
if _ALLOWED_ORIGIN == '*':
    print("[SEC] WARNING: CORS is open to all origins (ALLOWED_ORIGIN=*). "
          "Set ALLOWED_ORIGIN=https://your-domain.com in production.")
CORS(app, resources={r"/api/*": {"origins": _ALLOWED_ORIGIN}})

# ─── RATE LIMITER ─────────────────────────────────────────────────────────────
if LIMITER_AVAILABLE:
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://"
    )
else:
    limiter = None

# DB in persistent volume /data
DATA_DIR = os.environ.get('DATA_DIR', '/data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'dtv.db')
SESSIONS = {}  # token -> {user_id, expires}  (in-memory cache, backed by DB)
_last_clean = 0.0   # Unix timestamp of last clean_sessions() run
# SAML client cache (keyed by config hash for hot-reload)
_saml_client_cache = {}
_saml_tmp_registry = {}  # cfg_key -> list of temp file paths created for that client

# ─── SMTP PASSWORD ENCRYPTION (Fernet, key auto-generated in /data/smtp.key) ──
_SMTP_KEY_FILE = os.path.join(os.environ.get('DATA_DIR', '/data'), 'smtp.key')

def _get_smtp_fernet():
    """Return a Fernet instance for SMTP password encryption, or None if unavailable."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    try:
        if not os.path.exists(_SMTP_KEY_FILE):
            key = Fernet.generate_key()
            with open(_SMTP_KEY_FILE, 'wb') as _f:
                _f.write(key)
            try:
                os.chmod(_SMTP_KEY_FILE, 0o600)
            except Exception:
                pass
            print("[SEC] Generated new SMTP encryption key at", _SMTP_KEY_FILE)
        with open(_SMTP_KEY_FILE, 'rb') as _f:
            key = _f.read().strip()
        return Fernet(key)
    except Exception as e:
        print(f"[SEC] SMTP key error: {e} – storing password plaintext as fallback")
        return None

def _encrypt_smtp_pw(pw: str) -> str:
    if not pw:
        return pw
    f = _get_smtp_fernet()
    if not f:
        return pw  # fallback: plaintext
    return 'enc:' + f.encrypt(pw.encode()).decode()

def _decrypt_smtp_pw(stored: str) -> str:
    if not stored:
        return stored
    if not stored.startswith('enc:'):
        return stored  # legacy plaintext – still works
    f = _get_smtp_fernet()
    if not f:
        return ''
    try:
        return f.decrypt(stored[4:].encode()).decode()
    except Exception:
        return ''

# ─── SIMPLE TTL CACHE ─────────────────────────────────────────────────────────
# Lightweight in-memory cache to reduce DB reads for frequently-accessed endpoints.
# TTL default: 30 s. Invalidated explicitly on every write/update/delete.
_cache: dict = {}

def _cache_get(key):
    entry = _cache.get(key)
    if entry and time.time() < entry['exp']:
        return entry['val']
    _cache.pop(key, None)
    return None

def _cache_set(key, val, ttl: int = 30):
    _cache[key] = {'val': val, 'exp': time.time() + ttl}

def _cache_del(*keys):
    for k in keys:
        _cache.pop(k, None)

# ─── SAML ONE-TIME CODES (short-lived, single-use token exchange) ─────────────
_saml_codes: dict = {}  # {code: {'token': str, 'expires': float}}

def _saml_code_create(token: str) -> str:
    """Generate a 30-second one-time code that can be exchanged for a session token."""
    # Prune expired codes
    now = time.time()
    expired = [c for c, v in _saml_codes.items() if now > v['expires']]
    for c in expired:
        del _saml_codes[c]
    code = secrets.token_urlsafe(32)
    _saml_codes[code] = {'token': token, 'expires': now + 30}
    return code

# ─── SESSION STORE (DB-backed für multi-worker-safe auth) ────────────────────
def session_create(user_id, expires_iso):
    """Write a new session to DB and in-memory cache."""
    token = secrets.token_hex(32)
    SESSIONS[token] = {'user_id': user_id, 'expires': expires_iso}
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO sessions(token, user_id, expires) VALUES(?,?,?)",
        (token, user_id, expires_iso)
    )
    db.commit()
    db.close()
    return token

def session_get(token):
    """Get session from DB, with in-memory cache as performance hint.

    Always verifies against the DB so that logout on one Gunicorn worker
    invalidates the session on all others (multi-worker safety).
    """
    db = get_db()
    row = db.execute("SELECT user_id, expires FROM sessions WHERE token=?", (token,)).fetchone()
    db.close()
    if row:
        sess = {'user_id': row['user_id'], 'expires': row['expires']}
        SESSIONS[token] = sess  # keep cache warm for non-auth paths
        return sess
    # Token not in DB — remove stale in-memory entry if present
    SESSIONS.pop(token, None)
    return None

def session_delete(token):
    """Remove session from cache and DB."""
    SESSIONS.pop(token, None)
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token=?", (token,))
    db.commit()
    db.close()

def clean_sessions():
    """Remove expired sessions from DB and cache. Runs at most once per minute."""
    import time
    global _last_clean
    now_ts = time.monotonic()
    if now_ts - _last_clean < 60:
        return  # skip — cleaned recently enough
    _last_clean = now_ts
    now = datetime.now().isoformat()
    db = get_db()
    db.execute("DELETE FROM sessions WHERE expires < ?", (now,))
    db.commit()
    db.close()
    expired = [t for t, s in list(SESSIONS.items()) if s['expires'] < now]
    for t in expired:
        del SESSIONS[t]

def build_saml_client_from_db(s):
    """Build a pysaml2 client from DB-stored SAML settings, with caching.

    Temp files are tracked alongside their cache entry. On exception during
    build, all temp files created so far are cleaned up immediately.
    When a new config replaces an old cached entry, the old temp files are
    deleted to prevent accumulation.
    """
    import hashlib as _hashlib, tempfile
    cfg_key = _hashlib.md5(json.dumps(s, sort_keys=True).encode()).hexdigest()
    if cfg_key in _saml_client_cache:
        return _saml_client_cache[cfg_key]

    from saml2 import config as saml2_config
    from saml2.client import Saml2Client

    tmp_files = []  # track all temp files so we can clean up on failure

    def _tmp_write(suffix, content):
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode='w')
        f.write(content)
        f.close()
        tmp_files.append(f.name)
        return f.name

    try:
        metadata = {}
        if s.get('idp_metadata_url'):
            metadata['remote'] = [{'url': s['idp_metadata_url']}]
        if s.get('idp_metadata_xml'):
            metadata['local'] = [_tmp_write('.xml', s['idp_metadata_xml'])]

        cfg_dict = {
            'entityid': s.get('sp_entity_id', ''),
            'service': {
                'sp': {
                    'name': 'DT-Verwaltung',
                    'endpoints': {
                        'assertion_consumer_service': [
                            (s.get('sp_acs_url', ''),
                             'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'),
                        ],
                    },
                    'authn_requests_signed': bool(s.get('want_signed')),
                    'want_assertions_signed': True,
                    'allow_unsolicited': True,
                },
            },
            'metadata': metadata,
            'debug': False,
        }

        if s.get('sp_cert') and s.get('sp_key'):
            cfg_dict['key_file']  = _tmp_write('.key', s['sp_key'])
            cfg_dict['cert_file'] = _tmp_write('.crt', s['sp_cert'])

        cfg = saml2_config.Config()
        cfg.load(cfg_dict)
        client = Saml2Client(config=cfg)

        # Evict old cache entry and clean up its temp files
        if '_saml_tmp_files' not in globals():
            pass  # module-level dict tracks tmp files per cfg_key
        old_files = _saml_tmp_registry.pop(cfg_key, [])
        for f in old_files:
            try: os.unlink(f)
            except OSError: pass

        _saml_client_cache[cfg_key] = client
        _saml_tmp_registry[cfg_key] = tmp_files
        return client

    except Exception:
        # Clean up any temp files created before the failure
        for f in tmp_files:
            try: os.unlink(f)
            except OSError: pass
        raise


def process_saml_response_with_client(client, saml_response_b64):
    """Parse SAML response using a pre-built client."""
    from saml2 import BINDING_HTTP_POST

    authn_response = client.parse_authn_request_response(
        saml_response_b64, BINDING_HTTP_POST)
    if authn_response is None:
        raise ValueError('Leere SAML-Antwort')

    identity = authn_response.get_identity()
    name_id  = str(authn_response.get_subject())

    def get_attr(identity, *keys):
        for key in keys:
            val = identity.get(key)
            if val:
                return val[0] if isinstance(val, list) else val
        return None

    email = get_attr(identity,
        'email',
        'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
        'urn:oid:0.9.2342.19200300.100.1.3',
    ) or name_id

    name = get_attr(identity,
        'displayName',
        'http://schemas.microsoft.com/identity/claims/displayname',
        'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
        'urn:oid:2.16.840.1.113730.3.1.241',
    ) or email.split('@')[0]

    groups = identity.get(
        'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups',
        identity.get('groups', identity.get('memberOf', [])))
    if isinstance(groups, str):
        groups = [groups]

    return {'email': email, 'name': name, 'name_id': name_id, 'groups': groups or []}

# ─── DB INIT ─────────────────────────────────────────────────────────────────
def get_db():
    if _ENC_MOD and DB_KEY:
        db = _ENC_MOD.connect(DB_PATH)
        db.execute(f"PRAGMA key=\"x'{DB_KEY}'\"")
        db.execute("PRAGMA cipher_page_size=4096")
        db.execute("PRAGMA kdf_iter=256000")
        db.row_factory = _ENC_MOD.Row
    else:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS rollen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        farbe TEXT DEFAULT 'bg',
        berechtigungen TEXT NOT NULL DEFAULT '{"read":true,"write":false,"delete":false,"editTemplate":false,"manageUsers":false}'
    );
    CREATE TABLE IF NOT EXISTS benutzer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        rollen_id INTEGER NOT NULL DEFAULT 3,
        aktiv INTEGER DEFAULT 1,
        erstellt TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (rollen_id) REFERENCES rollen(id)
    );
    CREATE TABLE IF NOT EXISTS kunden (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nr TEXT UNIQUE NOT NULL,
        firma TEXT NOT NULL,
        ansprechpartner TEXT,
        email TEXT,
        tel TEXT,
        mobil TEXT,
        strasse TEXT,
        plz TEXT,
        ort TEXT,
        land TEXT DEFAULT 'Deutschland',
        sap_nr TEXT,
        vertragsnr TEXT,
        vertragsbeginn TEXT,
        vertragsende TEXT,
        vertragsstatus TEXT DEFAULT 'aktiv',
        vertragsnotiz TEXT,
        mengenrabatt_json TEXT DEFAULT '[]',
        max_mahnungen INTEGER DEFAULT 3,
        mahngebuehr REAL DEFAULT 5.00,
        vertrag_doc BLOB,
        vertrag_doc_type TEXT,
        vertrag_doc_name TEXT,
        erstellt TEXT DEFAULT CURRENT_TIMESTAMP,
        geaendert TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS vertrags_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kunden_id INTEGER NOT NULL,
        datum TEXT NOT NULL,
        vertragsnr TEXT,
        status TEXT,
        notiz TEXT,
        doc BLOB,
        doc_type TEXT,
        doc_name TEXT,
        FOREIGN KEY (kunden_id) REFERENCES kunden(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS datentraeger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kunden_id INTEGER NOT NULL,
        bezeichnung TEXT NOT NULL,
        serial TEXT NOT NULL,
        preis REAL NOT NULL DEFAULT 0,
        einheit TEXT DEFAULT 'monat',
        preis_jahr REAL NOT NULL DEFAULT 0,
        rabatt REAL DEFAULT 0,
        einlagerungs_datum TEXT NOT NULL,
        beschreibung TEXT,
        status TEXT DEFAULT 'eingelagert',
        bild BLOB,
        bild_type TEXT,
        eingang_doc BLOB,
        eingang_doc_type TEXT,
        eingang_doc_name TEXT,
        erstellt TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kunden_id) REFERENCES kunden(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS uebergaben (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kunden_id INTEGER NOT NULL,
        datum TEXT NOT NULL,
        empfaenger TEXT,
        grund TEXT,
        protokoll_nr TEXT,
        doc BLOB,
        doc_type TEXT,
        doc_name TEXT,
        abgeschlossen INTEGER DEFAULT 0,
        erstellt TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kunden_id) REFERENCES kunden(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS uebergabe_positionen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uebergabe_id INTEGER NOT NULL,
        datentraeger_id INTEGER NOT NULL,
        FOREIGN KEY (uebergabe_id) REFERENCES uebergaben(id) ON DELETE CASCADE,
        FOREIGN KEY (datentraeger_id) REFERENCES datentraeger(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS template_settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        rechnung_json TEXT DEFAULT '{}',
        uebergabe_json TEXT DEFAULT '{}',
        eingang_json TEXT DEFAULT '{}',
        vertrag_json TEXT DEFAULT '{}',
        logo BLOB,
        logo_type TEXT,
        akzentfarbe TEXT DEFAULT '#0065A4'
    );
    CREATE TABLE IF NOT EXISTS saml_settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        enabled INTEGER DEFAULT 0,
        idp_name TEXT DEFAULT 'Single Sign-On',
        sp_entity_id TEXT DEFAULT '',
        sp_acs_url TEXT DEFAULT '',
        idp_metadata_url TEXT DEFAULT '',
        idp_metadata_xml TEXT DEFAULT '',
        group_mapping TEXT DEFAULT '{}',
        want_signed INTEGER DEFAULT 0,
        sp_cert TEXT DEFAULT '',
        sp_key TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS tresore (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bezeichnung TEXT NOT NULL,
        hersteller TEXT,
        modell TEXT,
        seriennummer TEXT,
        land TEXT DEFAULT 'Deutschland',
        stadt TEXT,
        gebaeude TEXT,
        etage TEXT,
        raum TEXT,
        kaufdatum TEXT,
        kaufpreis REAL DEFAULT 0,
        wartungskosten_jaehrlich REAL DEFAULT 0,
        letzter_wartungstermin TEXT,
        naechster_wartungstermin TEXT,
        wartungsvertrag_doc BLOB,
        wartungsvertrag_doc_type TEXT,
        wartungsvertrag_doc_name TEXT,
        notizen TEXT,
        erstellt TEXT DEFAULT CURRENT_TIMESTAMP,
        geaendert TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS rechnungen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nr TEXT NOT NULL,
        kunden_id INTEGER,
        firma TEXT,
        kunden_nr TEXT,
        dat TEXT,
        zr TEXT,
        netto TEXT,
        html TEXT,
        ts INTEGER,
        erstellt TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS mahnungen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rechnung_nr TEXT NOT NULL,
        dat TEXT,
        html TEXT,
        ts INTEGER,
        erstellt TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP,
        benutzer TEXT NOT NULL,
        aktion TEXT NOT NULL,
        tabelle TEXT,
        datensatz_id INTEGER,
        details TEXT
    );
    CREATE TABLE IF NOT EXISTS smtp_settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        host TEXT DEFAULT '',
        port INTEGER DEFAULT 587,
        username TEXT DEFAULT '',
        password TEXT DEFAULT '',
        from_email TEXT DEFAULT '',
        from_name TEXT DEFAULT 'DT-Verwaltung',
        use_tls INTEGER DEFAULT 1,
        aktiv INTEGER DEFAULT 0
    );
    """)
    # Default roles
    for name, farbe, perms in [
        ('Admin',  'bg', '{"read":true,"write":true,"delete":true,"editTemplate":true,"manageUsers":true}'),
        ('User',   'bi', '{"read":true,"write":true,"delete":false,"editTemplate":false,"manageUsers":false}'),
        ('Viewer', 'ba', '{"read":true,"write":false,"delete":false,"editTemplate":false,"manageUsers":false}'),
    ]:
        db.execute("INSERT OR IGNORE INTO rollen(name,farbe,berechtigungen) VALUES(?,?,?)", (name, farbe, perms))
    # Migrate old "Benutzer" -> "User" safely
    try:
        db.execute("UPDATE rollen SET name='User' WHERE name='Benutzer' AND NOT EXISTS (SELECT 1 FROM rollen WHERE name='User')")
        db.execute("DELETE FROM rollen WHERE name='Benutzer'")
    except Exception:
        db.execute("DELETE FROM rollen WHERE name='Benutzer'")
        pass
    # Default admin – password from Docker secret file or env var (PBKDF2-hashed)
    _pw_file = os.environ.get('ADMIN_PASSWORD_FILE', '')
    if _pw_file and os.path.exists(_pw_file):
        with open(_pw_file) as _f:
            admin_pass = _f.read().strip()
    else:
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
    admin_hash = hash_pw(admin_pass)
    db.execute("INSERT OR IGNORE INTO benutzer(username,name,password_hash,rollen_id) VALUES('admin','Administrator',?,1)", (admin_hash,))
    # If ADMIN_PASSWORD is explicitly configured, always sync it to the DB so a redeploy resets the password
    if os.environ.get('ADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD_FILE'):
        db.execute("UPDATE benutzer SET password_hash=? WHERE username='admin'", (admin_hash,))
        print(f"[AUTH] Admin password synced from ADMIN_PASSWORD env var")
    # One-time admin password reset via RESET_ADMIN_PASSWORD env var
    _reset_pw = os.environ.get('RESET_ADMIN_PASSWORD', '').strip()
    if _reset_pw:
        db.execute("UPDATE benutzer SET password_hash=? WHERE username='admin'", (hash_pw(_reset_pw),))
        print(f"[AUTH] Admin password reset via RESET_ADMIN_PASSWORD env var")
    # Migration: add eingang_doc columns if missing
    for col, typ in [('eingang_doc','BLOB'),('eingang_doc_type','TEXT'),('eingang_doc_name','TEXT')]:
        try:
            db.execute(f"ALTER TABLE datentraeger ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Migration: add eingang_json to template_settings if missing
    try:
        db.execute("ALTER TABLE template_settings ADD COLUMN eingang_json TEXT DEFAULT '{}'")
    except Exception:
        pass
    # Migration: add vertrag_json to template_settings if missing
    try:
        db.execute("ALTER TABLE template_settings ADD COLUMN vertrag_json TEXT DEFAULT '{}'")
    except Exception:
        pass
    # Migration: add mengenrabatt_json to kunden if missing
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN mengenrabatt_json TEXT DEFAULT '[]'")
    except Exception:
        pass
    # Migration: add anrede to kunden if missing
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN anrede TEXT DEFAULT ''")
    except Exception:
        pass
    # Migration: add support contact fields to template_settings
    for col, typ, default in [
        ('support_name', 'TEXT', "'Support'"),
        ('support_email', 'TEXT', "''"),
    ]:
        try:
            db.execute(f"ALTER TABLE template_settings ADD COLUMN {col} {typ} DEFAULT {default}")
        except Exception:
            pass
    # Migration: add tresor_id to datentraeger if missing
    try:
        db.execute("ALTER TABLE datentraeger ADD COLUMN tresor_id INTEGER REFERENCES tresore(id) ON DELETE SET NULL")
    except Exception:
        pass
    # Migration: add weiter_im_bestand to uebergaben
    try:
        db.execute("ALTER TABLE uebergaben ADD COLUMN weiter_im_bestand INTEGER DEFAULT 0")
    except Exception:
        pass
    # Migration: add interne_nr to datentraeger
    try:
        db.execute("ALTER TABLE datentraeger ADD COLUMN interne_nr TEXT DEFAULT ''")
    except Exception:
        pass
    # Migration: add rechnungsempfaenger_id/eigentuemer_id to kunden
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN rechnungsempfaenger_id INTEGER")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN eigentuemer_id INTEGER")
    except Exception:
        pass
    # Migration: add 3-party ownership fields to datentraeger
    try:
        db.execute("ALTER TABLE datentraeger ADD COLUMN eigentuemer_id INTEGER")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE datentraeger ADD COLUMN neben_eigentuemer_id INTEGER")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE datentraeger ADD COLUMN rechnungsempfaenger_id INTEGER")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN szenario TEXT DEFAULT 'A'")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN escrow_haupt_id INTEGER")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN escrow_neben_id INTEGER")
    except Exception:
        pass
    # Migration: add max_mahnungen + mahngebuehr to kunden
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN max_mahnungen INTEGER DEFAULT 3")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE kunden ADD COLUMN mahngebuehr REAL DEFAULT 5.00")
    except Exception:
        pass
    # Migration: add bezahlt_am to rechnungen
    try:
        db.execute("ALTER TABLE rechnungen ADD COLUMN bezahlt_am TEXT")
    except Exception:
        pass
    # Migration: add TOTP columns to benutzer
    for col, typ in [('totp_secret','TEXT'), ('totp_enabled','INTEGER DEFAULT 0')]:
        try:
            db.execute(f"ALTER TABLE benutzer ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Migration: add Wartungsintervall to datentraeger
    for col, typ in [('wartungsintervall_jahre','INTEGER DEFAULT 0'), ('letzter_check_datum','TEXT')]:
        try:
            db.execute(f"ALTER TABLE datentraeger ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Migration: termin_wartungsfirma Feld in tresore
    try:
        db.execute("ALTER TABLE tresore ADD COLUMN termin_wartungsfirma TEXT")
    except Exception:
        pass
    # Migration: tresor_wartungen Historie-Tabelle
    db.execute("""
        CREATE TABLE IF NOT EXISTS tresor_wartungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tresor_id INTEGER NOT NULL REFERENCES tresore(id) ON DELETE CASCADE,
            datum TEXT NOT NULL,
            notizen TEXT,
            protokoll_doc BLOB,
            protokoll_doc_type TEXT,
            protokoll_doc_name TEXT,
            erstellt TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: foto columns on datentraeger
    for col, typ in [('foto_data','BLOB'),('foto_type','TEXT')]:
        try:
            db.execute(f"ALTER TABLE datentraeger ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Migration: dt_notizen table
    db.execute("""
        CREATE TABLE IF NOT EXISTS dt_notizen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datentraeger_id INTEGER NOT NULL REFERENCES datentraeger(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            benutzer TEXT NOT NULL,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: dt_wartungen table (pro-DT Wartungsprotokoll-History)
    db.execute("""
        CREATE TABLE IF NOT EXISTS dt_wartungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datentraeger_id INTEGER NOT NULL REFERENCES datentraeger(id) ON DELETE CASCADE,
            datum TEXT NOT NULL,
            notizen TEXT,
            benutzer TEXT NOT NULL,
            erstellt TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: fix umlaut encoding in uebergaben.grund (pre-i18n data)
    try:
        db.execute("UPDATE uebergaben SET grund='Rückgabe auf Wunsch' WHERE grund='Rueckgabe auf Wunsch'")
        db.execute("UPDATE uebergaben SET grund='Vertragsende' WHERE grund='Vertragsende'")
        db.execute("UPDATE uebergaben SET grund='Vernichtung beauftragt' WHERE grund='Vernichtung beauftragt'")
    except Exception:
        pass
    # Migration: notif_settings – Automatik-Tab configuration
    db.execute("""
        CREATE TABLE IF NOT EXISTS notif_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            auto_mahnung_aktiv INTEGER DEFAULT 0,
            auto_mahnung_tage INTEGER DEFAULT 14,
            wartung_warnung_aktiv INTEGER DEFAULT 0,
            wartung_warnung_tage INTEGER DEFAULT 30,
            weekly_digest_aktiv INTEGER DEFAULT 0,
            weekly_digest_wochentag INTEGER DEFAULT 1,
            weekly_digest_stunde INTEGER DEFAULT 8,
            weekly_digest_email TEXT DEFAULT ''
        )
    """)
    db.execute("INSERT OR IGNORE INTO notif_settings(id) VALUES(1)")
    # Migration: auto_notif_log – tracks what was already sent (prevents duplicate sends)
    db.execute("""
        CREATE TABLE IF NOT EXISTS auto_notif_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            typ TEXT NOT NULL,
            referenz_id INTEGER,
            referenz_key TEXT,
            gesendet_an TEXT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("INSERT OR IGNORE INTO smtp_settings(id) VALUES(1)")
    db.execute("INSERT OR IGNORE INTO template_settings(id) VALUES(1)")
    db.execute("INSERT OR IGNORE INTO saml_settings(id) VALUES(1)")
    db.commit()
    db.close()
    print(f"[DB] Initialized at {DB_PATH}")

# ─── SECURITY HEADERS ────────────────────────────────────────────────────────
@app.after_request
def add_security_headers(resp):
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'  # camera allowed for QR scanner
    # HSTS only meaningful over HTTPS – gunicorn hinter Reverse-Proxy
    resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # CSP: allow self + inline styles (needed for SPA) + cdnjs for QR-code lib
    resp.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    return resp

# ─── AUTH ─────────────────────────────────────────────────────────────────────
def hash_pw(pw):
    """Hash password with PBKDF2-HMAC-SHA256 + 32-byte random salt (600k iterations)."""
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 600_000)
    return 'pbkdf2:' + salt.hex() + ':' + key.hex()

def verify_pw(pw, stored):
    """Verify password. Supports new PBKDF2 format and legacy SHA-256 (auto-upgrades on login)."""
    if stored.startswith('pbkdf2:'):
        try:
            _, salt_hex, key_hex = stored.split(':', 2)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(key_hex)
            actual = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 600_000)
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
    # Legacy SHA-256
    return hmac.compare_digest(hashlib.sha256(pw.encode()).hexdigest(), stored)

_BLOB_MAX = 10 * 1024 * 1024  # 10 MB hard limit for all uploaded blobs

# Field length limits (characters) applied server-side on create/update
_FIELD_LIMITS = {
    'firma': 200, 'nr': 50, 'ansprechpartner': 200, 'email': 254,
    'tel': 50, 'mobil': 50, 'strasse': 200, 'plz': 20, 'ort': 200,
    'land': 100, 'sap_nr': 100, 'vertragsnr': 100,
    'bezeichnung': 200, 'serial': 200, 'interne_nr': 100,
    'beschreibung': 2000, 'notizen': 4000,
}

def _validate_lengths(data, limits=None):
    """Return an error string if any field in data exceeds its limit, else None."""
    for field, maxlen in (limits or _FIELD_LIMITS).items():
        val = data.get(field)
        if val and isinstance(val, str) and len(val) > maxlen:
            return f'Feld „{field}" zu lang (max. {maxlen} Zeichen)'
    return None

def _check_blob_size(b64_or_bytes, field_name='Datei', max_bytes=_BLOB_MAX):
    """Return an error string if the blob exceeds max_bytes, else None.

    Accepts both a base64 string (from JSON payloads) or raw bytes.
    For base64 strings, the decoded size is estimated as len(s) * 3 / 4
    to avoid decoding the whole payload just for the check.
    """
    if not b64_or_bytes:
        return None
    if isinstance(b64_or_bytes, (bytes, bytearray)):
        size = len(b64_or_bytes)
    else:
        # Rough upper-bound: base64 overhead is ~4/3
        size = int(len(b64_or_bytes) * 3 / 4)
    if size > max_bytes:
        mb = max_bytes // (1024 * 1024)
        return f'{field_name} zu groß (max. {mb} MB)'
    return None

def require_auth(perm=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = request.headers.get('X-Token', '')
            sess = session_get(token)
            if not sess or datetime.fromisoformat(sess['expires']) < datetime.now():
                return jsonify({'error': 'Nicht angemeldet'}), 401
            db = get_db()
            user = db.execute(
                "SELECT b.*,r.berechtigungen,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id WHERE b.id=? AND b.aktiv=1",
                (sess['user_id'],)
            ).fetchone()
            db.close()
            if not user:
                return jsonify({'error': 'Benutzer nicht gefunden'}), 401
            if perm:
                perms = json.loads(user['berechtigungen'])
                if not perms.get(perm):
                    return jsonify({'error': f'Keine Berechtigung: {perm}'}), 403
            request.user = dict(user)
            request.perms = json.loads(user['berechtigungen'])
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def _rate_limit(limit_str):
    """Conditional rate-limit decorator — no-op if flask-limiter not installed."""
    def decorator(f):
        if LIMITER_AVAILABLE:
            return limiter.limit(limit_str)(f)
        return f
    return decorator

@app.route('/api/login', methods=['POST'])
@_rate_limit("10 per minute; 30 per hour")
def login():
    clean_sessions()
    data = request.json or {}
    pw   = data.get('password', '')
    db   = get_db()
    user = db.execute(
        "SELECT b.*,r.berechtigungen,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id WHERE b.username=? AND b.aktiv=1",
        (data.get('username', ''),)
    ).fetchone()
    if not user or not verify_pw(pw, user['password_hash']):
        db.close()
        return jsonify({'error': 'Falscher Benutzername oder Passwort'}), 401
    user = dict(user)  # convert Row → dict so .get() works with pysqlcipher3
    # Check 2FA/TOTP if enabled
    if PYOTP_AVAILABLE and user.get('totp_enabled') and user.get('totp_secret'):
        totp_code = data.get('totp_code', '').strip()
        if not totp_code:
            db.close()
            return jsonify({'error': 'totp_required', 'totp_required': True}), 401
        totp = pyotp.TOTP(user['totp_secret'])
        if not totp.verify(totp_code, valid_window=1):
            db.close()
            return jsonify({'error': 'Ungültiger 2FA-Code'}), 401
    # Auto-upgrade legacy SHA-256 hash → PBKDF2 on successful login
    if not user['password_hash'].startswith('pbkdf2:'):
        db.execute("UPDATE benutzer SET password_hash=? WHERE id=?",
                   (hash_pw(pw), user['id']))
        db.commit()
    db.close()
    expires = (datetime.now() + timedelta(hours=8)).isoformat()
    token = session_create(user['id'], expires)
    return jsonify({'token': token, 'user': {
        'id': user['id'], 'username': user['username'], 'name': user['name'],
        'rollen_name': user['rollen_name'], 'farbe': user['farbe'],
        'perms': json.loads(user['berechtigungen']),
        'totp_enabled': bool(user.get('totp_enabled'))
    }})

@app.route('/api/logout', methods=['POST'])
def logout():
    session_delete(request.headers.get('X-Token', ''))
    return jsonify({'ok': True})

@app.route('/api/auth/refresh', methods=['POST'])
@_rate_limit('20 per minute')
def auth_refresh():
    """Extend an active session by another 8 hours."""
    token = request.headers.get('X-Token', '')
    sess = session_get(token)
    if not sess or datetime.fromisoformat(sess['expires']) < datetime.now():
        return jsonify({'error': 'Sitzung abgelaufen'}), 401
    new_expires = (datetime.now() + timedelta(hours=8)).isoformat()
    sess['expires'] = new_expires
    SESSIONS[token] = sess
    db = get_db()
    db.execute("UPDATE sessions SET expires=? WHERE token=?", (new_expires, token))
    db.commit()
    db.close()
    return jsonify({'ok': True, 'expires': new_expires})

@app.route('/api/emergency-pw-reset', methods=['POST'])
@_rate_limit("5 per hour")
def emergency_pw_reset():
    """Emergency admin password reset — only works if RESET_ADMIN_PASSWORD env var is set."""
    _reset_pw = os.environ.get('RESET_ADMIN_PASSWORD', '').strip()
    if not _reset_pw:
        return jsonify({'error': 'Not enabled'}), 403
    data = request.json or {}
    if data.get('token') != _reset_pw:
        return jsonify({'error': 'Invalid token'}), 403
    new_pw = data.get('password', '').strip()
    if not new_pw:
        return jsonify({'error': 'password required'}), 400
    if len(new_pw) < 8:
        return jsonify({'error': 'Passwort muss mindestens 8 Zeichen lang sein'}), 400
    db = get_db()
    db.execute("UPDATE benutzer SET password_hash=? WHERE username='admin'", (hash_pw(new_pw),))
    db.commit()
    db.close()
    print(f"[AUTH] Admin password reset via emergency endpoint")
    return jsonify({'ok': True})

@app.route('/api/me/password', methods=['PUT'])
@require_auth('read')
def change_own_password():
    data = request.json or {}
    password_alt = data.get('password_alt', '')
    password_neu = data.get('password', '')
    if not password_alt or not password_neu:
        return jsonify({'error': 'Altes und neues Passwort erforderlich'}), 400
    if len(password_neu) < 8:
        return jsonify({'error': 'Passwort muss mindestens 8 Zeichen lang sein'}), 400
    db = get_db()
    user = db.execute(
        "SELECT * FROM benutzer WHERE id=?",
        (request.user['id'],)
    ).fetchone()
    if not user or not verify_pw(password_alt, user['password_hash']):
        db.close()
        return jsonify({'error': 'Aktuelles Passwort ist falsch'}), 403
    db.execute("UPDATE benutzer SET password_hash=? WHERE id=?",
               (hash_pw(password_neu), request.user['id']))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ─── ROLLEN ──────────────────────────────────────────────────────────────────
@app.route('/api/rollen', methods=['GET'])
@require_auth('read')
def get_rollen():
    db = get_db()
    rows = db.execute("SELECT * FROM rollen ORDER BY id").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/rollen', methods=['POST'])
@require_auth('manageUsers')
def create_rolle():
    data = request.json or {}
    perms = data.get('berechtigungen', {"read": True, "write": False, "delete": False, "editTemplate": False, "manageUsers": False})
    db = get_db()
    db.execute("INSERT INTO rollen(name,farbe,berechtigungen) VALUES(?,?,?)",
               (data['name'], data.get('farbe', 'bg'), json.dumps(perms)))
    db.commit()
    rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = db.execute("SELECT * FROM rollen WHERE id=?", (rid,)).fetchone()
    db.close()
    return jsonify(dict(row)), 201

@app.route('/api/rollen/<int:rid>', methods=['PUT'])
@require_auth('manageUsers')
def update_rolle(rid):
    data = request.json or {}
    db = get_db()
    perms = data.get('berechtigungen', {})
    db.execute("UPDATE rollen SET name=?,farbe=?,berechtigungen=? WHERE id=?",
               (data['name'], data.get('farbe', 'bg'), json.dumps(perms), rid))
    db.commit()
    row = db.execute("SELECT * FROM rollen WHERE id=?", (rid,)).fetchone()
    db.close()
    return jsonify(dict(row))

@app.route('/api/rollen/<int:rid>/perms', methods=['PUT'])
@require_auth('manageUsers')
def update_rolle_perms(rid):
    data = request.json or {}
    db = get_db()
    db.execute("UPDATE rollen SET berechtigungen=? WHERE id=?", (json.dumps(data), rid))
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/rollen/<int:rid>', methods=['DELETE'])
@require_auth('manageUsers')
def delete_rolle(rid):
    if rid <= 3:
        return jsonify({'error': 'Standard-Rollen koennen nicht geloescht werden'}), 400
    db = get_db()
    db.execute("UPDATE benutzer SET rollen_id=3 WHERE rollen_id=?", (rid,))
    db.execute("DELETE FROM rollen WHERE id=?", (rid,))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ─── BENUTZER ─────────────────────────────────────────────────────────────────
@app.route('/api/benutzer', methods=['GET'])
@require_auth('manageUsers')
def get_benutzer():
    db = get_db()
    rows = db.execute(
        "SELECT b.id,b.username,b.name,b.rollen_id,b.aktiv,b.erstellt,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id ORDER BY b.id"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/benutzer', methods=['POST'])
@require_auth('manageUsers')
def create_benutzer():
    data = request.json or {}
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username und Passwort erforderlich'}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO benutzer(username,name,password_hash,rollen_id) VALUES(?,?,?,?)",
            (data['username'], data.get('name', data['username']), hash_pw(data['password']), data.get('rollen_id', 3))
        )
        db.commit()
        uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = db.execute(
            "SELECT b.*,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id WHERE b.id=?", (uid,)
        ).fetchone()
        db.close()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError:
        db.close()
        return jsonify({'error': 'Benutzername bereits vergeben'}), 400

@app.route('/api/benutzer/<int:uid>', methods=['PUT'])
@require_auth('manageUsers')
def update_benutzer(uid):
    data = request.json or {}
    db = get_db()
    if data.get('_only_password') and data.get('password'):
        db.execute("UPDATE benutzer SET password_hash=? WHERE id=?",
                   (hash_pw(data['password']), uid))
    elif data.get('_only_aktiv'):
        db.execute("UPDATE benutzer SET aktiv=? WHERE id=?",
                   (1 if data.get('aktiv') else 0, uid))
    elif data.get('password'):
        db.execute("UPDATE benutzer SET name=?,rollen_id=?,aktiv=?,password_hash=? WHERE id=?",
                   (data.get('name'), data.get('rollen_id', 3), data.get('aktiv', 1), hash_pw(data['password']), uid))
    else:
        db.execute("UPDATE benutzer SET name=?,rollen_id=?,aktiv=? WHERE id=?",
                   (data.get('name'), data.get('rollen_id', 3), int(data.get('aktiv', 1)), uid))
    db.commit()
    row = db.execute(
        "SELECT b.*,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id WHERE b.id=?", (uid,)
    ).fetchone()
    db.close()
    return jsonify(dict(row))

@app.route('/api/benutzer/<int:uid>', methods=['DELETE'])
@require_auth('manageUsers')
def delete_benutzer(uid):
    if uid == 1:
        return jsonify({'error': 'Admin kann nicht geloescht werden'}), 400
    db = get_db()
    db.execute("DELETE FROM benutzer WHERE id=?", (uid,))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ─── KUNDEN ──────────────────────────────────────────────────────────────────
@app.route('/api/kunden', methods=['GET'])
@require_auth('read')
def get_kunden():
    cached = _cache_get('kunden')
    if cached is not None:
        return jsonify(cached)
    db = get_db()
    rows = db.execute(
        "SELECT id,nr,firma,ansprechpartner,email,tel,mobil,strasse,plz,ort,land,sap_nr,vertragsnr,vertragsbeginn,vertragsende,vertragsstatus,vertragsnotiz,vertrag_doc_name,max_mahnungen,mahngebuehr FROM kunden ORDER BY firma"
    ).fetchall()
    db.close()
    result = [dict(r) for r in rows]
    _cache_set('kunden', result)
    return jsonify(result)

@app.route('/api/kunden', methods=['POST'])
@require_auth('write')
def create_kunde():
    data = request.json or {}
    if not data.get('firma') or not data.get('nr'):
        return jsonify({'error': 'Firma und Kundennummer erforderlich'}), 400
    err = _validate_lengths(data)
    if err:
        return jsonify({'error': err}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO kunden(nr,firma,anrede,ansprechpartner,email,tel,mobil,strasse,plz,ort,land,sap_nr,vertragsnr,vertragsbeginn,vertragsende,vertragsstatus,vertragsnotiz,mengenrabatt_json,szenario,escrow_haupt_id,escrow_neben_id,max_mahnungen,mahngebuehr) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data['nr'], data['firma'], data.get('anrede',''), data.get('ansprechpartner'), data.get('email'), data.get('tel'),
             data.get('mobil'), data.get('strasse'), data.get('plz'), data.get('ort'), data.get('land', 'Deutschland'),
             data.get('sap_nr'), data.get('vertragsnr'), data.get('vertragsbeginn'), data.get('vertragsende'),
             data.get('vertragsstatus', 'aktiv'), data.get('vertragsnotiz'), data.get('mengenrabatt_json', '[]'),
             data.get('szenario', 'A'), data.get('escrow_haupt_id') or None, data.get('escrow_neben_id') or None,
             int(data.get('max_mahnungen') or 3), float(data.get('mahngebuehr') or 5.00))
        )
        db.commit()
        kid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
        db.close()
        _cache_del('kunden')
        log_audit(request.user['username'], 'KUNDE_ERSTELLT', 'kunden', kid, data.get('firma'))
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError:
        db.close()
        return jsonify({'error': 'Kundennummer bereits vergeben'}), 400

@app.route('/api/kunden/<int:kid>', methods=['PUT'])
@require_auth('write')
def update_kunde(kid):
    data = request.json or {}
    err = _validate_lengths(data)
    if err:
        return jsonify({'error': err}), 400
    db = get_db()
    old = db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
    if old and old['vertragsnr'] and old['vertragsnr'] != data.get('vertragsnr') and data.get('vertragsnr'):
        db.execute(
            "INSERT INTO vertrags_history(kunden_id,datum,vertragsnr,status,notiz) VALUES(?,?,?,?,?)",
            (kid, datetime.now().strftime('%d.%m.%Y'), old['vertragsnr'],
             old['vertragsstatus'] or 'abgelaufen', old['vertragsnotiz'] or '')
        )
    db.execute(
        "UPDATE kunden SET nr=?,firma=?,anrede=?,ansprechpartner=?,email=?,tel=?,mobil=?,strasse=?,plz=?,ort=?,land=?,sap_nr=?,vertragsnr=?,vertragsbeginn=?,vertragsende=?,vertragsstatus=?,vertragsnotiz=?,mengenrabatt_json=?,szenario=?,escrow_haupt_id=?,escrow_neben_id=?,max_mahnungen=?,mahngebuehr=?,geaendert=CURRENT_TIMESTAMP WHERE id=?",
        (data['nr'], data['firma'], data.get('anrede',''), data.get('ansprechpartner'), data.get('email'), data.get('tel'),
         data.get('mobil'), data.get('strasse'), data.get('plz'), data.get('ort'), data.get('land', 'Deutschland'),
         data.get('sap_nr'), data.get('vertragsnr'), data.get('vertragsbeginn'), data.get('vertragsende'),
         data.get('vertragsstatus', 'aktiv'), data.get('vertragsnotiz'), data.get('mengenrabatt_json', '[]'),
         data.get('szenario', 'A'), data.get('escrow_haupt_id') or None, data.get('escrow_neben_id') or None,
         int(data.get('max_mahnungen') or 3), float(data.get('mahngebuehr') or 5.00), kid)
    )
    db.commit()
    row = db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
    db.close()
    _cache_del('kunden')
    log_audit(request.user['username'], 'KUNDE_GEAENDERT', 'kunden', kid, data.get('firma'))
    return jsonify(dict(row))

@app.route('/api/kunden/<int:kid>', methods=['DELETE'])
@require_auth('delete')
def delete_kunde(kid):
    db = get_db()
    row = db.execute("SELECT firma FROM kunden WHERE id=?", (kid,)).fetchone()
    db.execute("DELETE FROM kunden WHERE id=?", (kid,))
    db.commit()
    db.close()
    _cache_del('kunden')
    log_audit(request.user['username'], 'KUNDE_GELOESCHT', 'kunden', kid, row['firma'] if row else None)
    return jsonify({'ok': True})

@app.route('/api/kunden/<int:kid>/history', methods=['GET'])
@require_auth('read')
def get_vertrags_history(kid):
    db = get_db()
    rows = db.execute("SELECT * FROM vertrags_history WHERE kunden_id=? ORDER BY id DESC", (kid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/kunden/<int:kid>/vertrag_doc', methods=['GET'])
@require_auth('read')
def get_vertrag_doc(kid):
    db = get_db()
    row = db.execute("SELECT vertrag_doc,vertrag_doc_type FROM kunden WHERE id=?", (kid,)).fetchone()
    db.close()
    if not row or not row['vertrag_doc']:
        return jsonify({'error': 'Kein Dokument'}), 404
    return jsonify({'data': row['vertrag_doc'], 'type': row['vertrag_doc_type']})

@app.route('/api/kunden/<int:kid>/neuer_vertrag', methods=['POST'])
@require_auth('write')
def neuer_vertrag(kid):
    data = request.json or {}
    err = _check_blob_size(data.get('doc'), 'Vertragsdokument')
    if err:
        return jsonify({'error': err}), 413
    db = get_db()
    old = db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
    if old and old['vertragsnr']:
        db.execute(
            "INSERT INTO vertrags_history(kunden_id,datum,vertragsnr,status,notiz,doc,doc_type,doc_name) VALUES(?,?,?,?,?,?,?,?)",
            (kid, datetime.now().strftime('%d.%m.%Y'), old['vertragsnr'],
             old['vertragsstatus'] or 'abgelaufen', old['vertragsnotiz'] or '',
             old['vertrag_doc'], old['vertrag_doc_type'], old['vertrag_doc_name'])
        )
    db.execute(
        "UPDATE kunden SET vertragsnr=?,vertragsbeginn=?,vertragsende=?,vertragsstatus=?,vertragsnotiz=?,vertrag_doc=?,vertrag_doc_type=?,vertrag_doc_name=?,geaendert=CURRENT_TIMESTAMP WHERE id=?",
        (data.get('vertragsnr'), data.get('vertragsbeginn'), data.get('vertragsende'),
         data.get('vertragsstatus', 'aktiv'), data.get('vertragsnotiz', ''),
         data.get('doc'), data.get('doc_type'), data.get('doc_name'), kid)
    )
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ─── DATENTRÄGER ─────────────────────────────────────────────────────────────
@app.route('/api/datentraeger', methods=['GET'])
@require_auth('read')
def get_datentraeger():
    kunden_id = request.args.get('kunden_id')
    db = get_db()
    if kunden_id:
        rows = db.execute(
            "SELECT d.*,k.firma,k.nr as kunden_nr,e.firma as eigentuemer_firma,ne.firma as neben_eigentuemer_firma,re.firma as rechnungsempfaenger_firma,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN kunden e ON d.eigentuemer_id=e.id LEFT JOIN kunden ne ON d.neben_eigentuemer_id=ne.id LEFT JOIN kunden re ON d.rechnungsempfaenger_id=re.id LEFT JOIN tresore t ON d.tresor_id=t.id WHERE d.kunden_id=? ORDER BY d.id", (kunden_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT d.*,k.firma,k.nr as kunden_nr,e.firma as eigentuemer_firma,ne.firma as neben_eigentuemer_firma,re.firma as rechnungsempfaenger_firma,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN kunden e ON d.eigentuemer_id=e.id LEFT JOIN kunden ne ON d.neben_eigentuemer_id=ne.id LEFT JOIN kunden re ON d.rechnungsempfaenger_id=re.id LEFT JOIN tresore t ON d.tresor_id=t.id ORDER BY d.id"
        ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        d['hat_bild'] = bool(d.get('bild'))
        d['hat_eingang_doc'] = bool(d.get('eingang_doc'))
        d.pop('bild', None)
        d.pop('eingang_doc', None)
        result.append(d)
    return jsonify(result)

@app.route('/api/datentraeger/<int:did>/eingang_doc', methods=['GET'])
@require_auth('read')
def get_dt_eingang_doc(did):
    db = get_db()
    row = db.execute("SELECT eingang_doc,eingang_doc_type,eingang_doc_name FROM datentraeger WHERE id=?", (did,)).fetchone()
    db.close()
    if not row or not row['eingang_doc']:
        return jsonify({'error': 'Kein Dokument'}), 404
    return jsonify({'data': row['eingang_doc'], 'type': row['eingang_doc_type'], 'name': row['eingang_doc_name'] or 'Eingangsprotokoll'})

@app.route('/api/datentraeger/<int:did>/bild', methods=['GET'])
@require_auth('read')
def get_dt_bild(did):
    db = get_db()
    row = db.execute("SELECT bild,bild_type FROM datentraeger WHERE id=?", (did,)).fetchone()
    db.close()
    if not row or not row['bild']:
        return jsonify({'error': 'Kein Bild'}), 404
    return jsonify({'data': row['bild'], 'type': row['bild_type']})

@app.route('/api/datentraeger', methods=['POST'])
@require_auth('write')
def create_dt():
    data = request.json or {}
    err = _validate_lengths(data)
    if err:
        return jsonify({'error': err}), 400
    for field in ('bild', 'eingang_doc'):
        err = _check_blob_size(data.get(field), field)
        if err:
            return jsonify({'error': err}), 413
    db = get_db()
    db.execute(
        "INSERT INTO datentraeger(kunden_id,bezeichnung,serial,preis,einheit,preis_jahr,rabatt,einlagerungs_datum,beschreibung,bild,bild_type,eingang_doc,eingang_doc_type,eingang_doc_name,tresor_id,interne_nr,eigentuemer_id,neben_eigentuemer_id,rechnungsempfaenger_id,wartungsintervall_jahre,letzter_check_datum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (data['kunden_id'], data['bezeichnung'], data['serial'], data.get('preis', 0), data.get('einheit', 'monat'),
         data.get('preis_jahr', 0), data.get('rabatt', 0), data['einlagerungs_datum'],
         data.get('beschreibung', ''), data.get('bild'), data.get('bild_type'),
         data.get('eingang_doc'), data.get('eingang_doc_type'), data.get('eingang_doc_name'),
         data.get('tresor_id') or None, data.get('interne_nr',''),
         data.get('eigentuemer_id') or None, data.get('neben_eigentuemer_id') or None, data.get('rechnungsempfaenger_id') or None,
         data.get('wartungsintervall_jahre') or 0, data.get('letzter_check_datum') or None)
    )
    db.commit()
    did = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = db.execute(
        "SELECT d.*,k.firma,k.nr as kunden_nr,e.firma as eigentuemer_firma,ne.firma as neben_eigentuemer_firma,re.firma as rechnungsempfaenger_firma,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN kunden e ON d.eigentuemer_id=e.id LEFT JOIN kunden ne ON d.neben_eigentuemer_id=ne.id LEFT JOIN kunden re ON d.rechnungsempfaenger_id=re.id LEFT JOIN tresore t ON d.tresor_id=t.id WHERE d.id=?", (did,)
    ).fetchone()
    db.close()
    d = dict(row)
    d['hat_bild'] = bool(data.get('bild'))
    d['hat_eingang_doc'] = bool(data.get('eingang_doc'))
    d.pop('bild', None)
    d.pop('eingang_doc', None)
    log_audit(request.user['username'], 'DT_ERSTELLT', 'datentraeger', did,
              f"{data.get('bezeichnung')} | SN:{data.get('serial')}")
    return jsonify(d), 201

@app.route('/api/datentraeger/<int:did>', methods=['PUT'])
@require_auth('write')
def update_dt(did):
    data = request.json or {}
    err = _validate_lengths(data)
    if err:
        return jsonify({'error': err}), 400
    for field in ('bild', 'eingang_doc'):
        err = _check_blob_size(data.get(field), field)
        if err:
            return jsonify({'error': err}), 413
    db = get_db()
    _wj = data.get('wartungsintervall_jahre') or 0
    _lcd = data.get('letzter_check_datum') or None
    # Dynamic SQL: always update scalar fields; conditionally include blob columns
    cols = [
        "kunden_id=?","bezeichnung=?","serial=?","preis=?","einheit=?",
        "preis_jahr=?","rabatt=?","einlagerungs_datum=?","beschreibung=?",
        "tresor_id=?","interne_nr=?","eigentuemer_id=?","neben_eigentuemer_id=?",
        "rechnungsempfaenger_id=?","wartungsintervall_jahre=?","letzter_check_datum=?"
    ]
    vals = [
        data['kunden_id'], data['bezeichnung'], data['serial'],
        data.get('preis',0), data.get('einheit','monat'),
        data.get('preis_jahr',0), data.get('rabatt',0), data['einlagerungs_datum'],
        data.get('beschreibung',''),
        data.get('tresor_id') or None, data.get('interne_nr',''),
        data.get('eigentuemer_id') or None, data.get('neben_eigentuemer_id') or None,
        data.get('rechnungsempfaenger_id') or None, _wj, _lcd
    ]
    if data.get('bild'):
        cols += ["bild=?","bild_type=?"]
        vals += [data['bild'], data.get('bild_type')]
    if data.get('eingang_doc'):
        cols += ["eingang_doc=?","eingang_doc_type=?","eingang_doc_name=?"]
        vals += [data['eingang_doc'], data.get('eingang_doc_type'), data.get('eingang_doc_name')]
    vals.append(did)
    db.execute(f"UPDATE datentraeger SET {','.join(cols)} WHERE id=?", vals)
    db.commit()
    row = db.execute(
        "SELECT d.*,k.firma,k.nr as kunden_nr,e.firma as eigentuemer_firma,ne.firma as neben_eigentuemer_firma,re.firma as rechnungsempfaenger_firma,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN kunden e ON d.eigentuemer_id=e.id LEFT JOIN kunden ne ON d.neben_eigentuemer_id=ne.id LEFT JOIN kunden re ON d.rechnungsempfaenger_id=re.id LEFT JOIN tresore t ON d.tresor_id=t.id WHERE d.id=?", (did,)
    ).fetchone()
    db.close()
    d = dict(row)
    d['hat_bild'] = bool(d.get('bild'))
    d.pop('bild', None)
    log_audit(request.user['username'], 'DT_GEAENDERT', 'datentraeger', did,
              f"{data.get('bezeichnung')} | SN:{data.get('serial')}")
    return jsonify(d)

@app.route('/api/datentraeger/<int:did>', methods=['DELETE'])
@require_auth('delete')
def delete_dt(did):
    db = get_db()
    row = db.execute("SELECT bezeichnung, serial FROM datentraeger WHERE id=?", (did,)).fetchone()
    db.execute("DELETE FROM datentraeger WHERE id=?", (did,))
    db.commit()
    db.close()
    log_audit(request.user['username'], 'DT_GELOESCHT', 'datentraeger', did,
              f"{row['bezeichnung']} | SN:{row['serial']}" if row else None)
    return jsonify({'ok': True})

# ─── ÜBERGABEN ───────────────────────────────────────────────────────────────
@app.route('/api/uebergaben', methods=['GET'])
@require_auth('read')
def get_uebergaben():
    db = get_db()
    rows = db.execute(
        "SELECT u.*,k.firma,k.nr as kunden_nr FROM uebergaben u JOIN kunden k ON u.kunden_id=k.id ORDER BY u.id DESC"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['hat_doc'] = bool(d.get('doc'))
        d['weiter_im_bestand'] = bool(d.get('weiter_im_bestand'))
        d.pop('doc', None)
        pos = db.execute("SELECT datentraeger_id FROM uebergabe_positionen WHERE uebergabe_id=?", (d['id'],)).fetchall()
        d['dt_ids'] = [p['datentraeger_id'] for p in pos]
        result.append(d)
    db.close()
    return jsonify(result)

@app.route('/api/uebergaben', methods=['POST'])
@require_auth('write')
def create_uebergabe():
    data = request.json or {}
    kunden_id = data.get('kunden_id')
    datum = data.get('datum', '')
    empfaenger = data.get('Empfänger', data.get('empfaenger', ''))
    grund = data.get('grund', '')
    dt_ids = sorted(data.get('dt_ids', []))
    db = get_db()
    # Duplikatschutz: prüfe ob eine identische offene Übergabe bereits existiert
    existing = db.execute(
        "SELECT id,protokoll_nr FROM uebergaben WHERE kunden_id=? AND datum=? AND abgeschlossen=0 ORDER BY id DESC LIMIT 1",
        (kunden_id, datum)
    ).fetchone()
    if existing:
        # Prüfe ob die DT-Liste identisch ist
        ex_dts = sorted([r['datentraeger_id'] for r in db.execute(
            "SELECT datentraeger_id FROM uebergabe_positionen WHERE uebergabe_id=?", (existing['id'],)).fetchall()])
        if ex_dts == dt_ids:
            db.close()
            return jsonify({'id': existing['id'], 'protokoll_nr': existing['protokoll_nr']}), 200
    pnr = f"UP-{datetime.now().strftime('%Y%m%d')}-{data.get('kunden_nr', '?')}"
    db.execute(
        "INSERT INTO uebergaben(kunden_id,datum,empfaenger,grund,protokoll_nr,abgeschlossen) VALUES(?,?,?,?,?,0)",
        (kunden_id, datum, empfaenger, grund, pnr)
    )
    db.commit()
    uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    for did in dt_ids:
        db.execute("INSERT INTO uebergabe_positionen(uebergabe_id,datentraeger_id) VALUES(?,?)", (uid, did))
    db.commit()
    db.close()
    log_audit(request.user['username'], 'UEBERGABE_ERSTELLT', 'uebergaben', uid,
              f"Nr:{pnr} | Kunde:{kunden_id} | DTs:{len(dt_ids)}")
    return jsonify({'id': uid, 'protokoll_nr': pnr}), 201

@app.route('/api/uebergaben/<int:uid>/abschliessen', methods=['POST'])
@require_auth('write')
def abschliesse_uebergabe(uid):
    data = request.json or {}
    weiter_im_bestand = 1 if data.get('weiter_im_bestand') else 0
    db = get_db()
    db.execute(
        "UPDATE uebergaben SET abgeschlossen=1,doc=?,doc_type=?,doc_name=?,weiter_im_bestand=? WHERE id=?",
        (data.get('doc'), data.get('doc_type'), data.get('doc_name'), weiter_im_bestand, uid)
    )
    if not weiter_im_bestand:
        pos = db.execute("SELECT datentraeger_id FROM uebergabe_positionen WHERE uebergabe_id=?", (uid,)).fetchall()
        for p in pos:
            db.execute("UPDATE datentraeger SET status='uebergeben' WHERE id=?", (p['datentraeger_id'],))
    db.commit()
    db.close()
    mode = 'weiter_im_bestand' if weiter_im_bestand else 'uebergeben'
    log_audit(request.user['username'], 'UEBERGABE_ABGESCHLOSSEN', 'uebergaben', uid, mode)
    return jsonify({'ok': True})

@app.route('/api/uebergaben/<int:uid>', methods=['DELETE'])
@require_auth('write')
def delete_uebergabe(uid):
    db = get_db()
    row = db.execute("SELECT id, protokoll_nr FROM uebergaben WHERE id=?", (uid,)).fetchone()
    if not row:
        db.close()
        return jsonify({'error': 'Nicht gefunden'}), 404
    db.execute("DELETE FROM uebergabe_positionen WHERE uebergabe_id=?", (uid,))
    db.execute("DELETE FROM uebergaben WHERE id=?", (uid,))
    db.commit()
    db.close()
    log_audit(request.user['username'], 'UEBERGABE_GELOESCHT', 'uebergaben', uid,
              row['protokoll_nr'] if row else None)
    return jsonify({'ok': True})



@app.route('/api/uebergaben/<int:uid>/doc', methods=['GET'])
@require_auth('read')
def get_uebergabe_doc(uid):
    db = get_db()
    row = db.execute("SELECT doc,doc_type FROM uebergaben WHERE id=?", (uid,)).fetchone()
    db.close()
    if not row or not row['doc']:
        return jsonify({'error': 'Kein Dokument'}), 404
    return jsonify({'data': row['doc'], 'type': row['doc_type']})

# ─── TEMPLATES ───────────────────────────────────────────────────────────────
@app.route('/api/templates', methods=['GET'])
@require_auth('read')
def get_templates():
    db = get_db()
    row = db.execute("SELECT rechnung_json,uebergabe_json,eingang_json,vertrag_json,akzentfarbe,logo_type,support_name,support_email FROM template_settings WHERE id=1").fetchone()
    db.close()
    d = dict(row)
    d['hat_logo'] = bool(row['logo_type'])
    return jsonify(d)

@app.route('/api/templates', methods=['PUT'])
@require_auth('editTemplate')
def update_templates():
    data = request.json or {}
    db = get_db()
    sn = data.get('support_name', 'Support')
    se = data.get('support_email', '')
    if data.get('logo'):
        db.execute(
            "UPDATE template_settings SET rechnung_json=?,uebergabe_json=?,eingang_json=?,vertrag_json=?,akzentfarbe=?,logo=?,logo_type=?,support_name=?,support_email=? WHERE id=1",
            (data.get('rechnung_json', '{}'), data.get('uebergabe_json', '{}'), data.get('eingang_json', '{}'),
             data.get('vertrag_json', '{}'), data.get('akzentfarbe', '#0065A4'), data.get('logo'), data.get('logo_type'), sn, se)
        )
    else:
        db.execute(
            "UPDATE template_settings SET rechnung_json=?,uebergabe_json=?,eingang_json=?,vertrag_json=?,akzentfarbe=?,support_name=?,support_email=? WHERE id=1",
            (data.get('rechnung_json', '{}'), data.get('uebergabe_json', '{}'), data.get('eingang_json', '{}'),
             data.get('vertrag_json', '{}'), data.get('akzentfarbe', '#0065A4'), sn, se)
        )
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/templates/logo', methods=['GET'])
@require_auth('read')
def get_logo():
    db = get_db()
    row = db.execute("SELECT logo,logo_type FROM template_settings WHERE id=1").fetchone()
    db.close()
    if not row or not row['logo']:
        return jsonify({'error': 'Kein Logo'}), 404
    return jsonify({'data': row['logo'], 'type': row['logo_type']})

@app.route('/api/datentraeger/export/csv', methods=['GET'])
@require_auth('read')
def export_datentraeger_csv():
    import csv, io
    db = get_db()
    rows = db.execute(
        "SELECT d.id,d.bezeichnung,d.serial,d.status,d.einlagerungs_datum,d.preis,d.einheit,d.preis_jahr,d.rabatt,d.beschreibung,"
        "k.nr as kunden_nr,k.firma,"
        "t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum "
        "FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN tresore t ON d.tresor_id=t.id ORDER BY k.firma,d.id"
    ).fetchall()
    db.close()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['ID','Bezeichnung','Seriennummer','Status','Einlagerungsdatum','Preis/Monat','Einheit','Preis/Jahr','Rabatt%','Beschreibung',
                     'Kundennummer','Firma',
                     'Tresor','Land','Stadt','Gebäude','Etage','Raum'])
    for r in rows:
        writer.writerow([r['id'],r['bezeichnung'],r['serial'],r['status'],r['einlagerungs_datum'],
                        r['preis'],r['einheit'],r['preis_jahr'],r['rabatt'],r['beschreibung'],
                        r['kunden_nr'],r['firma'],
                        r['tresor_bezeichnung'] or '',r['tresor_land'] or '',r['tresor_stadt'] or '',
                        r['tresor_gebaeude'] or '',r['tresor_etage'] or '',r['tresor_raum'] or ''])
    output.seek(0)
    from flask import Response
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=datentraeger_export.csv'}
    )

# ─── DB BACKUP ───────────────────────────────────────────────────────────────
def _sqlite_backup(dst_path):
    """Create a consistent SQLite online backup (WAL-safe) using the backup API."""
    import sqlite3 as _sqlite3
    src = _sqlite3.connect(DB_PATH)
    dst = _sqlite3.connect(dst_path)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()

@app.route('/api/db/export', methods=['GET'])
@require_auth('manageUsers')
def export_db():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    tmp = f'/tmp/dtv_export_{ts}.db'
    try:
        _sqlite_backup(tmp)
        return send_file(tmp, as_attachment=True,
                         download_name=f'dtv_backup_{ts}.db',
                         mimetype='application/octet-stream')
    except Exception as e:
        return jsonify({'error': f'Backup fehlgeschlagen: {e}'}), 500

# ─── SAML ────────────────────────────────────────────────────────────────────

# ─── SAML SETTINGS (DB-backed) ───────────────────────────────────────────────

def get_saml_settings_db():
    """Load SAML config from DB."""
    db = get_db()
    row = db.execute("SELECT * FROM saml_settings WHERE id=1").fetchone()
    db.close()
    return dict(row) if row else {}

@app.route('/api/saml_settings', methods=['GET'])
@require_auth('manageUsers')
def get_saml_settings():
    s = get_saml_settings_db()
    # Never send private key to frontend
    s.pop('sp_key', None)
    s['has_sp_key'] = bool(s.get('sp_cert'))
    return jsonify(s)

@app.route('/api/saml_settings', methods=['PUT'])
@require_auth('manageUsers')
def update_saml_settings():
    data = request.json or {}
    db = get_db()
    # Only update sp_cert/sp_key if provided
    if data.get('sp_key'):
        db.execute("""UPDATE saml_settings SET
            enabled=?,idp_name=?,sp_entity_id=?,sp_acs_url=?,
            idp_metadata_url=?,idp_metadata_xml=?,group_mapping=?,
            want_signed=?,sp_cert=?,sp_key=? WHERE id=1""",
            (1 if data.get('enabled') else 0,
             data.get('idp_name','Single Sign-On'),
             data.get('sp_entity_id',''), data.get('sp_acs_url',''),
             data.get('idp_metadata_url',''), data.get('idp_metadata_xml',''),
             data.get('group_mapping','{}'),
             1 if data.get('want_signed') else 0,
             data.get('sp_cert',''), data.get('sp_key','')))
    else:
        db.execute("""UPDATE saml_settings SET
            enabled=?,idp_name=?,sp_entity_id=?,sp_acs_url=?,
            idp_metadata_url=?,idp_metadata_xml=?,group_mapping=?,
            want_signed=? WHERE id=1""",
            (1 if data.get('enabled') else 0,
             data.get('idp_name','Single Sign-On'),
             data.get('sp_entity_id',''), data.get('sp_acs_url',''),
             data.get('idp_metadata_url',''), data.get('idp_metadata_xml',''),
             data.get('group_mapping','{}'),
             1 if data.get('want_signed') else 0))
    db.commit()
    db.close()
    # Reload SAML client cache and clean up temp files
    _saml_client_cache.clear()
    for files in _saml_tmp_registry.values():
        for f in files:
            try: os.unlink(f)
            except OSError: pass
    _saml_tmp_registry.clear()
    return jsonify({'ok': True})

@app.route('/api/saml_settings/test', methods=['POST'])
@require_auth('manageUsers')
def test_saml_settings():
    """Validate the current SAML config without saving."""
    s = get_saml_settings_db()
    issues = []
    if not s.get('sp_entity_id'):
        issues.append('SP Entity ID fehlt')
    if not s.get('sp_acs_url'):
        issues.append('ACS URL fehlt')
    if not s.get('idp_metadata_url') and not s.get('idp_metadata_xml'):
        issues.append('IdP Metadata fehlt (URL oder XML)')
    if issues:
        return jsonify({'ok': False, 'issues': issues})
    # Try to build SAML client
    try:
        build_saml_client_from_db(s)
        return jsonify({'ok': True, 'message': 'SAML-Konfiguration gueltig'})
    except Exception as e:
        return jsonify({'ok': False, 'issues': [str(e)]})

@app.route('/api/saml_settings/generate_cert', methods=['POST'])
@require_auth('manageUsers')
def generate_cert():
    """Generate a self-signed SP certificate."""
    try:
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            key_path  = os.path.join(tmp, 'sp.key')
            cert_path = os.path.join(tmp, 'sp.crt')
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
                '-keyout', key_path, '-out', cert_path,
                '-days', '3650', '-nodes',
                '-subj', '/CN=DTV-SP'
            ], check=True, capture_output=True)
            key  = open(key_path).read()
            cert = open(cert_path).read()
        db = get_db()
        db.execute("UPDATE saml_settings SET sp_cert=?,sp_key=? WHERE id=1", (cert, key))
        db.commit()
        db.close()
        _saml_client_cache.clear()
        for files in _saml_tmp_registry.values():
            for f in files:
                try: os.unlink(f)
                except OSError: pass
        _saml_tmp_registry.clear()
        return jsonify({'ok': True, 'cert': cert})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/me', methods=['GET'])
@require_auth('read')
def get_me():
    """Return current user's info including 2FA status. Used by SAML flow and frontend."""
    u = request.user
    token = request.headers.get('X-Token','')
    sess = session_get(token)
    totp_enabled = False
    if sess:
        db = get_db()
        row = db.execute("SELECT totp_enabled FROM benutzer WHERE id=?", (sess['user_id'],)).fetchone()
        db.close()
        if row:
            totp_enabled = bool(row['totp_enabled'])
    return jsonify({
        'id': u['id'], 'username': u['username'], 'name': u['name'],
        'rollen_name': u['rollen_name'], 'farbe': u['farbe'],
        'perms': request.perms, 'totp_enabled': totp_enabled
    })

@app.route('/api/saml/config', methods=['GET'])
def saml_config():
    """Tell frontend whether SAML is enabled (reads from DB)."""
    if not SAML_AVAILABLE:
        return jsonify({'enabled': False, 'idp_name': 'SSO', 'sp_entity_id': ''})
    s = get_saml_settings_db()
    return jsonify({
        'enabled': bool(s.get('enabled')) and SAML_AVAILABLE,
        'idp_name': s.get('idp_name', 'Single Sign-On'),
        'sp_entity_id': s.get('sp_entity_id', ''),
    })

@app.route('/api/saml/login', methods=['GET'])
def saml_login():
    """Redirect browser to IdP for authentication."""
    if not SAML_AVAILABLE:
        return jsonify({'error': 'pysaml2 nicht installiert'}), 400
    s = get_saml_settings_db()
    if not s.get('enabled'):
        return jsonify({'error': 'SAML nicht aktiviert'}), 400
    try:
        client = build_saml_client_from_db(s)
        req_id, info = client.prepare_for_authenticate()
        for key, value in dict(info['headers']).items():
            if key == 'Location':
                return redirect(value)
        raise Exception('No Location header')
    except Exception as e:
        app.logger.error(f'SAML login error: {e}')
        return jsonify({'error': f'SAML Login Fehler: {str(e)}'}), 500

@app.route('/api/saml/acs', methods=['POST'])
def saml_acs():
    """
    Assertion Consumer Service – IdP posts SAML response here.
    Creates/updates user in DB and issues a session token.
    Redirects to frontend with token in URL fragment.
    """
    if not SAML_AVAILABLE:
        return jsonify({'error': 'pysaml2 nicht installiert'}), 400
    s = get_saml_settings_db()
    if not s.get('enabled'):
        return jsonify({'error': 'SAML nicht aktiviert'}), 400

    saml_response = request.form.get('SAMLResponse', '')
    if not saml_response:
        return jsonify({'error': 'Kein SAMLResponse im Request'}), 400

    try:
        client = build_saml_client_from_db(s)
        user_info = process_saml_response_with_client(client, saml_response)
    except Exception as e:
        app.logger.error(f'SAML ACS error: {e}')
        return redirect(f'/?saml_error={str(e)[:100]}')

    email   = user_info['email']
    name    = user_info['name']
    groups  = user_info['groups']
    SAML_GROUP_MAPPING = s.get('group_mapping', '{}')

    db = get_db()

    # Check if user exists by email (stored in username field for SAML users)
    user = db.execute(
        "SELECT b.*,r.berechtigungen,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id WHERE b.username=? AND b.aktiv=1",
        (email,)
    ).fetchone()

    if user:
        # Update name and rolle from IdP groups if mapping configured
        new_rollen_id = map_groups_to_rolle(groups, db, SAML_GROUP_MAPPING)
        if new_rollen_id != user['rollen_id']:
            db.execute("UPDATE benutzer SET name=?,rollen_id=? WHERE id=?",
                       (name, new_rollen_id, user['id']))
            db.commit()
            # Reload
            user = db.execute(
                "SELECT b.*,r.berechtigungen,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id WHERE b.id=?",
                (user['id'],)
            ).fetchone()
    else:
        # Auto-provision new user from IdP
        rollen_id = map_groups_to_rolle(groups, db, SAML_GROUP_MAPPING)
        # Use a random unusable password (SAML users can't log in with password)
        fake_hash = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()
        try:
            db.execute(
                "INSERT INTO benutzer(username,name,password_hash,rollen_id) VALUES(?,?,?,?)",
                (email, name, fake_hash, rollen_id)
            )
            db.commit()
            uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            user = db.execute(
                "SELECT b.*,r.berechtigungen,r.name as rollen_name,r.farbe FROM benutzer b JOIN rollen r ON b.rollen_id=r.id WHERE b.id=?",
                (uid,)
            ).fetchone()
            app.logger.info(f'SAML: Auto-provisioned user {email} with rollen_id={rollen_id}')
        except Exception as e:
            db.close()
            app.logger.error(f'SAML user provisioning failed: {e}')
            return redirect(f'/?saml_error=Benutzer+konnte+nicht+erstellt+werden')

    db.close()

    # Issue session token
    expires = (datetime.now() + timedelta(hours=8)).isoformat()
    token = session_create(user['id'], expires)

    # Redirect to frontend via one-time code (avoids session token in URL/browser history)
    frontend_url = os.environ.get('SAML_FRONTEND_URL', '/')
    code = _saml_code_create(token)
    return redirect(f'{frontend_url}?saml_code={code}')

@app.route('/api/saml/exchange', methods=['POST'])
@_rate_limit("20 per minute")
def saml_exchange():
    """Exchange a single-use SAML code (30 s TTL) for a session token."""
    data = request.json or {}
    code = data.get('code', '')
    entry = _saml_codes.pop(code, None)
    if not entry or time.time() > entry['expires']:
        return jsonify({'error': 'Invalid or expired code'}), 403
    return jsonify({'token': entry['token']})

@app.route('/api/saml/metadata', methods=['GET'])
def saml_metadata():
    """Serve SP metadata XML for IdP registration."""
    if not SAML_AVAILABLE:
        return jsonify({'error': 'pysaml2 nicht installiert'}), 400
    s = get_saml_settings_db()
    if not s.get('sp_entity_id'):
        return jsonify({'error': 'SP Entity ID nicht konfiguriert'}), 400
    try:
        client = build_saml_client_from_db(s)
        from saml2.metadata import entity_descriptor
        from lxml import etree
        xml = etree.tostring(entity_descriptor(client.config),
                             pretty_print=True, xml_declaration=True, encoding='utf-8')
        from flask import Response
        return Response(xml, mimetype='application/xml')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/saml/init_cert', methods=['POST'])
@require_auth('manageUsers')
def saml_init_cert():
    """Generate self-signed SP cert (only needed for signed requests)."""
    data_dir = os.environ.get('DATA_DIR', '/data')
    key, cert = generate_self_signed_cert(data_dir)
    if key and cert:
        return jsonify({'ok': True, 'key': key, 'cert': cert})
    return jsonify({'error': 'Zertifikat-Erstellung fehlgeschlagen'}), 500

# ─── TRESORE ─────────────────────────────────────────────────────────────────
@app.route('/api/tresore', methods=['GET'])
@require_auth('read')
def get_tresore():
    db = get_db()
    rows = db.execute(
        "SELECT t.*, (SELECT COUNT(*) FROM datentraeger WHERE tresor_id=t.id AND status='eingelagert') as anzahl_dt FROM tresore t ORDER BY t.bezeichnung"
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        d['hat_wartungsvertrag'] = bool(d.get('wartungsvertrag_doc'))
        d.pop('wartungsvertrag_doc', None)
        result.append(d)
    return jsonify(result)

@app.route('/api/tresore', methods=['POST'])
@require_auth('write')
def create_tresor():
    data = request.json or {}
    if not data.get('bezeichnung'):
        return jsonify({'error': 'Bezeichnung erforderlich'}), 400
    db = get_db()
    db.execute(
        "INSERT INTO tresore(bezeichnung,hersteller,modell,seriennummer,land,stadt,gebaeude,etage,raum,kaufdatum,kaufpreis,wartungskosten_jaehrlich,letzter_wartungstermin,naechster_wartungstermin,termin_wartungsfirma,notizen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (data['bezeichnung'], data.get('hersteller'), data.get('modell'), data.get('seriennummer'),
         data.get('land', 'Deutschland'), data.get('stadt'), data.get('gebaeude'), data.get('etage'), data.get('raum'),
         data.get('kaufdatum'), data.get('kaufpreis', 0), data.get('wartungskosten_jaehrlich', 0),
         data.get('letzter_wartungstermin'), data.get('naechster_wartungstermin'), data.get('termin_wartungsfirma'), data.get('notizen'))
    )
    db.commit()
    tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = db.execute("SELECT * FROM tresore WHERE id=?", (tid,)).fetchone()
    db.close()
    d = dict(row)
    d['hat_wartungsvertrag'] = False
    d.pop('wartungsvertrag_doc', None)
    log_audit(request.user['username'], 'TRESOR_ERSTELLT', 'tresore', tid, data.get('bezeichnung'))
    return jsonify(d), 201

@app.route('/api/tresore/<int:tid>', methods=['GET'])
@require_auth('read')
def get_tresor(tid):
    db = get_db()
    row = db.execute("SELECT * FROM tresore WHERE id=?", (tid,)).fetchone()
    db.close()
    if not row:
        return jsonify({'error': 'Nicht gefunden'}), 404
    d = dict(row)
    d['hat_wartungsvertrag'] = bool(d.get('wartungsvertrag_doc'))
    d.pop('wartungsvertrag_doc', None)
    return jsonify(d)

@app.route('/api/tresore/<int:tid>', methods=['PUT'])
@require_auth('write')
def update_tresor(tid):
    data = request.json or {}
    err = _check_blob_size(data.get('wartungsvertrag_doc'), 'Wartungsvertrag')
    if err:
        return jsonify({'error': err}), 413
    db = get_db()
    if data.get('wartungsvertrag_doc'):
        db.execute(
            "UPDATE tresore SET bezeichnung=?,hersteller=?,modell=?,seriennummer=?,land=?,stadt=?,gebaeude=?,etage=?,raum=?,kaufdatum=?,kaufpreis=?,wartungskosten_jaehrlich=?,letzter_wartungstermin=?,naechster_wartungstermin=?,termin_wartungsfirma=?,notizen=?,wartungsvertrag_doc=?,wartungsvertrag_doc_type=?,wartungsvertrag_doc_name=?,geaendert=CURRENT_TIMESTAMP WHERE id=?",
            (data['bezeichnung'], data.get('hersteller'), data.get('modell'), data.get('seriennummer'),
             data.get('land', 'Deutschland'), data.get('stadt'), data.get('gebaeude'), data.get('etage'), data.get('raum'),
             data.get('kaufdatum'), data.get('kaufpreis', 0), data.get('wartungskosten_jaehrlich', 0),
             data.get('letzter_wartungstermin'), data.get('naechster_wartungstermin'), data.get('termin_wartungsfirma'), data.get('notizen'),
             data.get('wartungsvertrag_doc'), data.get('wartungsvertrag_doc_type'), data.get('wartungsvertrag_doc_name'), tid)
        )
    else:
        db.execute(
            "UPDATE tresore SET bezeichnung=?,hersteller=?,modell=?,seriennummer=?,land=?,stadt=?,gebaeude=?,etage=?,raum=?,kaufdatum=?,kaufpreis=?,wartungskosten_jaehrlich=?,letzter_wartungstermin=?,naechster_wartungstermin=?,termin_wartungsfirma=?,notizen=?,geaendert=CURRENT_TIMESTAMP WHERE id=?",
            (data['bezeichnung'], data.get('hersteller'), data.get('modell'), data.get('seriennummer'),
             data.get('land', 'Deutschland'), data.get('stadt'), data.get('gebaeude'), data.get('etage'), data.get('raum'),
             data.get('kaufdatum'), data.get('kaufpreis', 0), data.get('wartungskosten_jaehrlich', 0),
             data.get('letzter_wartungstermin'), data.get('naechster_wartungstermin'), data.get('termin_wartungsfirma'), data.get('notizen'), tid)
        )
    db.commit()
    row = db.execute("SELECT * FROM tresore WHERE id=?", (tid,)).fetchone()
    db.close()
    d = dict(row)
    d['hat_wartungsvertrag'] = bool(d.get('wartungsvertrag_doc'))
    d.pop('wartungsvertrag_doc', None)
    log_audit(request.user['username'], 'TRESOR_GEAENDERT', 'tresore', tid, data.get('bezeichnung'))
    return jsonify(d)

@app.route('/api/tresore/<int:tid>', methods=['DELETE'])
@require_auth('delete')
def delete_tresor(tid):
    db = get_db()
    row = db.execute("SELECT bezeichnung FROM tresore WHERE id=?", (tid,)).fetchone()
    # Unlink DTs from this tresor first
    db.execute("UPDATE datentraeger SET tresor_id=NULL WHERE tresor_id=?", (tid,))
    db.execute("DELETE FROM tresore WHERE id=?", (tid,))
    db.commit()
    db.close()
    log_audit(request.user['username'], 'TRESOR_GELOESCHT', 'tresore', tid,
              row['bezeichnung'] if row else None)
    return jsonify({'ok': True})

# ─── TRESOR WARTUNGS-HISTORIE ────────────────────────────────────────────────
@app.route('/api/tresore/<int:tid>/wartungen', methods=['GET'])
@require_auth('read')
def get_tresor_wartungen(tid):
    db = get_db()
    rows = db.execute(
        "SELECT id, tresor_id, datum, notizen, protokoll_doc_name, protokoll_doc_type, erstellt FROM tresor_wartungen WHERE tresor_id=? ORDER BY datum DESC",
        (tid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/tresore/<int:tid>/wartungen', methods=['POST'])
@require_auth('write')
def create_tresor_wartung(tid):
    data = request.json or {}
    if not data.get('datum'):
        return jsonify({'error': 'Datum erforderlich'}), 400
    db = get_db()
    doc = data.get('protokoll_doc')
    doc_type = data.get('protokoll_doc_type')
    doc_name = data.get('protokoll_doc_name')
    db.execute(
        "INSERT INTO tresor_wartungen(tresor_id,datum,notizen,protokoll_doc,protokoll_doc_type,protokoll_doc_name) VALUES(?,?,?,?,?,?)",
        (tid, data['datum'], data.get('notizen'), doc, doc_type, doc_name)
    )
    # Auto-update letzter_wartungstermin in tresore
    db.execute("UPDATE tresore SET letzter_wartungstermin=?,geaendert=CURRENT_TIMESTAMP WHERE id=?", (data['datum'], tid))
    # Auto-calculate next due date if interval is set
    tresor = db.execute("SELECT wartungsintervall_jahre FROM tresore WHERE id=?", (tid,)).fetchone() if False else None
    # (interval field not in tresore, skip auto-calc for now — done via frontend suggestion)
    db.commit()
    wid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = db.execute("SELECT id,tresor_id,datum,notizen,protokoll_doc_name,protokoll_doc_type,erstellt FROM tresor_wartungen WHERE id=?", (wid,)).fetchone()
    db.close()
    return jsonify(dict(row)), 201

@app.route('/api/tresore/<int:tid>/wartungen/<int:wid>', methods=['DELETE'])
@require_auth('delete')
def delete_tresor_wartung(tid, wid):
    db = get_db()
    db.execute("DELETE FROM tresor_wartungen WHERE id=? AND tresor_id=?", (wid, tid))
    db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/api/tresore/<int:tid>/wartungen/<int:wid>/protokoll', methods=['GET'])
@require_auth('read')
def get_tresor_wartung_protokoll(tid, wid):
    db = get_db()
    row = db.execute("SELECT protokoll_doc,protokoll_doc_type,protokoll_doc_name FROM tresor_wartungen WHERE id=? AND tresor_id=?", (wid, tid)).fetchone()
    db.close()
    if not row or not row['protokoll_doc']:
        return jsonify({'error': 'Kein Protokoll'}), 404
    return jsonify({'data': row['protokoll_doc'], 'type': row['protokoll_doc_type'], 'name': row['protokoll_doc_name'] or 'Wartungsprotokoll'})

@app.route('/api/tresore/<int:tid>/wartungsvertrag', methods=['GET'])
@require_auth('read')
def get_tresor_wartungsvertrag(tid):
    db = get_db()
    row = db.execute("SELECT wartungsvertrag_doc,wartungsvertrag_doc_type,wartungsvertrag_doc_name FROM tresore WHERE id=?", (tid,)).fetchone()
    db.close()
    if not row or not row['wartungsvertrag_doc']:
        return jsonify({'error': 'Kein Dokument'}), 404
    return jsonify({'data': row['wartungsvertrag_doc'], 'type': row['wartungsvertrag_doc_type'], 'name': row['wartungsvertrag_doc_name'] or 'Wartungsvertrag'})

@app.route('/api/tresore/wartungstermine', methods=['GET'])
@require_auth('read')
def get_wartungstermine():
    """Return tresore with upcoming or overdue maintenance appointments (within 60 days)."""
    from datetime import date, timedelta as td
    heute = date.today()
    grenze = (heute + td(days=60)).isoformat()
    db = get_db()
    rows = db.execute(
        "SELECT id, bezeichnung, naechster_wartungstermin, land, stadt, gebaeude, etage, raum FROM tresore WHERE naechster_wartungstermin IS NOT NULL AND naechster_wartungstermin != '' AND naechster_wartungstermin <= ? ORDER BY naechster_wartungstermin",
        (grenze,)
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            wt = date.fromisoformat(r['naechster_wartungstermin'])
            d['ueberfaellig'] = wt < heute
            d['tage_bis_wartung'] = (wt - heute).days
        except Exception:
            d['ueberfaellig'] = False
            d['tage_bis_wartung'] = None
        result.append(d)
    return jsonify(result)

# ─── HEALTH ──────────────────────────────────────────────────────────────────
# ─── RECHNUNGEN ──────────────────────────────────────────────────────────────
@app.route('/api/rechnungen', methods=['GET'])
@require_auth('read')
def get_rechnungen():
    cached = _cache_get('rechnungen')
    if cached is not None:
        return jsonify(cached)
    db = get_db()
    rows = db.execute(
        "SELECT id,nr,kunden_id,firma,kunden_nr,dat,zr,netto,ts,erstellt,bezahlt_am FROM rechnungen ORDER BY ts DESC"
    ).fetchall()
    db.close()
    result = [dict(r) for r in rows]
    _cache_set('rechnungen', result)
    return jsonify(result)

@app.route('/api/rechnungen', methods=['POST'])
@require_auth('write')
def post_rechnungen():
    data = request.json or {}
    db = get_db()
    # upsert by nr: preserve bezahlt_am if overwriting
    old = db.execute("SELECT bezahlt_am FROM rechnungen WHERE nr=?", (data.get('nr',''),)).fetchone()
    bezahlt_am = old['bezahlt_am'] if old else None
    db.execute("DELETE FROM rechnungen WHERE nr=?", (data.get('nr',''),))
    db.execute(
        "INSERT INTO rechnungen(nr,kunden_id,firma,kunden_nr,dat,zr,netto,html,ts,bezahlt_am) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (data.get('nr'), data.get('kunden_id'), data.get('firma'), data.get('kunden_nr'),
         data.get('dat'), data.get('zr'), data.get('netto'), data.get('html'), data.get('ts'), bezahlt_am)
    )
    db.commit()
    row = db.execute("SELECT id FROM rechnungen WHERE nr=?", (data.get('nr'),)).fetchone()
    db.close()
    _cache_del('rechnungen')
    log_audit(request.user['username'], 'RECHNUNG_ERSTELLT', 'rechnungen',
              row['id'] if row else None, f"Nr:{data.get('nr')} | {data.get('firma')}")
    return jsonify({'id': row['id'] if row else None}), 201

@app.route('/api/rechnungen/<int:rid>/bezahlt', methods=['PATCH'])
@require_auth('write')
def rechnung_bezahlt(rid):
    db = get_db()
    db.execute("UPDATE rechnungen SET bezahlt_am=? WHERE id=?",
               (datetime.now().strftime('%Y-%m-%d'), rid))
    db.commit()
    db.close()
    _cache_del('rechnungen')
    return jsonify({'ok': True})

@app.route('/api/rechnungen/<int:rid>/unbezahlt', methods=['PATCH'])
@require_auth('write')
def rechnung_unbezahlt(rid):
    db = get_db()
    db.execute("UPDATE rechnungen SET bezahlt_am=NULL WHERE id=?", (rid,))
    db.commit()
    db.close()
    _cache_del('rechnungen')
    return jsonify({'ok': True})

@app.route('/api/rechnungen/<int:rid>', methods=['DELETE'])
@require_auth('delete')
def delete_rechnung(rid):
    db = get_db()
    row = db.execute("SELECT nr, firma FROM rechnungen WHERE id=?", (rid,)).fetchone()
    db.execute("DELETE FROM rechnungen WHERE id=?", (rid,))
    db.commit()
    db.close()
    _cache_del('rechnungen')
    log_audit(request.user['username'], 'RECHNUNG_GELOESCHT', 'rechnungen', rid,
              f"Nr:{row['nr']} | {row['firma']}" if row else None)
    return jsonify({'ok': True})

@app.route('/api/rechnungen', methods=['DELETE'])
@require_auth('delete')
def delete_all_rechnungen():
    db = get_db()
    db.execute("DELETE FROM rechnungen")
    db.commit()
    db.close()
    _cache_del('rechnungen')
    return jsonify({'ok': True})

@app.route('/api/rechnungen/<int:rid>/email', methods=['POST'])
@require_auth('write')
def send_rechnung_email(rid):
    data = request.json or {}
    to_addr = data.get('to', '')
    if not to_addr:
        return jsonify({'error': 'Empfänger-E-Mail fehlt'}), 400
    db = get_db()
    row = db.execute("SELECT * FROM rechnungen WHERE id=?", (rid,)).fetchone()
    db.close()
    if not row:
        return jsonify({'error': 'Rechnung nicht gefunden'}), 404
    subject = data.get('subject') or f"Rechnung {row['nr']}"
    html_body = row['html'] or f'<p>Rechnung {row["nr"]}</p>'
    ok, err = _send_email(to_addr, subject, html_body)
    if ok:
        token = request.headers.get('X-Token', '')
        sess = session_get(token)
        uname = 'system'
        if sess:
            db2 = get_db()
            u = db2.execute("SELECT username FROM benutzer WHERE id=?", (sess['user_id'],)).fetchone()
            db2.close()
            if u: uname = u['username']
        log_audit(uname, 'EMAIL_RECHNUNG', 'rechnungen', rid, f'An: {to_addr}, Nr: {row["nr"]}')
        return jsonify({'ok': True})
    return jsonify({'error': err}), 500

# ─── MAHNUNGEN ───────────────────────────────────────────────────────────────
@app.route('/api/mahnungen/<rechnung_nr>', methods=['GET'])
@require_auth('read')
def get_mahnungen(rechnung_nr):
    db = get_db()
    rows = db.execute(
        "SELECT id,rechnung_nr,dat,ts FROM mahnungen WHERE rechnung_nr=? ORDER BY ts ASC",
        (rechnung_nr,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/mahnungen', methods=['POST'])
@require_auth('write')
def post_mahnung():
    data = request.json or {}
    db = get_db()
    db.execute(
        "INSERT INTO mahnungen(rechnung_nr,dat,html,ts) VALUES(?,?,?,?)",
        (data.get('rechnung_nr'), data.get('dat'), data.get('html'), data.get('ts'))
    )
    db.commit()
    return jsonify({'ok': True}), 201

@app.route('/api/mahnungen/<int:mid>', methods=['DELETE'])
@require_auth('delete')
def delete_mahnung(mid):
    db = get_db()
    db.execute("DELETE FROM mahnungen WHERE id=?", (mid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/mahnungen_by_id/<int:mid>', methods=['GET'])
@require_auth('read')
def get_mahnung_by_id(mid):
    db = get_db()
    row = db.execute("SELECT id,rechnung_nr,dat,html,ts FROM mahnungen WHERE id=?", (mid,)).fetchone()
    if not row:
        return jsonify({'error': 'Nicht gefunden'}), 404
    return jsonify(dict(row))

# ─── RE-NUMMER ────────────────────────────────────────────────────────────────
@app.route('/api/re_nr', methods=['GET'])
@require_auth('read')
def get_re_nr():
    db = get_db()
    # Latest nr in current year
    import datetime
    yr = datetime.date.today().year
    row = db.execute(
        "SELECT nr FROM rechnungen WHERE nr LIKE ? ORDER BY ts DESC LIMIT 1",
        (f'RE-{yr}-%',)
    ).fetchone()
    if row:
        return jsonify({'nr': row['nr']})
    return jsonify({'nr': None})

# ─── AUDIT LOG ───────────────────────────────────────────────────────────────
def log_audit(user_name, aktion, tabelle=None, datensatz_id=None, details=None):
    try:
        db = get_db()
        db.execute(
            "INSERT INTO audit_log(benutzer,aktion,tabelle,datensatz_id,details) VALUES(?,?,?,?,?)",
            (user_name, aktion, tabelle, datensatz_id, details)
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[AUDIT] Error: {e}")

@app.route('/api/audit_log', methods=['GET'])
@require_auth('manageUsers')
def get_audit_log():
    try:
        limit = min(int(request.args.get('limit', 200)), 500)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (ValueError, TypeError):
        return jsonify({'error': 'Ungültige Parameter'}), 400
    db = get_db()
    rows = db.execute(
        "SELECT id,ts,benutzer,aktion,tabelle,datensatz_id,details FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    total = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    db.close()
    return jsonify({'items': [dict(r) for r in rows], 'total': total})

# ─── SMTP SETTINGS ───────────────────────────────────────────────────────────
@app.route('/api/smtp_settings', methods=['GET'])
@require_auth('manageUsers')
def get_smtp_settings():
    db = get_db()
    row = db.execute("SELECT id,host,port,username,from_email,from_name,use_tls,aktiv FROM smtp_settings WHERE id=1").fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@app.route('/api/smtp_settings', methods=['PUT'])
@require_auth('manageUsers')
def update_smtp_settings():
    data = request.json or {}
    try:
        port = int(data.get('port', 587))
        if not (1 <= port <= 65535):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({'error': 'Ungültiger SMTP-Port (1–65535)'}), 400
    db = get_db()
    # Store password only if provided (not empty) – encrypt before storing
    if data.get('password'):
        db.execute(
            "UPDATE smtp_settings SET host=?,port=?,username=?,password=?,from_email=?,from_name=?,use_tls=?,aktiv=? WHERE id=1",
            (data.get('host',''), port, data.get('username',''),
             _encrypt_smtp_pw(data.get('password','')), data.get('from_email',''), data.get('from_name','DT-Verwaltung'),
             1 if data.get('use_tls') else 0, 1 if data.get('aktiv') else 0)
        )
    else:
        db.execute(
            "UPDATE smtp_settings SET host=?,port=?,username=?,from_email=?,from_name=?,use_tls=?,aktiv=? WHERE id=1",
            (data.get('host',''), port, data.get('username',''),
             data.get('from_email',''), data.get('from_name','DT-Verwaltung'),
             1 if data.get('use_tls') else 0, 1 if data.get('aktiv') else 0)
        )
    db.commit()
    db.close()
    return jsonify({'ok': True})

def _sanitize_header(val):
    """Strip newlines to prevent e-mail header injection."""
    return str(val or '').replace('\r', '').replace('\n', '').strip()

def _send_email(to_addr, subject, html_body):
    """Send an email using the configured SMTP settings. Returns (ok, error_msg)."""
    # Guard against header injection
    to_addr = _sanitize_header(to_addr)
    subject = _sanitize_header(subject)
    # Basic format check – must contain @ and no spaces
    if not to_addr or '@' not in to_addr or ' ' in to_addr:
        return False, 'Ungültige E-Mail-Adresse'
    db = get_db()
    cfg = db.execute("SELECT * FROM smtp_settings WHERE id=1").fetchone()
    db.close()
    if not cfg or not cfg['aktiv'] or not cfg['host']:
        return False, 'SMTP nicht konfiguriert oder deaktiviert'
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg['To'] = to_addr
        # Plain-text fallback for mail clients that don't render HTML
        import re as _re
        plain_body = _re.sub(r'<[^>]+>', '', html_body).strip()
        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        if cfg['use_tls']:
            server = smtplib.SMTP(cfg['host'], cfg['port'], timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(cfg['host'], cfg['port'], timeout=10)
        if cfg['username'] and cfg['password']:
            server.login(cfg['username'], _decrypt_smtp_pw(cfg['password']))
        server.sendmail(cfg['from_email'], [to_addr], msg.as_string())
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

@app.route('/api/smtp/test', methods=['POST'])
@require_auth('manageUsers')
def smtp_test():
    data = request.json or {}
    to_addr = data.get('to', '')
    if not to_addr:
        return jsonify({'error': 'Empfänger fehlt'}), 400
    ok, err = _send_email(to_addr, 'DT-Verwaltung SMTP Test', '<p>SMTP-Test erfolgreich! DT-Verwaltung kann E-Mails senden.</p>')
    if ok:
        return jsonify({'ok': True})
    return jsonify({'error': err}), 500

@app.route('/api/mahnungen/<int:mid>/email', methods=['POST'])
@require_auth('write')
def send_mahnung_email(mid):
    data = request.json or {}
    to_addr = data.get('to', '')
    if not to_addr:
        return jsonify({'error': 'Empfänger-E-Mail fehlt'}), 400
    db = get_db()
    row = db.execute("SELECT * FROM mahnungen WHERE id=?", (mid,)).fetchone()
    db.close()
    if not row:
        return jsonify({'error': 'Mahnung nicht gefunden'}), 404
    subject = f"Mahnung {row['rechnung_nr']}"
    ok, err = _send_email(to_addr, subject, row['html'] or '<p>Mahnung</p>')
    if ok:
        token = request.headers.get('X-Token','')
        sess = session_get(token)
        uname = 'system'
        if sess:
            db2 = get_db()
            u = db2.execute("SELECT username FROM benutzer WHERE id=?", (sess['user_id'],)).fetchone()
            db2.close()
            if u: uname = u['username']
        log_audit(uname, 'EMAIL_MAHNUNG', 'mahnungen', mid, f'An: {to_addr}, Rechnung: {row["rechnung_nr"]}')
        return jsonify({'ok': True})
    return jsonify({'error': err}), 500

# ─── 2FA / TOTP ──────────────────────────────────────────────────────────────
@app.route('/api/me/totp/setup', methods=['POST'])
@require_auth()
def totp_setup():
    if not PYOTP_AVAILABLE:
        return jsonify({'error': '2FA nicht verfügbar (pyotp fehlt)'}), 503
    data = request.json or {}
    current_pw = data.get('current_password', '')
    token = request.headers.get('X-Token','')
    sess = session_get(token)
    db = get_db()
    user = db.execute("SELECT id,username,totp_secret,totp_enabled,password_hash FROM benutzer WHERE id=?", (sess['user_id'],)).fetchone()
    if not user or not verify_pw(current_pw, user['password_hash']):
        db.close()
        return jsonify({'error': 'Aktuelles Passwort ist falsch'}), 403
    # Generate new secret
    secret = pyotp.random_base32()
    db.execute("UPDATE benutzer SET totp_secret=? WHERE id=?", (secret, user['id']))
    db.commit()
    db.close()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user['username'], issuer_name='DT-Verwaltung')
    return jsonify({'secret': secret, 'uri': uri})

@app.route('/api/me/totp/enable', methods=['POST'])
@require_auth()
def totp_enable():
    if not PYOTP_AVAILABLE:
        return jsonify({'error': '2FA nicht verfügbar'}), 503
    data = request.json or {}
    code = data.get('code','').strip()
    token = request.headers.get('X-Token','')
    sess = session_get(token)
    db = get_db()
    user = db.execute("SELECT id,username,totp_secret FROM benutzer WHERE id=?", (sess['user_id'],)).fetchone()
    if not user or not user['totp_secret']:
        db.close()
        return jsonify({'error': 'Kein TOTP-Secret gesetzt – erst /setup aufrufen'}), 400
    totp = pyotp.TOTP(user['totp_secret'])
    if not totp.verify(code, valid_window=1):
        db.close()
        return jsonify({'error': 'Falscher Code'}), 400
    db.execute("UPDATE benutzer SET totp_enabled=1 WHERE id=?", (user['id'],))
    db.commit()
    db.close()
    log_audit(user['username'], '2FA_AKTIVIERT', 'benutzer', user['id'])
    return jsonify({'ok': True})

@app.route('/api/me/totp', methods=['DELETE'])
@require_auth()
def totp_disable():
    data = request.json or {}
    current_pw = data.get('current_password', '')
    token = request.headers.get('X-Token','')
    sess = session_get(token)
    db = get_db()
    user = db.execute("SELECT id,username,password_hash,totp_secret,totp_enabled FROM benutzer WHERE id=?", (sess['user_id'],)).fetchone()
    if not user or not verify_pw(current_pw, user['password_hash']):
        db.close()
        return jsonify({'error': 'Aktuelles Passwort ist falsch'}), 403
    db.execute("UPDATE benutzer SET totp_enabled=0, totp_secret=NULL WHERE id=?", (sess['user_id'],))
    db.commit()
    db.close()
    log_audit(user['username'], '2FA_DEAKTIVIERT', 'benutzer', sess['user_id'])
    return jsonify({'ok': True})


# ─── DASHBOARD CHART ─────────────────────────────────────────────────────────
@app.route('/api/dashboard/umsatz_monat', methods=['GET'])
@require_auth('read')
def dashboard_umsatz_monat():
    """Return monthly invoiced amounts for the last 12 months."""
    db = get_db()
    rows = db.execute(
        "SELECT dat, netto FROM rechnungen WHERE dat IS NOT NULL ORDER BY ts DESC LIMIT 500"
    ).fetchall()
    db.close()
    from collections import defaultdict
    buckets = defaultdict(float)
    for r in rows:
        try:
            # dat format: DD.MM.YYYY
            parts = r['dat'].split('.')
            if len(parts) == 3:
                key = f"{parts[2]}-{parts[1]}"
                val = float(str(r['netto'] or '0').replace(',', '.').replace('€', '').strip())
                buckets[key] += val
        except Exception:
            pass
    # Return last 12 months sorted
    from datetime import date
    today = date.today()
    result = []
    for i in range(11, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y}-{m:02d}"
        result.append({'monat': key, 'netto': round(buckets.get(key, 0), 2)})
    return jsonify(result)

# ─── DT WARTUNG (fällige Check-Termine) ──────────────────────────────────────
@app.route('/api/datentraeger/wartung_faellig', methods=['GET'])
@require_auth('read')
def dt_wartung_faellig():
    """Return DTs whose scheduled media check is due within 60 days or overdue."""
    db = get_db()
    rows = db.execute(
        "SELECT d.id,d.bezeichnung,d.serial,d.interne_nr,d.letzter_check_datum,d.wartungsintervall_jahre,k.firma FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id WHERE d.wartungsintervall_jahre>0 AND d.status='eingelagert'"
    ).fetchall()
    db.close()
    today = datetime.today().date()
    result = []
    for r in rows:
        d = dict(r)
        if d['letzter_check_datum']:
            try:
                last = datetime.strptime(d['letzter_check_datum'], '%Y-%m-%d').date()
            except Exception:
                continue
            naechster = last.replace(year=last.year + d['wartungsintervall_jahre'])
        else:
            # Never checked — use einlagerung as fallback (not available here, skip)
            continue
        delta = (naechster - today).days
        if delta <= 60:
            d['naechster_check'] = naechster.isoformat()
            d['tage_bis_check'] = delta
            d['ueberfaellig'] = delta < 0
            result.append(d)
    result.sort(key=lambda x: x['tage_bis_check'])
    return jsonify(result)

@app.route('/api/ping', methods=['GET'])
def ping():
    """Unauthenticated liveness check – used by Docker HEALTHCHECK."""
    return jsonify({'ok': True})

@app.route('/api/health', methods=['GET'])
@require_auth('read')
def health():
    return jsonify({'status': 'ok'})

# ─── PHASE 1: DB-BACKUP ──────────────────────────────────────────────────────
@app.route('/api/admin/backup', methods=['GET'])
@require_auth('manageUsers')
def admin_backup():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    tmp = f'/tmp/dtv_backup_{ts}.db'
    try:
        _sqlite_backup(tmp)
        return send_file(tmp, as_attachment=True,
                         download_name=f'dtv_backup_{ts}.db',
                         mimetype='application/octet-stream')
    except Exception as e:
        return jsonify({'error': f'Backup fehlgeschlagen: {e}'}), 500

# ─── PHASE 1: AUDIT-LOG CSV EXPORT ───────────────────────────────────────────
@app.route('/api/audit_log_csv', methods=['GET'])
@require_auth('manageUsers')
def audit_log_csv():
    import csv, io
    db = get_db()
    rows = db.execute(
        "SELECT ts, benutzer, aktion, tabelle, datensatz_id, details FROM audit_log ORDER BY id DESC LIMIT 10000"
    ).fetchall()
    db.close()
    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(['Zeitstempel','Benutzer','Aktion','Tabelle','ID','Details'])
    for r in rows:
        w.writerow(list(r))
    from flask import Response
    return Response(
        '﻿' + out.getvalue(),   # BOM für Excel
        content_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=audit_log.csv'}
    )

# ─── PHASE 2: DT-FOTO ────────────────────────────────────────────────────────
@app.route('/api/datentraeger/<int:did>/foto', methods=['POST'])
@require_auth('write')
def upload_dt_foto(did):
    # Accept JSON with base64 data: {data: "base64...", mime: "image/jpeg"}
    body = request.get_json(silent=True) or {}
    b64 = body.get('data', '')
    mime = body.get('mime', 'image/jpeg')
    if not b64:
        return jsonify({'error': 'Kein Foto'}), 400
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return jsonify({'error': 'Ungültige Bilddaten'}), 400
    if len(raw) > 5 * 1024 * 1024:
        return jsonify({'error': 'Foto zu groß (max. 5 MB)'}), 413
    db = get_db()
    db.execute("UPDATE datentraeger SET foto_data=?, foto_type=? WHERE id=?", (raw, mime, did))
    db.commit()
    db.close()
    _cache_del('datentraeger')
    log_audit(request.user['username'], 'FOTO_UPLOAD', 'datentraeger', did, f'type={mime}, size={len(raw)}')
    return jsonify({'ok': True})

@app.route('/api/datentraeger/<int:did>/foto', methods=['GET'])
@require_auth('read')
def get_dt_foto(did):
    db = get_db()
    row = db.execute("SELECT foto_data, foto_type FROM datentraeger WHERE id=?", (did,)).fetchone()
    db.close()
    if not row or not row['foto_data']:
        return jsonify({'data': None}), 200
    b64 = base64.b64encode(row['foto_data']).decode('utf-8')
    mime = row['foto_type'] or 'image/jpeg'
    return jsonify({'data': f'data:{mime};base64,{b64}'})

@app.route('/api/datentraeger/<int:did>/foto', methods=['DELETE'])
@require_auth('write')
def delete_dt_foto(did):
    db = get_db()
    db.execute("UPDATE datentraeger SET foto_data=NULL, foto_type=NULL WHERE id=?", (did,))
    db.commit()
    db.close()
    _cache_del('datentraeger')
    return jsonify({'ok': True})

# ─── PHASE 2: DT-NOTIZEN ─────────────────────────────────────────────────────
@app.route('/api/datentraeger/<int:did>/notizen', methods=['GET'])
@require_auth('read')
def get_dt_notizen(did):
    db = get_db()
    rows = db.execute(
        "SELECT id, text, benutzer, ts FROM dt_notizen WHERE datentraeger_id=? ORDER BY ts DESC", (did,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/datentraeger/<int:did>/notizen', methods=['POST'])
@require_auth('write')
def add_dt_notiz(did):
    data = request.json or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Text fehlt'}), 400
    benutzer = request.user.get('username', '?')
    ts = datetime.now().isoformat(timespec='seconds')
    db = get_db()
    cur = db.execute(
        "INSERT INTO dt_notizen(datentraeger_id, text, benutzer, ts) VALUES(?,?,?,?)",
        (did, text, benutzer, ts)
    )
    db.commit()
    nid = cur.lastrowid
    db.close()
    return jsonify({'ok': True, 'id': nid, 'benutzer': benutzer, 'ts': ts})

@app.route('/api/datentraeger/<int:did>/notizen/<int:nid>', methods=['DELETE'])
@require_auth('write')
def delete_dt_notiz(did, nid):
    db = get_db()
    db.execute("DELETE FROM dt_notizen WHERE id=? AND datentraeger_id=?", (nid, did))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ─── PHASE 2: DT-WARTUNGSHISTORIE ────────────────────────────────────────────
@app.route('/api/datentraeger/<int:did>/wartungen', methods=['GET'])
@require_auth('read')
def get_dt_wartungen(did):
    db = get_db()
    rows = db.execute(
        "SELECT id, datum, notizen, benutzer, erstellt FROM dt_wartungen WHERE datentraeger_id=? ORDER BY datum DESC",
        (did,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/datentraeger/<int:did>/wartungen', methods=['POST'])
@require_auth('write')
def add_dt_wartung(did):
    data = request.json or {}
    datum = (data.get('datum') or '').strip() or datetime.now().strftime('%Y-%m-%d')
    notizen = (data.get('notizen') or '').strip()
    benutzer = request.user.get('username', '?')
    db = get_db()
    db.execute("UPDATE datentraeger SET letzter_check_datum=? WHERE id=?", (datum, did))
    cur = db.execute(
        "INSERT INTO dt_wartungen(datentraeger_id, datum, notizen, benutzer) VALUES(?,?,?,?)",
        (did, datum, notizen, benutzer)
    )
    db.commit()
    wid = cur.lastrowid
    db.close()
    _cache_del('datentraeger')
    return jsonify({'ok': True, 'id': wid, 'datum': datum, 'notizen': notizen, 'benutzer': benutzer})

@app.route('/api/datentraeger/<int:did>/wartungen/<int:wid>', methods=['DELETE'])
@require_auth('write')
def delete_dt_wartung(did, wid):
    db = get_db()
    db.execute("DELETE FROM dt_wartungen WHERE id=? AND datentraeger_id=?", (wid, did))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ─── PHASE 4: STATS / CHARTS ─────────────────────────────────────────────────
@app.route('/api/stats/charts', methods=['GET'])
@require_auth('read')
def stats_charts():
    cached = _cache_get('stats_charts')
    if cached:
        return jsonify(cached)
    db = get_db()
    # Monthly revenue last 12 months — use invoice date (dat: DD.MM.YYYY), not erstellt
    from collections import defaultdict
    _rev_rows = db.execute("SELECT dat, netto FROM rechnungen WHERE dat IS NOT NULL").fetchall()
    _buckets = defaultdict(float)
    for r in _rev_rows:
        try:
            parts = str(r['dat']).split('.')
            if len(parts) == 3:
                key = f"{parts[2]}-{parts[1]}"
                val = str(r['netto']).replace('.','').replace(',','.').replace('€','').replace(' ','')
                _buckets[key] += float(val)
        except Exception:
            pass
    revenue_months, revenue_values = [], []
    now = datetime.now()
    for i in range(11, -1, -1):
        yr = (now.month - i - 1) // 12
        mo = ((now.month - i - 1) % 12) + 1
        yr_actual = now.year + yr if (now.month - i - 1) >= 0 else now.year - 1 + yr
        mo_str = f'{yr_actual}-{mo:02d}'
        revenue_months.append(mo_str)
        revenue_values.append(round(_buckets.get(mo_str, 0.0), 2))
    # DT status counts
    status_rows = db.execute(
        "SELECT status, COUNT(*) as cnt FROM datentraeger GROUP BY status"
    ).fetchall()
    dt_status = {r['status']: r['cnt'] for r in status_rows}
    # Vault utilization (top 8)
    vault_rows = db.execute("""
        SELECT t.bezeichnung, COUNT(d.id) as cnt
        FROM tresore t
        LEFT JOIN datentraeger d ON d.tresor_id=t.id AND d.status='eingelagert'
        GROUP BY t.id ORDER BY cnt DESC LIMIT 8
    """).fetchall()
    vault_util = [{'name': r['bezeichnung'], 'cnt': r['cnt']} for r in vault_rows]
    # Upcoming expirations (next 60 days) for push notifications
    cutoff = (now + timedelta(days=60)).strftime('%Y-%m-%d')
    today = now.strftime('%Y-%m-%d')
    exp_rows = db.execute("""
        SELECT k.firma, k.nr, k.vertragsende
        FROM kunden k
        WHERE k.vertragsende IS NOT NULL AND k.vertragsende != ''
          AND k.vertragsende >= ? AND k.vertragsende <= ?
        ORDER BY k.vertragsende ASC LIMIT 20
    """, (today, cutoff)).fetchall()
    expirations = [{'firma': r['firma'], 'nr': r['nr'], 'datum': r['vertragsende']} for r in exp_rows]
    db.close()
    result = {
        'revenue_months': revenue_months,
        'revenue_values': revenue_values,
        'dt_status': dt_status,
        'vault_utilization': vault_util,
        'upcoming_expirations': expirations,
    }
    _cache_set('stats_charts', result, 120)
    return jsonify(result)

# ─── AUTOMATIK / NOTIFICATION SETTINGS ──────────────────────────────────────
@app.route('/api/admin/notif_settings', methods=['GET'])
@require_auth('manageUsers')
def get_notif_settings():
    db = get_db()
    row = db.execute("SELECT * FROM notif_settings WHERE id=1").fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@app.route('/api/admin/notif_settings', methods=['POST'])
@require_auth('manageUsers')
def save_notif_settings():
    data = request.json or {}
    db = get_db()
    db.execute("""
        UPDATE notif_settings SET
            auto_mahnung_aktiv=?, auto_mahnung_tage=?,
            wartung_warnung_aktiv=?, wartung_warnung_tage=?,
            weekly_digest_aktiv=?, weekly_digest_wochentag=?,
            weekly_digest_stunde=?, weekly_digest_email=?
        WHERE id=1
    """, (
        1 if data.get('auto_mahnung_aktiv') else 0,
        max(1, int(data.get('auto_mahnung_tage', 14))),
        1 if data.get('wartung_warnung_aktiv') else 0,
        max(1, int(data.get('wartung_warnung_tage', 30))),
        1 if data.get('weekly_digest_aktiv') else 0,
        int(data.get('weekly_digest_wochentag', 1)) % 7,
        int(data.get('weekly_digest_stunde', 8)) % 24,
        str(data.get('weekly_digest_email', ''))[:254],
    ))
    db.commit()
    db.close()
    log_audit(request.user['username'], 'NOTIF_SETTINGS_UPDATE', 'notif_settings', 1, str(data))
    return jsonify({'ok': True})

# ─── STATIC ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# ─── BACKGROUND SCHEDULER ────────────────────────────────────────────────────
import threading as _threading

def _scheduler_get_notif_settings(db):
    row = db.execute("SELECT * FROM notif_settings WHERE id=1").fetchone()
    return dict(row) if row else {}

def _scheduler_already_sent(db, typ, referenz_key):
    """Check if a notification of this type+key was sent today already."""
    today = datetime.now().strftime('%Y-%m-%d')
    row = db.execute(
        "SELECT id FROM auto_notif_log WHERE typ=? AND referenz_key=? AND ts>=?",
        (typ, referenz_key, today)
    ).fetchone()
    return row is not None

def _scheduler_log_sent(db, typ, referenz_id, referenz_key, gesendet_an):
    db.execute(
        "INSERT INTO auto_notif_log(typ, referenz_id, referenz_key, gesendet_an, ts) VALUES(?,?,?,?,?)",
        (typ, referenz_id, referenz_key, gesendet_an, datetime.now().isoformat(timespec='seconds'))
    )

def _scheduler_run_auto_mahnungen(db, cfg):
    """Send automatic Mahnung emails for overdue invoices."""
    if not cfg.get('auto_mahnung_aktiv'):
        return
    tage = int(cfg.get('auto_mahnung_tage', 14))
    cutoff = (datetime.now() - timedelta(days=tage)).strftime('%Y-%m-%d')
    # Find invoices without bezahlt_am, with a valid kunden_id and email
    rows = db.execute("""
        SELECT r.id, r.nr, r.dat, r.netto, r.firma, k.email, k.ansprechpartner
        FROM rechnungen r
        LEFT JOIN kunden k ON k.id = r.kunden_id
        WHERE r.bezahlt_am IS NULL OR r.bezahlt_am = ''
          AND r.dat IS NOT NULL AND r.dat != ''
          AND k.email IS NOT NULL AND k.email != ''
    """).fetchall()
    sent_count = 0
    for r in rows:
        try:
            # Parse DD.MM.YYYY
            parts = str(r['dat']).split('.')
            if len(parts) != 3:
                continue
            inv_date = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            if inv_date > datetime.now() - timedelta(days=tage):
                continue
            referenz_key = f"mahnung_{r['nr']}"
            if _scheduler_already_sent(db, 'auto_mahnung', referenz_key):
                continue
            subject = f"Zahlungserinnerung: Rechnung {r['nr']}"
            body = f"""<p>Sehr geehrte Damen und Herren,</p>
<p>wir möchten Sie freundlich daran erinnern, dass folgende Rechnung noch offen ist:</p>
<table><tr><td><b>Rechnungsnummer:</b></td><td>{r['nr']}</td></tr>
<tr><td><b>Rechnungsdatum:</b></td><td>{r['dat']}</td></tr>
<tr><td><b>Betrag (netto):</b></td><td>{r['netto']}</td></tr></table>
<p>Bitte überweisen Sie den ausstehenden Betrag zeitnah.</p>
<p>Mit freundlichen Grüßen,<br>Ihr DT-Verwaltung Team</p>"""
            send_mail(r['email'], subject, body)
            _scheduler_log_sent(db, 'auto_mahnung', r['id'], referenz_key, r['email'])
            sent_count += 1
        except Exception as e:
            print(f"[SCHEDULER] Mahnung error for {r.get('nr')}: {e}")
    if sent_count:
        db.commit()
        print(f"[SCHEDULER] Auto-Mahnungen: {sent_count} gesendet")

def _scheduler_run_wartungswarnung(db, cfg):
    """Send maintenance warning emails for overdue/upcoming DT checks."""
    if not cfg.get('wartung_warnung_aktiv'):
        return
    tage = int(cfg.get('wartung_warnung_tage', 30))
    today = datetime.now()
    cutoff_future = (today + timedelta(days=tage)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    # Find DTs with wartungsintervall and letzter_check_datum
    rows = db.execute("""
        SELECT d.id, d.bezeichnung, d.serial, d.letzter_check_datum, d.wartungsintervall_jahre,
               k.firma, k.email
        FROM datentraeger d
        LEFT JOIN kunden k ON k.id = d.kunden_id
        WHERE d.wartungsintervall_jahre > 0
          AND d.letzter_check_datum IS NOT NULL AND d.letzter_check_datum != ''
          AND k.email IS NOT NULL AND k.email != ''
    """).fetchall()
    sent_count = 0
    for r in rows:
        try:
            letzter = datetime.fromisoformat(r['letzter_check_datum'])
            naechster = letzter.replace(year=letzter.year + int(r['wartungsintervall_jahre']))
            naechster_str = naechster.strftime('%Y-%m-%d')
            if naechster_str > cutoff_future:
                continue  # Still plenty of time
            referenz_key = f"wartung_{r['id']}_{naechster_str}"
            if _scheduler_already_sent(db, 'wartungswarnung', referenz_key):
                continue
            overdue = naechster_str < today_str
            subject = (f"Wartung überfällig: {r['bezeichnung']}" if overdue
                       else f"Wartung fällig in {(naechster - today).days} Tagen: {r['bezeichnung']}")
            body = f"""<p>Sehr geehrte Damen und Herren,</p>
<p>für folgenden Datenträger {'ist die Wartung überfällig' if overdue else 'steht eine Wartung an'}:</p>
<table><tr><td><b>Bezeichnung:</b></td><td>{r['bezeichnung']}</td></tr>
<tr><td><b>Seriennummer:</b></td><td>{r['serial']}</td></tr>
<tr><td><b>Nächste Wartung:</b></td><td>{naechster.strftime('%d.%m.%Y')}</td></tr></table>
<p>Bitte planen Sie die Wartung entsprechend.</p>
<p>Mit freundlichen Grüßen,<br>Ihr DT-Verwaltung Team</p>"""
            send_mail(r['email'], subject, body)
            _scheduler_log_sent(db, 'wartungswarnung', r['id'], referenz_key, r['email'])
            sent_count += 1
        except Exception as e:
            print(f"[SCHEDULER] Wartungswarnung error for DT {r.get('id')}: {e}")
    if sent_count:
        db.commit()
        print(f"[SCHEDULER] Wartungswarnungen: {sent_count} gesendet")

def _scheduler_run_weekly_digest(db, cfg):
    """Send weekly digest email on configured weekday + hour."""
    if not cfg.get('weekly_digest_aktiv'):
        return
    email = str(cfg.get('weekly_digest_email', '')).strip()
    if not email:
        return
    wochentag = int(cfg.get('weekly_digest_wochentag', 1))  # 0=Mo ... 6=So
    stunde = int(cfg.get('weekly_digest_stunde', 8))
    now = datetime.now()
    if now.weekday() != wochentag or now.hour != stunde:
        return
    referenz_key = f"digest_{now.strftime('%Y-%W')}"
    if _scheduler_already_sent(db, 'weekly_digest', referenz_key):
        return
    # Collect stats
    open_invoices = db.execute(
        "SELECT COUNT(*) as cnt FROM rechnungen WHERE bezahlt_am IS NULL OR bezahlt_am=''"
    ).fetchone()['cnt']
    dt_count = db.execute("SELECT COUNT(*) as cnt FROM datentraeger WHERE status='eingelagert'").fetchone()['cnt']
    expiring = db.execute("""
        SELECT firma, vertragsende FROM kunden
        WHERE vertragsende IS NOT NULL AND vertragsende != ''
          AND vertragsende >= date('now') AND vertragsende <= date('now', '+30 days')
        ORDER BY vertragsende LIMIT 10
    """).fetchall()
    body = f"""<h2>DT-Verwaltung – Wöchentlicher Statusbericht</h2>
<p><b>KW {now.strftime('%W')}/{now.year}</b></p>
<h3>Übersicht</h3>
<table>
<tr><td><b>Eingelagerte Datenträger:</b></td><td>{dt_count}</td></tr>
<tr><td><b>Offene Rechnungen:</b></td><td>{open_invoices}</td></tr>
</table>"""
    if expiring:
        body += "<h3>Verträge – ablaufend in 30 Tagen</h3><ul>"
        for e in expiring:
            body += f"<li>{e['firma']} – {e['vertragsende']}</li>"
        body += "</ul>"
    body += "<p><i>Automatisch generiert von DT-Verwaltung</i></p>"
    try:
        send_mail(email, f"DT-Verwaltung Statusbericht KW {now.strftime('%W')}", body)
        _scheduler_log_sent(db, 'weekly_digest', None, referenz_key, email)
        db.commit()
        print(f"[SCHEDULER] Weekly digest gesendet an {email}")
    except Exception as e:
        print(f"[SCHEDULER] Weekly digest error: {e}")

def _scheduler_tick():
    """Called every hour by the background thread."""
    try:
        db = get_db()
        cfg = _scheduler_get_notif_settings(db)
        _scheduler_run_auto_mahnungen(db, cfg)
        _scheduler_run_wartungswarnung(db, cfg)
        _scheduler_run_weekly_digest(db, cfg)
        db.close()
    except Exception as e:
        print(f"[SCHEDULER] Tick error: {e}")

def _start_scheduler():
    """Start the background scheduler thread that runs every 60 minutes."""
    def _loop():
        # Wait 60s after startup before first run (DB must be initialized)
        _threading.Event().wait(60)
        while True:
            _scheduler_tick()
            _threading.Event().wait(3600)  # run hourly
    t = _threading.Thread(target=_loop, daemon=True, name='dtv-scheduler')
    t.start()
    print("[SCHEDULER] Background scheduler started (hourly)")

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    _start_scheduler()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    print(f"[APP] Starting on port {port}, debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)
else:
    # Called by gunicorn
    init_db()
    _start_scheduler()
