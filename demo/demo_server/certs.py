"""Generate a throwaway local test CA and the two server certificates (task T1.1).

- server.pem: valid for the demo hostnames (a/b/c.demo.test), signed by the test CA.
- wrong-host.pem: signed by the same CA but for another hostname, so a client that
  connects as a.demo.test must reject it (acceptance row 22).

The CA's private key is never written to disk: once the certificates are issued nobody can
sign anything else with this CA. Files go to demo/certs/, which is gitignored.
"""

import datetime
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

VALID_DAYS = 365


@dataclass(frozen=True)
class CertPaths:
    ca: Path
    server_cert: Path
    server_key: Path
    wrong_host_cert: Path
    wrong_host_key: Path

    def all_exist(self) -> bool:
        return all(
            p.is_file()
            for p in (
                self.ca,
                self.server_cert,
                self.server_key,
                self.wrong_host_cert,
                self.wrong_host_key,
            )
        )


def cert_paths(directory: Path) -> CertPaths:
    return CertPaths(
        ca=directory / "test-ca.pem",
        server_cert=directory / "server.pem",
        server_key=directory / "server.key",
        wrong_host_cert=directory / "wrong-host.pem",
        wrong_host_key=directory / "wrong-host.key",
    )


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _make_ca(now: datetime.datetime) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = _name("LinkGuard local test CA (do not trust outside tests)")
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
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
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _issue(
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    hostnames: tuple[str, ...],
    now: datetime.datetime,
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(hostnames[0]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(h) for h in hostnames]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def generate_certs(directory: Path, hostnames: tuple[str, ...], wrong_host: str) -> CertPaths:
    """Create a fresh CA, a valid server cert and a wrong-host cert in `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.UTC)
    ca_key, ca_cert = _make_ca(now)
    server_key, server_cert = _issue(ca_key, ca_cert, hostnames, now)
    wrong_key, wrong_cert = _issue(ca_key, ca_cert, (wrong_host,), now)

    paths = cert_paths(directory)
    _write_cert(paths.ca, ca_cert)
    _write_cert(paths.server_cert, server_cert)
    _write_key(paths.server_key, server_key)
    _write_cert(paths.wrong_host_cert, wrong_cert)
    _write_key(paths.wrong_host_key, wrong_key)
    return paths
