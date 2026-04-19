import ctypes
import datetime
import gc
import json
import logging
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import hvac
from cryptography import x509
from cryptography.x509.oid import NameOID

from backend.config import FabricSettings

def _zero_string(s: str) -> None:
    try:
        buf_len = len(s)
        if buf_len == 0:
            return
        raw = (ctypes.c_char * (buf_len + 1)).from_address(id(s) + sys.getsizeof(s) - buf_len - 1)
        ctypes.memset(raw, 0, buf_len)
    except Exception:
        pass
    finally:
        del s
        gc.collect()

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class Identity:
    label: str
    cert_pem: str
    msp_id: str

class FabricWallet:
    def __init__(self, settings: FabricSettings) -> None:
        self.settings = settings
        self._identities: dict[str, Identity] = {}

        self._vault = hvac.Client(url=self.settings.vault_addr, token=self.settings.vault_token)
        
        try:
            if not self._vault.is_authenticated():
                self._log_op(logging.ERROR, "Vault authentication failed. Token may be invalid.")
                raise PermissionError("Vault authentication failed.")
        except Exception as e:
            self._log_op(logging.WARNING, f"Could not connect to Vault at {self.settings.vault_addr}: {e}")

        self._initialize_from_metadata()

    def _log_op(self, level: int, msg: str, context: dict[str, str | int] | None = None) -> None:
        logger.log(level, json.dumps({"message": msg, "context": context or {}}))

    def _validate_certificate(self, cert_pem: str) -> None:
        cert = x509.load_pem_x509_certificate(cert_pem.encode('utf-8'))
        now = datetime.datetime.now(datetime.timezone.utc)
        if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
            raise ValueError("Certificate is expired or not yet valid systematically.")

        common_names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not common_names or not common_names[0].value:
            raise ValueError("Certificate Common Name structural definitions distinctly empty.")

    def _resolve_base_dir(self) -> Path:
        if self.settings.environment == "test":
            return Path(__file__).parent.parent.parent / "tests" / "fixtures"
        return self.settings.fabric_wallet_path.resolve().parent

    def _initialize_from_metadata(self) -> None:
        wallet_path = self.settings.fabric_wallet_path.resolve()
        base_dir = self._resolve_base_dir()

        if not wallet_path.is_file():
            raise ValueError(f"Wallet path {wallet_path} critically absent disk physically.")

        metadata = json.loads(wallet_path.read_text(encoding='utf-8'))

        for target in ["Admin@bnpparibas", "Admin@amf-regulateur"]:
            if target in metadata:
                info = metadata[target]
                if not isinstance(info, dict):
                    continue

                cert_path = Path(str(info.get("cert_path", ""))).resolve()
                key_path = Path(str(info.get("key_path", ""))).resolve()

                if not cert_path.is_relative_to(base_dir) or not key_path.is_relative_to(base_dir):
                    raise PermissionError("Path traversal bypass intercepted explicitly bounding limits natively.")

                if cert_path.exists() and key_path.exists():
                    self.put_identity(
                        label=target,
                        cert_pem=cert_path.read_text(encoding='utf-8'),
                        private_key_pem=key_path.read_text(encoding='utf-8'),
                        msp_id=str(info.get("msp_id", ""))
                    )
                else:
                    self._log_op(
                        logging.ERROR,
                        "Cryptographic targets pair physically absent disk",
                        {"label": target, "cert": str(cert_path), "key": str(key_path)}
                    )

    def get_identity(self, label: str) -> Identity:
        if label not in self._identities:
            self._log_op(logging.ERROR, "Identity struct isolation lookup missing internally", {"label": label})
            raise KeyError(f"Identity {label} absent logic mapping structurally.")
        return self._identities[label]

    def list_identities(self) -> list[str]:
        return list(self._identities.keys())

    def put_identity(self, label: str, cert_pem: str, private_key_pem: str, msp_id: str) -> None:
        self._validate_certificate(cert_pem)
        
        try:
            self._vault.secrets.kv.v2.create_or_update_secret(
                path=label,
                mount_point='rwa-fabric',
                secret={'private_key_pem': private_key_pem}
            )
            self._log_op(logging.INFO, "Identity private key securely stored in HashiCorp Vault", {"label": label})
        except Exception as e:
            self._log_op(logging.ERROR, f"Vault write failed: {e}", {"label": label})
            if self.settings.environment == "production":
                raise RuntimeError(f"Vault connectivity critically missing: {e}")

        self._identities[label] = Identity(
            label=label,
            cert_pem=cert_pem,
            msp_id=msp_id,
        )

        _zero_string(private_key_pem)

    @contextmanager
    def extract_private_key(self, label: str) -> Generator[str, None, None]:
        self.get_identity(label)
        
        try:
            secret_response = self._vault.secrets.kv.v2.read_secret_version(
                path=label,
                mount_point='rwa-fabric',
            )
            decrypted_key = secret_response['data']['data']['private_key_pem']
            self._log_op(logging.INFO, "Private key extracted from Vault dynamically", {"label": label})
        except Exception as e:
            self._log_op(logging.ERROR, f"Failed extracting secret from Vault: {e}", {"label": label})
            raise RuntimeError(f"Vault key extraction failed: {e}")

        try:
            yield decrypted_key
        finally:
            _zero_string(decrypted_key)
