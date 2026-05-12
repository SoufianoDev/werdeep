import logging
import os
import ssl
import sys

logger = logging.getLogger(__name__)

_patched = False
_ca_bundle_path = None


def _find_ca_bundle():
    ssl_paths = ssl.get_default_verify_paths()
    if ssl_paths.cafile and os.path.isfile(ssl_paths.cafile):
        return ssl_paths.cafile

    system_paths = [
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/etc/ssl/ca-bundle.pem",
        "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
        "/etc/ssl/cert.pem",
        "/usr/local/share/cert.pem",
        "/usr/share/cert.pem",
    ]
    for p in system_paths:
        if os.path.isfile(p):
            return p

    if sys.platform == "darwin":
        darwin_paths = [
            "/usr/local/etc/openssl/cert.pem",
            "/opt/homebrew/etc/openssl@3/cert.pem",
            "/opt/homebrew/etc/openssl@1.1/cert.pem",
            "/usr/local/etc/openssl@3/cert.pem",
        ]
        for p in darwin_paths:
            if os.path.isfile(p):
                return p

    try:
        import certifi

        certifi_path = certifi.where()
        if os.path.isfile(certifi_path):
            return certifi_path
    except ImportError:
        pass

    return None


def get_ca_bundle():
    """Return the path to the system CA certificate bundle."""
    global _ca_bundle_path
    if _ca_bundle_path is None:
        _ca_bundle_path = _find_ca_bundle() or ""
    return _ca_bundle_path


def patch_ssl():
    """Patch SSL environment variables and library defaults with the system CA bundle."""
    global _patched
    if _patched:
        return True

    ca_bundle = get_ca_bundle()
    if not ca_bundle:
        logger.warning("SSL_PATCH: No CA certificate bundle found")
        _patched = True
        return False

    os.environ["SSL_CERT_FILE"] = ca_bundle
    os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
    os.environ["CURL_CA_BUNDLE"] = ca_bundle

    try:
        import urllib3.util.ssl_ as ssl_util

        if hasattr(ssl_util, "DEFAULT_CA_BUNDLE_PATH"):
            ssl_util.DEFAULT_CA_BUNDLE_PATH = ca_bundle
    except ImportError:
        pass

    try:
        import requests.utils

        if hasattr(requests.utils, "DEFAULT_CA_BUNDLE_PATH"):
            requests.utils.DEFAULT_CA_BUNDLE_PATH = ca_bundle
    except ImportError:
        pass

    try:
        import requests.adapters

        if hasattr(requests.adapters, "DEFAULT_CA_BUNDLE_PATH"):
            requests.adapters.DEFAULT_CA_BUNDLE_PATH = ca_bundle
    except ImportError:
        pass

    _patched = True
    return True


def get_scrapy_ssl_settings():
    """Return Scrapy SSL settings dict pointing to the system CA bundle."""
    ca_bundle = get_ca_bundle()
    if not ca_bundle:
        return {}
    return {
        "REQUESTS_CA_BUNDLE": ca_bundle,
    }
