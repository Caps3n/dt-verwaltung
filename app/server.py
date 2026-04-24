#!/usr/bin/env python3
"""DT-Verwaltung Backend – Flask + SQLite/SQLCipher (Docker-ready)"""
import json, hashlib, hmac, secrets, os, base64, sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, send_file, redirect
from flask_cors import CORS

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
CORS(app, resources={r"/api/*": {"origins": "*"}})

# DB in persistent volume /data
DATA_DIR = os.environ.get('DATA_DIR', '/data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'dtv.db')
SESSIONS = {}  # token -> {user_id, expires}  (in-memory cache, backed by DB)
# SAML client cache (keyed by config hash for hot-reload)
_saml_client_cache = {}

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
    """Get session from in-memory cache or fall back to DB."""
    if token in SESSIONS:
        return SESSIONS[token]
    db = get_db()
    row = db.execute("SELECT user_id, expires FROM sessions WHERE token=?", (token,)).fetchone()
    db.close()
    if row:
        sess = {'user_id': row['user_id'], 'expires': row['expires']}
        SESSIONS[token] = sess  # cache it
        return sess
    return None

def session_delete(token):
    """Remove session from cache and DB."""
    SESSIONS.pop(token, None)
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token=?", (token,))
    db.commit()
    db.close()

def clean_sessions():
    """Remove expired sessions from DB and cache."""
    now = datetime.now().isoformat()
    db = get_db()
    db.execute("DELETE FROM sessions WHERE expires < ?", (now,))
    db.commit()
    db.close()
    expired = [t for t, s in list(SESSIONS.items()) if s['expires'] < now]
    for t in expired:
        del SESSIONS[t]

def build_saml_client_from_db(s):
    """Build a pysaml2 client from DB-stored SAML settings, with caching."""
    import hashlib as _hashlib
    cfg_key = _hashlib.md5(json.dumps(s, sort_keys=True).encode()).hexdigest()
    if cfg_key in _saml_client_cache:
        return _saml_client_cache[cfg_key]

    from saml2 import config as saml2_config
    from saml2.client import Saml2Client

    metadata = {}
    if s.get('idp_metadata_url'):
        metadata['remote'] = [{'url': s['idp_metadata_url']}]
    if s.get('idp_metadata_xml'):
        # Write to temp file
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix='.xml', delete=False, mode='w')
        tmp.write(s['idp_metadata_xml'])
        tmp.close()
        metadata['local'] = [tmp.name]

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

    # Add cert/key if present
    if s.get('sp_cert') and s.get('sp_key'):
        import tempfile
        kf = tempfile.NamedTemporaryFile(suffix='.key', delete=False, mode='w')
        kf.write(s['sp_key']); kf.close()
        cf = tempfile.NamedTemporaryFile(suffix='.crt', delete=False, mode='w')
        cf.write(s['sp_cert']); cf.close()
        cfg_dict['key_file']  = kf.name
        cfg_dict['cert_file'] = cf.name

    cfg = saml2_config.Config()
    cfg.load(cfg_dict)
    client = Saml2Client(config=cfg)
    _saml_client_cache[cfg_key] = client
    return client


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
    CREATE TABLE IF NOT EXISTS saml_config (
        id INTEGER PRIMARY KEY DEFAULT 1,
        enabled INTEGER DEFAULT 0,
        idp_name TEXT DEFAULT 'Single Sign-On',
        sp_entity_id TEXT DEFAULT '',
        sp_acs_url TEXT DEFAULT '',
        idp_metadata_url TEXT DEFAULT '',
        idp_metadata_xml TEXT DEFAULT '',
        group_mapping TEXT DEFAULT '{}',
        sp_cert TEXT DEFAULT '',
        sp_key TEXT DEFAULT '',
        geaendert TEXT DEFAULT CURRENT_TIMESTAMP
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
    db.execute("INSERT OR IGNORE INTO template_settings(id) VALUES(1)")
    db.execute("INSERT OR IGNORE INTO saml_config(id) VALUES(1)")
    db.execute("INSERT OR IGNORE INTO saml_settings(id) VALUES(1)")
    db.commit()
    db.close()
    print(f"[DB] Initialized at {DB_PATH}")

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

@app.route('/api/login', methods=['POST'])
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
        'perms': json.loads(user['berechtigungen'])
    }})

@app.route('/api/logout', methods=['POST'])
def logout():
    session_delete(request.headers.get('X-Token', ''))
    return jsonify({'ok': True})

@app.route('/api/me/password', methods=['PUT'])
@require_auth('read')
def change_own_password():
    data = request.json or {}
    password_alt = data.get('password_alt', '')
    password_neu = data.get('password', '')
    if not password_alt or not password_neu:
        return jsonify({'error': 'Altes und neues Passwort erforderlich'}), 400
    if len(password_neu) < 4:
        return jsonify({'error': 'Neues Passwort zu kurz'}), 400
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
    db = get_db()
    rows = db.execute(
        "SELECT id,nr,firma,ansprechpartner,email,tel,mobil,strasse,plz,ort,land,sap_nr,vertragsnr,vertragsbeginn,vertragsende,vertragsstatus,vertragsnotiz,vertrag_doc_name FROM kunden ORDER BY firma"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/kunden', methods=['POST'])
@require_auth('write')
def create_kunde():
    data = request.json or {}
    if not data.get('firma') or not data.get('nr'):
        return jsonify({'error': 'Firma und Kundennummer erforderlich'}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO kunden(nr,firma,anrede,ansprechpartner,email,tel,mobil,strasse,plz,ort,land,sap_nr,vertragsnr,vertragsbeginn,vertragsende,vertragsstatus,vertragsnotiz,mengenrabatt_json,rechnungsempfaenger_id,eigentuemer_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data['nr'], data['firma'], data.get('anrede',''), data.get('ansprechpartner'), data.get('email'), data.get('tel'),
             data.get('mobil'), data.get('strasse'), data.get('plz'), data.get('ort'), data.get('land', 'Deutschland'),
             data.get('sap_nr'), data.get('vertragsnr'), data.get('vertragsbeginn'), data.get('vertragsende'),
             data.get('vertragsstatus', 'aktiv'), data.get('vertragsnotiz'), data.get('mengenrabatt_json', '[]'),
             data.get('rechnungsempfaenger_id') or None, data.get('eigentuemer_id') or None)
        )
        db.commit()
        kid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
        db.close()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError:
        db.close()
        return jsonify({'error': 'Kundennummer bereits vergeben'}), 400

@app.route('/api/kunden/<int:kid>', methods=['PUT'])
@require_auth('write')
def update_kunde(kid):
    data = request.json or {}
    db = get_db()
    old = db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
    if old and old['vertragsnr'] and old['vertragsnr'] != data.get('vertragsnr') and data.get('vertragsnr'):
        db.execute(
            "INSERT INTO vertrags_history(kunden_id,datum,vertragsnr,status,notiz) VALUES(?,?,?,?,?)",
            (kid, datetime.now().strftime('%d.%m.%Y'), old['vertragsnr'],
             old['vertragsstatus'] or 'abgelaufen', old['vertragsnotiz'] or '')
        )
    db.execute(
        "UPDATE kunden SET nr=?,firma=?,anrede=?,ansprechpartner=?,email=?,tel=?,mobil=?,strasse=?,plz=?,ort=?,land=?,sap_nr=?,vertragsnr=?,vertragsbeginn=?,vertragsende=?,vertragsstatus=?,vertragsnotiz=?,mengenrabatt_json=?,rechnungsempfaenger_id=?,eigentuemer_id=?,geaendert=CURRENT_TIMESTAMP WHERE id=?",
        (data['nr'], data['firma'], data.get('anrede',''), data.get('ansprechpartner'), data.get('email'), data.get('tel'),
         data.get('mobil'), data.get('strasse'), data.get('plz'), data.get('ort'), data.get('land', 'Deutschland'),
         data.get('sap_nr'), data.get('vertragsnr'), data.get('vertragsbeginn'), data.get('vertragsende'),
         data.get('vertragsstatus', 'aktiv'), data.get('vertragsnotiz'), data.get('mengenrabatt_json', '[]'),
         data.get('rechnungsempfaenger_id') or None, data.get('eigentuemer_id') or None, kid)
    )
    db.commit()
    row = db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
    db.close()
    return jsonify(dict(row))

@app.route('/api/kunden/<int:kid>', methods=['DELETE'])
@require_auth('delete')
def delete_kunde(kid):
    db = get_db()
    db.execute("DELETE FROM kunden WHERE id=?", (kid,))
    db.commit()
    db.close()
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
            "SELECT d.*,k.firma,k.nr as kunden_nr,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN tresore t ON d.tresor_id=t.id WHERE d.kunden_id=? ORDER BY d.id", (kunden_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT d.*,k.firma,k.nr as kunden_nr,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN tresore t ON d.tresor_id=t.id ORDER BY d.id"
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
    db = get_db()
    db.execute(
        "INSERT INTO datentraeger(kunden_id,bezeichnung,serial,preis,einheit,preis_jahr,rabatt,einlagerungs_datum,beschreibung,bild,bild_type,eingang_doc,eingang_doc_type,eingang_doc_name,tresor_id,interne_nr) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (data['kunden_id'], data['bezeichnung'], data['serial'], data.get('preis', 0), data.get('einheit', 'monat'),
         data.get('preis_jahr', 0), data.get('rabatt', 0), data['einlagerungs_datum'],
         data.get('beschreibung', ''), data.get('bild'), data.get('bild_type'),
         data.get('eingang_doc'), data.get('eingang_doc_type'), data.get('eingang_doc_name'),
         data.get('tresor_id') or None, data.get('interne_nr',''))
    )
    db.commit()
    did = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = db.execute(
        "SELECT d.*,k.firma,k.nr as kunden_nr,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN tresore t ON d.tresor_id=t.id WHERE d.id=?", (did,)
    ).fetchone()
    db.close()
    d = dict(row)
    d['hat_bild'] = bool(data.get('bild'))
    d['hat_eingang_doc'] = bool(data.get('eingang_doc'))
    d.pop('bild', None)
    d.pop('eingang_doc', None)
    return jsonify(d), 201

@app.route('/api/datentraeger/<int:did>', methods=['PUT'])
@require_auth('write')
def update_dt(did):
    data = request.json or {}
    db = get_db()
    if data.get('bild') and data.get('eingang_doc'):
        db.execute(
            "UPDATE datentraeger SET kunden_id=?,bezeichnung=?,serial=?,preis=?,einheit=?,preis_jahr=?,rabatt=?,einlagerungs_datum=?,beschreibung=?,bild=?,bild_type=?,eingang_doc=?,eingang_doc_type=?,eingang_doc_name=?,tresor_id=?,interne_nr=? WHERE id=?",
            (data['kunden_id'], data['bezeichnung'], data['serial'], data.get('preis',0), data.get('einheit','monat'),
             data.get('preis_jahr',0), data.get('rabatt',0), data['einlagerungs_datum'],
             data.get('beschreibung',''), data.get('bild'), data.get('bild_type'),
             data.get('eingang_doc'), data.get('eingang_doc_type'), data.get('eingang_doc_name'),
             data.get('tresor_id') or None, data.get('interne_nr',''), did)
        )
    elif data.get('bild'):
        db.execute(
            "UPDATE datentraeger SET kunden_id=?,bezeichnung=?,serial=?,preis=?,einheit=?,preis_jahr=?,rabatt=?,einlagerungs_datum=?,beschreibung=?,bild=?,bild_type=?,tresor_id=?,interne_nr=? WHERE id=?",
            (data['kunden_id'], data['bezeichnung'], data['serial'], data.get('preis',0), data.get('einheit','monat'),
             data.get('preis_jahr',0), data.get('rabatt',0), data['einlagerungs_datum'],
             data.get('beschreibung',''), data.get('bild'), data.get('bild_type'),
             data.get('tresor_id') or None, data.get('interne_nr',''), did)
        )
    elif data.get('eingang_doc'):
        db.execute(
            "UPDATE datentraeger SET kunden_id=?,bezeichnung=?,serial=?,preis=?,einheit=?,preis_jahr=?,rabatt=?,einlagerungs_datum=?,beschreibung=?,eingang_doc=?,eingang_doc_type=?,eingang_doc_name=?,tresor_id=?,interne_nr=? WHERE id=?",
            (data['kunden_id'], data['bezeichnung'], data['serial'], data.get('preis',0), data.get('einheit','monat'),
             data.get('preis_jahr',0), data.get('rabatt',0), data['einlagerungs_datum'],
             data.get('beschreibung',''), data.get('eingang_doc'), data.get('eingang_doc_type'), data.get('eingang_doc_name'),
             data.get('tresor_id') or None, data.get('interne_nr',''), did)
        )
    else:
        db.execute(
            "UPDATE datentraeger SET kunden_id=?,bezeichnung=?,serial=?,preis=?,einheit=?,preis_jahr=?,rabatt=?,einlagerungs_datum=?,beschreibung=?,tresor_id=?,interne_nr=? WHERE id=?",
            (data['kunden_id'], data['bezeichnung'], data['serial'], data.get('preis',0), data.get('einheit','monat'),
             data.get('preis_jahr',0), data.get('rabatt',0), data['einlagerungs_datum'],
             data.get('beschreibung',''), data.get('tresor_id') or None, did)
        )
    db.commit()
    row = db.execute(
        "SELECT d.*,k.firma,k.nr as kunden_nr,t.bezeichnung as tresor_bezeichnung,t.land as tresor_land,t.stadt as tresor_stadt,t.gebaeude as tresor_gebaeude,t.etage as tresor_etage,t.raum as tresor_raum FROM datentraeger d JOIN kunden k ON d.kunden_id=k.id LEFT JOIN tresore t ON d.tresor_id=t.id WHERE d.id=?", (did,)
    ).fetchone()
    db.close()
    d = dict(row)
    d['hat_bild'] = bool(d.get('bild'))
    d.pop('bild', None)
    return jsonify(d)

@app.route('/api/datentraeger/<int:did>', methods=['DELETE'])
@require_auth('delete')
def delete_dt(did):
    db = get_db()
    db.execute("DELETE FROM datentraeger WHERE id=?", (did,))
    db.commit()
    db.close()
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
    pnr = f"UP-{datetime.now().strftime('%Y%m%d')}-{data.get('kunden_nr', '?')}"
    db = get_db()
    db.execute(
        "INSERT INTO uebergaben(kunden_id,datum,empfaenger,grund,protokoll_nr,abgeschlossen) VALUES(?,?,?,?,?,0)",
        (data['kunden_id'], data.get('datum', ''), data.get('Empfänger', data.get('Empfänger', data.get('Empfänger', data.get('empfaenger', '')))), data.get('grund', ''), pnr)
    )
    db.commit()
    uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    for did in data.get('dt_ids', []):
        db.execute("INSERT INTO uebergabe_positionen(uebergabe_id,datentraeger_id) VALUES(?,?)", (uid, did))
    db.commit()
    db.close()
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
    return jsonify({'ok': True})

@app.route('/api/uebergaben/<int:uid>', methods=['DELETE'])
@require_auth('write')
def delete_uebergabe(uid):
    db = get_db()
    row = db.execute("SELECT id FROM uebergaben WHERE id=?", (uid,)).fetchone()
    if not row:
        db.close()
        return jsonify({'error': 'Nicht gefunden'}), 404
    db.execute("DELETE FROM uebergabe_positionen WHERE uebergabe_id=?", (uid,))
    db.execute("DELETE FROM uebergaben WHERE id=?", (uid,))
    db.commit()
    db.close()
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
@app.route('/api/db/export', methods=['GET'])
@require_auth('manageUsers')
def export_db():
    return send_file(DB_PATH, as_attachment=True, download_name='dtv_backup.db')

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
    # Reload SAML client cache
    _saml_client_cache.clear()
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
        return jsonify({'ok': True, 'cert': cert})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/me', methods=['GET'])
@require_auth('read')
def get_me():
    """Return current user's info. Used by SAML flow to get user context after token redirect."""
    u = request.user
    return jsonify({
        'id': u['id'], 'username': u['username'], 'name': u['name'],
        'rollen_name': u['rollen_name'], 'farbe': u['farbe'],
        'perms': request.perms
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

    # Redirect to frontend with token
    frontend_url = os.environ.get('SAML_FRONTEND_URL', '/')
    return redirect(f'{frontend_url}#saml_token={token}')

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
        "INSERT INTO tresore(bezeichnung,hersteller,modell,seriennummer,land,stadt,gebaeude,etage,raum,kaufdatum,kaufpreis,wartungskosten_jaehrlich,letzter_wartungstermin,naechster_wartungstermin,notizen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (data['bezeichnung'], data.get('hersteller'), data.get('modell'), data.get('seriennummer'),
         data.get('land', 'Deutschland'), data.get('stadt'), data.get('gebaeude'), data.get('etage'), data.get('raum'),
         data.get('kaufdatum'), data.get('kaufpreis', 0), data.get('wartungskosten_jaehrlich', 0),
         data.get('letzter_wartungstermin'), data.get('naechster_wartungstermin'), data.get('notizen'))
    )
    db.commit()
    tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = db.execute("SELECT * FROM tresore WHERE id=?", (tid,)).fetchone()
    db.close()
    d = dict(row)
    d['hat_wartungsvertrag'] = False
    d.pop('wartungsvertrag_doc', None)
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
    db = get_db()
    if data.get('wartungsvertrag_doc'):
        db.execute(
            "UPDATE tresore SET bezeichnung=?,hersteller=?,modell=?,seriennummer=?,land=?,stadt=?,gebaeude=?,etage=?,raum=?,kaufdatum=?,kaufpreis=?,wartungskosten_jaehrlich=?,letzter_wartungstermin=?,naechster_wartungstermin=?,notizen=?,wartungsvertrag_doc=?,wartungsvertrag_doc_type=?,wartungsvertrag_doc_name=?,geaendert=CURRENT_TIMESTAMP WHERE id=?",
            (data['bezeichnung'], data.get('hersteller'), data.get('modell'), data.get('seriennummer'),
             data.get('land', 'Deutschland'), data.get('stadt'), data.get('gebaeude'), data.get('etage'), data.get('raum'),
             data.get('kaufdatum'), data.get('kaufpreis', 0), data.get('wartungskosten_jaehrlich', 0),
             data.get('letzter_wartungstermin'), data.get('naechster_wartungstermin'), data.get('notizen'),
             data.get('wartungsvertrag_doc'), data.get('wartungsvertrag_doc_type'), data.get('wartungsvertrag_doc_name'), tid)
        )
    else:
        db.execute(
            "UPDATE tresore SET bezeichnung=?,hersteller=?,modell=?,seriennummer=?,land=?,stadt=?,gebaeude=?,etage=?,raum=?,kaufdatum=?,kaufpreis=?,wartungskosten_jaehrlich=?,letzter_wartungstermin=?,naechster_wartungstermin=?,notizen=?,geaendert=CURRENT_TIMESTAMP WHERE id=?",
            (data['bezeichnung'], data.get('hersteller'), data.get('modell'), data.get('seriennummer'),
             data.get('land', 'Deutschland'), data.get('stadt'), data.get('gebaeude'), data.get('etage'), data.get('raum'),
             data.get('kaufdatum'), data.get('kaufpreis', 0), data.get('wartungskosten_jaehrlich', 0),
             data.get('letzter_wartungstermin'), data.get('naechster_wartungstermin'), data.get('notizen'), tid)
        )
    db.commit()
    row = db.execute("SELECT * FROM tresore WHERE id=?", (tid,)).fetchone()
    db.close()
    d = dict(row)
    d['hat_wartungsvertrag'] = bool(d.get('wartungsvertrag_doc'))
    d.pop('wartungsvertrag_doc', None)
    return jsonify(d)

@app.route('/api/tresore/<int:tid>', methods=['DELETE'])
@require_auth('delete')
def delete_tresor(tid):
    db = get_db()
    # Unlink DTs from this tresor first
    db.execute("UPDATE datentraeger SET tresor_id=NULL WHERE tresor_id=?", (tid,))
    db.execute("DELETE FROM tresore WHERE id=?", (tid,))
    db.commit()
    db.close()
    return jsonify({'ok': True})

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
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'db': DB_PATH})

# ─── STATIC ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    print(f"[APP] Starting on port {port}, debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)
else:
    # Called by gunicorn
    init_db()
