import asyncio
import json
import logging
import os

import yaml

from backend.config import FabricSettings

from .retry import fabric_retry
from .wallet import FabricWallet

logger = logging.getLogger(__name__)

type PayloadDict = dict[str, str | int | float | bool | dict[str, str | int | float | bool] | list[str | int | float | bool] | None]

class FabricEndorsementError(Exception):
    pass

class AssetNotFoundException(Exception):
    pass

class AssetFrozenError(Exception):
    def __init__(self, regulatory_ref: str):
        self.regulatory_ref = regulatory_ref
        super().__init__(f"Asset is frozen: {regulatory_ref}")

class FabricClient:

    def __init__(self, settings: FabricSettings, wallet: FabricWallet) -> None:
        self.settings = settings
        self.wallet = wallet
        self.channel_name = self.settings.fabric_channel
        self.chaincode_name = self.settings.fabric_chaincode

        self._network_config: dict[str, dict[str, str | dict[str, str]]] = {}
        self._peers: list[dict[str, str]] = []

        self.crypto_base = os.path.expanduser("~/rwa-platform/crypto-config")
        self.fabric_cfg = os.path.expanduser("~/go/src/github.com/hyperledger/fabric-samples/config")
        self.peer_bin = os.path.expanduser("~/go/src/github.com/hyperledger/fabric-samples/bin/peer")
        self.orderer_ca = f"{self.crypto_base}/ordererOrganizations/finance-trust.com/orderers/orderer.finance-trust.com/msp/tlscacerts/tlsca.finance-trust.com-cert.pem"

    _FORBIDDEN_PATTERN = __import__("re").compile(
        r"[\x00-\x1f\x7f]"
        r"|[$`]"
        r"|[;|&]"
        r"|\.\."
        r"|[><]"
    )

    def _sanitize_arguments(self, args: tuple[str, ...]) -> None:
        for arg in args:
            if not isinstance(arg, str):
                raise TypeError(f"Argument Fabric CLI doit être str, reçu {type(arg).__name__}")
            if self._FORBIDDEN_PATTERN.search(arg):
                raise ValueError(
                    f"Argument Fabric CLI contient des caractères interdits: {arg!r:.80}"
                )

    async def connect(self) -> None:
        profile_content = await asyncio.to_thread(self.settings.fabric_connection_profile.read_text, encoding='utf-8')
        config_parsed = yaml.safe_load(profile_content)
        self._network_config = config_parsed if isinstance(config_parsed, dict) else {}

        peers = self._network_config.get("peers", {})
        if not isinstance(peers, dict):
            peers = {}

        for peer_id, peer_ext in peers.items():
            if not isinstance(peer_ext, dict):
                continue

            url_raw = str(peer_ext.get("url", ""))
            addr = url_raw.replace("grpcs://", "").replace("grpc://", "")
            port = addr.split(":")[-1] if ":" in addr else "7051"

            tls_certs = peer_ext.get("tlsCACerts", {})
            cert_rel = str(tls_certs.get("path", "")) if isinstance(tls_certs, dict) else ""

            cert_abs = cert_rel.replace("./crypto-config", self.crypto_base)

            self._peers.append({
                "address": f"{peer_id}:{port}",
                "tlsRoot": cert_abs
            })

    async def disconnect(self) -> None:
        pass

    def _get_env_for_identity(self, identity_label: str) -> dict[str, str]:
        env = os.environ.copy()
        env["FABRIC_CFG_PATH"] = self.fabric_cfg

        if "bnp" in identity_label.lower():
            env["CORE_PEER_LOCALMSPID"] = "BNPParibasMSP"
            env["CORE_PEER_ADDRESS"] = "peer0.bnpparibas.finance-trust.com:7051"
            env["CORE_PEER_MSPCONFIGPATH"] = f"{self.crypto_base}/peerOrganizations/bnpparibas.finance-trust.com/users/Admin@bnpparibas.finance-trust.com/msp"
            env["CORE_PEER_TLS_CERT_FILE"] = f"{self.crypto_base}/peerOrganizations/bnpparibas.finance-trust.com/peers/peer0.bnpparibas.finance-trust.com/tls/server.crt"
            env["CORE_PEER_TLS_KEY_FILE"] = f"{self.crypto_base}/peerOrganizations/bnpparibas.finance-trust.com/peers/peer0.bnpparibas.finance-trust.com/tls/server.key"
            env["CORE_PEER_TLS_ROOTCERT_FILE"] = f"{self.crypto_base}/peerOrganizations/bnpparibas.finance-trust.com/peers/peer0.bnpparibas.finance-trust.com/tls/ca.crt"
        elif "amf" in identity_label.lower():
            env["CORE_PEER_LOCALMSPID"] = "AMFRegulateurMSP"
            env["CORE_PEER_ADDRESS"] = "peer0.amf-regulateur.finance-trust.com:7091"
            env["CORE_PEER_MSPCONFIGPATH"] = f"{self.crypto_base}/peerOrganizations/amf-regulateur.finance-trust.com/users/Admin@amf-regulateur.finance-trust.com/msp"
            env["CORE_PEER_TLS_CERT_FILE"] = f"{self.crypto_base}/peerOrganizations/amf-regulateur.finance-trust.com/peers/peer0.amf-regulateur.finance-trust.com/tls/server.crt"
            env["CORE_PEER_TLS_KEY_FILE"] = f"{self.crypto_base}/peerOrganizations/amf-regulateur.finance-trust.com/peers/peer0.amf-regulateur.finance-trust.com/tls/server.key"
            env["CORE_PEER_TLS_ROOTCERT_FILE"] = f"{self.crypto_base}/peerOrganizations/amf-regulateur.finance-trust.com/peers/peer0.amf-regulateur.finance-trust.com/tls/ca.crt"
        else:
            raise ValueError(f"Unknown identity mapping {identity_label}")

        env["CORE_PEER_TLS_ENABLED"] = "true"
        return env

    async def _exec_cli(self, cmd: list[str], env: dict[str, str]) -> tuple[str, str]:
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        except FileNotFoundError as exc:
            # Refuse to silently mock — a missing peer binary in production would
            # result in fake "successful" transactions that never hit the ledger.
            logger.error(f"Fabric peer binary not found at {self.peer_bin}")
            raise FabricEndorsementError(
                f"Fabric peer binary not available at {self.peer_bin}. "
                "Refusing to fabricate a successful response."
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.settings.fabric_grpc_timeout,
            )
        except TimeoutError as exc:
            process.kill()
            raise FabricEndorsementError("Fabric CLI subprocess explicitly timed out boundary limit.") from exc

        stdout_dec = stdout.decode('utf-8').strip()
        stderr_dec = stderr.decode('utf-8').strip()

        if process.returncode != 0:
            if "introuvable sur le ledger" in stderr_dec:
                raise AssetNotFoundException("Specifically missing required structural matching parameters dynamically.")
            if "gelé" in stderr_dec:
                import re
                match = re.search(r"ref:\s*([A-Z0-9_-]+)", stderr_dec)
                ref = match.group(1) if match else "UNKNOWN_REF"
                raise AssetFrozenError(ref)
            raise FabricEndorsementError(f"CLI error {process.returncode}: {stderr_dec}")

        return stdout_dec, stderr_dec

    @fabric_retry()
    async def submit_transaction(
        self,
        function: str,
        *args: str,
        identity_label: str
    ) -> PayloadDict | list[PayloadDict | str | int | float | bool] | str | None:
        self._sanitize_arguments(args)

        env = self._get_env_for_identity(identity_label)

        payload = {"Args": [function, *list(args)]}

        cmd = [
            self.peer_bin, "chaincode", "invoke",
            "-o", "orderer.finance-trust.com:7050",
            "--tls", "--cafile", self.orderer_ca,
            "-C", self.channel_name,
            "-n", self.chaincode_name,
        ]

        for p in self._peers:
            cmd.extend(["--peerAddresses", p["address"], "--tlsRootCertFiles", p["tlsRoot"]])

        cmd.extend(["-c", json.dumps(payload), "--waitForEvent"])

        stdout, stderr = await self._exec_cli(cmd, env)

        try:
            lines = stdout.split('\n')
            for line in reversed(lines):
                if line.startswith('payload:'):
                    p_str = line.split('payload:', 1)[1].strip().strip('"')
                    return json.loads(p_str.replace('\\"', '"'))
                if '{' in line:
                    return json.loads(line)
            return {"status": 200, "message": "Transaction submitted successfully."}
        except (json.JSONDecodeError, IndexError, ValueError) as exc:
            logger.error(f"submit_transaction: impossible de parser la réponse Fabric: {exc}")
            raise FabricEndorsementError(f"Réponse Fabric illisible: {stdout[:200]}") from exc

    def _convert_keys(self, obj):
        """Recursively convert camelCase keys to snake_case in a nested structure.

        Strict: never invents missing fields. If the chaincode response is
        incomplete, the downstream Pydantic validator will surface the error
        rather than silently materialising fabricated UUIDs and values.
        """
        import re
        if isinstance(obj, list):
            return [self._convert_keys(i) for i in obj]
        if isinstance(obj, dict):
            return {
                re.sub('([a-z0-9])([A-Z])', r'\1_\2', k).lower(): self._convert_keys(v)
                for k, v in obj.items()
            }
        return obj

    @fabric_retry()
    async def evaluate_transaction(
        self,
        function: str,
        *args: str,
        identity_label: str
    ) -> PayloadDict | list[PayloadDict | str | int | float | bool] | str | None:
        self._sanitize_arguments(args)

        env = self._get_env_for_identity(identity_label)
        payload = {"Args": [function, *list(args)]}

        cmd = [
            self.peer_bin, "chaincode", "query",
            "-C", self.channel_name,
            "-n", self.chaincode_name,
            "-c", json.dumps(payload)
        ]

        stdout, stderr = await self._exec_cli(cmd, env)

        try:
            return self._convert_keys(json.loads(stdout))
        except (json.JSONDecodeError, ValueError) as exc:
            if stdout:
                logger.warning(f"evaluate_transaction: réponse non-JSON, retour brut: {exc}")
                return stdout
            logger.error(f"evaluate_transaction: réponse vide du chaincode: {exc}")
            return None
