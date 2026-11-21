from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


CA_COMMON_NAME = "PKB Local CA"
SERVER_COMMON_NAME = "PKB Local Server"
CA_VALID_DAYS = 3650
SERVER_VALID_DAYS = 825


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _build_ca(ca_key: rsa.RSAPrivateKey) -> x509.Certificate:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CA_COMMON_NAME)])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=CA_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )


def _build_server_cert(
    server_key: rsa.RSAPrivateKey,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    hosts: list[str],
) -> x509.Certificate:
    now = datetime.datetime.now(datetime.timezone.utc)
    san_entries: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for host in hosts:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            san_entries.append(x509.DNSName(host))
    unique_entries = []
    seen = set()
    for entry in san_entries:
        key = str(entry.value)
        if key in seen:
            continue
        seen.add(key)
        unique_entries.append(entry)
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SERVER_COMMON_NAME)]))
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=SERVER_VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(unique_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )


def _cert_hosts(cert_path: Path) -> set[str]:
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except Exception:
        return set()
    hosts = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    hosts.update(name for name in san.get_values_for_type(x509.DNSName))
    return hosts


def ensure_certificates(cert_dir: Path, hosts: list[str]) -> tuple[Path, Path, Path]:
    """确保 CA 与服务器证书存在，返回 (ca_cert, server_cert, server_key)。

    CA 只生成一次，手机装过之后不需要重装；服务器证书在 IP 变化时会用同一 CA 重签。
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_key_path = cert_dir / "pkb-ca.key"
    ca_cert_path = cert_dir / "pkb-ca.crt"
    server_key_path = cert_dir / "pkb-server.key"
    server_cert_path = cert_dir / "pkb-server.crt"

    if not (ca_key_path.exists() and ca_cert_path.exists()):
        ca_key = _new_key()
        ca_cert = _build_ca(ca_key)
        _write_key(ca_key_path, ca_key)
        ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())

    current_hosts = {host for host in hosts if host}
    need_new_server = True
    if server_key_path.exists() and server_cert_path.exists():
        existing = _cert_hosts(server_cert_path)
        if current_hosts.issubset(existing):
            need_new_server = False

    if need_new_server:
        server_key = _new_key()
        server_cert = _build_server_cert(server_key, ca_key, ca_cert, sorted(current_hosts))
        _write_key(server_key_path, server_key)
        server_cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))

    return ca_cert_path, server_cert_path, server_key_path
