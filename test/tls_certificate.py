"""Generate a short-lived certificate for verified loopback TLS tests."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import unittest


@contextmanager
def tls_certificate():
    if shutil.which("openssl") is None:
        raise unittest.SkipTest("OpenSSL is required for the verified TLS fixture")
    with tempfile.TemporaryDirectory() as directory:
        certificate = Path(directory) / "certificate.pem"
        key = Path(directory) / "key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=localhost",
            "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
        ], check=True, capture_output=True, timeout=15)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        yield certificate, context
