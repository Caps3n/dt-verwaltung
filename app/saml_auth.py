"""
SAML 2.0 Authentication für DT-Verwaltung
Unterstützt: Azure AD, Okta, Keycloak, ADFS und alle SAML2-kompatiblen IdPs

Konfiguration über Umgebungsvariablen (siehe .env.example):
  SAML_ENABLED=true
  SAML_IDP_METADATA_URL=https://login.microsoftonline.com/{tenant}/federationmetadata/2007-06/federationmetadata.xml
  SAML_SP_ENTITY_ID=https://dtv.deinefirma.de
  SAML_SP_ACS_URL=https://dtv.deinefirma.de/api/saml/acs
"""
import os, json, hashlib, secrets, logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SAML_ENABLED = os.environ.get('SAML_ENABLED', 'false').lower() == 'true'

def is_saml_enabled():
    return SAML_ENABLED

def get_saml_config():
    """Build pysaml2 config from environment variables."""
    sp_entity_id  = os.environ.get('SAML_SP_ENTITY_ID', '')
    acs_url       = os.environ.get('SAML_SP_ACS_URL', '')
    idp_meta_url  = os.environ.get('SAML_IDP_METADATA_URL', '')
    idp_meta_file = os.environ.get('SAML_IDP_METADATA_FILE', '')
    cert_file     = os.environ.get('SAML_SP_CERT_FILE', '/data/saml/sp.crt')
    key_file      = os.environ.get('SAML_SP_KEY_FILE',  '/data/saml/sp.key')
    name_id_format = os.environ.get('SAML_NAMEID_FORMAT', 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress')

    metadata = {}
    if idp_meta_url:
        metadata['remote'] = [{'url': idp_meta_url}]
    if idp_meta_file and os.path.exists(idp_meta_file):
        metadata['local'] = [idp_meta_file]

    config = {
        'entityid': sp_entity_id,
        'service': {
            'sp': {
                'name': 'DT-Verwaltung',
                'endpoints': {
                    'assertion_consumer_service': [
                        (acs_url, 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'),
                    ],
                },
                'name_id_format': [name_id_format],
                'authn_requests_signed': False,
                'want_assertions_signed': True,
                'allow_unsolicited': True,
            },
        },
        'metadata': metadata,
        'debug': False,
        'key_file':  key_file  if os.path.exists(key_file)  else None,
        'cert_file': cert_file if os.path.exists(cert_file) else None,
    }

    # Remove None values
    config = {k: v for k, v in config.items() if v is not None}
    return config


def build_saml_client():
    """Create a pysaml2 Saml2Client."""
    from saml2 import config as saml2_config
    from saml2.client import Saml2Client

    cfg = saml2_config.Config()
    cfg.load(get_saml_config())
    return Saml2Client(config=cfg)


def get_saml_login_url():
    """Return the IdP redirect URL to start SSO."""
    try:
        client = build_saml_client()
        req_id, info = client.prepare_for_authenticate()
        for key, value in dict(info['headers']).items():
            if key == 'Location':
                return {'url': value, 'req_id': req_id}
        raise Exception('No Location header in SAML auth request')
    except Exception as e:
        logger.error(f'SAML login URL error: {e}')
        raise


def process_saml_response(saml_response_b64):
    """
    Parse and validate the SAML Response from IdP.
    Returns dict with: email, name, groups, attributes
    """
    from saml2 import BINDING_HTTP_POST
    from saml2.response import StatusError

    try:
        client = build_saml_client()

        # Parse the response
        authn_response = client.parse_authn_request_response(
            saml_response_b64,
            BINDING_HTTP_POST,
        )

        if authn_response is None:
            raise ValueError('Empty SAML response')

        identity = authn_response.get_identity()
        name_id  = str(authn_response.get_subject())

        # Extract attributes – field names vary by IdP
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
            'givenName',
        ) or email.split('@')[0]

        # Groups/Roles from IdP
        groups = identity.get(
            'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups',
            identity.get('groups', identity.get('memberOf', []))
        )
        if isinstance(groups, str):
            groups = [groups]

        return {
            'email':      email,
            'name':       name,
            'name_id':    name_id,
            'groups':     groups or [],
            'attributes': {k: (v[0] if isinstance(v, list) and v else v) for k, v in identity.items()},
        }

    except StatusError as e:
        logger.error(f'SAML StatusError: {e}')
        raise ValueError(f'SAML-Fehler vom IdP: {e}')
    except Exception as e:
        logger.error(f'SAML response parse error: {e}')
        raise


def map_groups_to_rolle(groups, db, group_mapping_json):
    """
    Map IdP groups to DTV Rollen.
    group_mapping_json: {"Admins":"1","IT-Staff":"2","Read-Only":"3"}
    Returns rollen_id (default: Viewer=3)
    """
    if not groups or not group_mapping_json:
        return 3  # Default: Viewer

    try:
        mapping = json.loads(group_mapping_json)
    except (json.JSONDecodeError, TypeError):
        return 3

    for group in groups:
        for pattern, rollen_id in mapping.items():
            if pattern.lower() in group.lower() or group.lower() in pattern.lower():
                try:
                    return int(rollen_id)
                except (ValueError, TypeError):
                    pass
    return 3


def generate_sp_metadata():
    """Generate SP metadata XML for registering at IdP."""
    try:
        from saml2.metadata import entity_descriptor
        client = build_saml_client()
        metadata_xml = entity_descriptor(client.config)
        from lxml import etree
        return etree.tostring(metadata_xml, pretty_print=True, xml_declaration=True, encoding='utf-8')
    except Exception as e:
        logger.error(f'SP metadata error: {e}')
        raise


def generate_self_signed_cert(data_dir='/data'):
    """
    Generate a self-signed certificate for the SP.
    Only needed if the IdP requires signed requests.
    """
    import subprocess
    saml_dir = os.path.join(data_dir, 'saml')
    os.makedirs(saml_dir, exist_ok=True)
    key_path  = os.path.join(saml_dir, 'sp.key')
    cert_path = os.path.join(saml_dir, 'sp.crt')

    if os.path.exists(key_path) and os.path.exists(cert_path):
        return key_path, cert_path

    try:
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', key_path, '-out', cert_path,
            '-days', '3650', '-nodes',
            '-subj', '/CN=DT-Verwaltung-SP'
        ], check=True, capture_output=True)
        logger.info(f'Self-signed SAML cert generated: {cert_path}')
        return key_path, cert_path
    except Exception as e:
        logger.error(f'Cert generation failed: {e}')
        return None, None
