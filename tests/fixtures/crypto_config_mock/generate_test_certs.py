import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_VALIDITY_DAYS = 365

def generate_self_signed_cert(org_name: str, common_name: str, out_cert_path: Path, out_key_path: Path) -> None:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org_name),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=CERT_VALIDITY_DAYS)
    ).sign(private_key, hashes.SHA256())

    out_cert_path.parent.mkdir(parents=True, exist_ok=True)
    out_key_path.parent.mkdir(parents=True, exist_ok=True)

    out_cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    out_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

def main() -> None:
    base_dir = Path(__file__).parent

    generate_self_signed_cert(
        org_name="BNPParibas",
        common_name="test-admin-bnp",
        out_cert_path=base_dir / "peerOrganizations" / "bnpparibas.finance-trust.com" / "users" / "Admin@bnpparibas.finance-trust.com" / "msp" / "signcerts" / "cert.pem",
        out_key_path=base_dir / "peerOrganizations" / "bnpparibas.finance-trust.com" / "users" / "Admin@bnpparibas.finance-trust.com" / "msp" / "keystore" / "priv_sk",
    )

    generate_self_signed_cert(
        org_name="AMFRegulateur",
        common_name="test-admin-amf",
        out_cert_path=base_dir / "peerOrganizations" / "amf-regulateur.finance-trust.com" / "users" / "Admin@amf-regulateur.finance-trust.com" / "msp" / "signcerts" / "cert.pem",
        out_key_path=base_dir / "peerOrganizations" / "amf-regulateur.finance-trust.com" / "users" / "Admin@amf-regulateur.finance-trust.com" / "msp" / "keystore" / "priv_sk",
    )

if __name__ == "__main__":
    main()
