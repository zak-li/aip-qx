from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.fabric_client.network import AssetFrozenError, AssetNotFoundException, FabricClient


async def test_submit_transaction_calls_peer_chaincode_invoke():
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b'{"txID":"abc123","status":"ACTIF"}', b""))
    mock_process.returncode = 0

    settings = MagicMock()
    settings.fabric_channel = "rwa-channel"
    settings.fabric_chaincode = "rwa-token"
    settings.fabric_grpc_timeout = 30
    settings.fabric_connection_profile = MagicMock()

    wallet = MagicMock()
    client = FabricClient(settings, wallet)
    client._peers = [{"address": "peer0:7051", "tlsRoot": "/tmp/ca.crt"}]

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await client.submit_transaction.__wrapped__(client, "TokenizeAsset", "RWA-TEST-001", identity_label="admin-bnp")

    mock_exec.assert_called_once()
    call_args = mock_exec.call_args[0]
    assert "chaincode" in call_args
    assert "invoke" in call_args

async def test_evaluate_transaction_calls_peer_chaincode_query():
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b'{"assetID":"RWA-TEST-001","status":"ACTIF"}', b""))
    mock_process.returncode = 0

    settings = MagicMock()
    settings.fabric_channel = "rwa-channel"
    settings.fabric_chaincode = "rwa-token"
    settings.fabric_grpc_timeout = 30
    settings.fabric_connection_profile = MagicMock()

    wallet = MagicMock()
    client = FabricClient(settings, wallet)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        await client.evaluate_transaction.__wrapped__(client, "GetAsset", "RWA-TEST-001", identity_label="admin-bnp")

    mock_exec.assert_called_once()
    call_args = mock_exec.call_args[0]
    assert "chaincode" in call_args
    assert "query" in call_args

async def test_submit_raises_asset_frozen_error_on_stderr_match():
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b"", "Asset gel\u00e9 ref: REG01-INV-2026-001".encode()))
    mock_process.returncode = 1

    settings = MagicMock()
    settings.fabric_channel = "rwa-channel"
    settings.fabric_chaincode = "rwa-token"
    settings.fabric_grpc_timeout = 30

    wallet = MagicMock()
    client = FabricClient(settings, wallet)
    client._peers = [{"address": "peer0:7051", "tlsRoot": "/tmp/ca.crt"}]

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(AssetFrozenError) as exc_info:
            await client.submit_transaction.__wrapped__(client, "TransferAsset", "RWA-OBL-BANK01-2025-001", identity_label="admin-bnp")

    assert "REG01-INV-2026-001" in exc_info.value.regulatory_ref

async def test_evaluate_raises_asset_not_found_on_stderr_match():
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b"", b"introuvable sur le ledger"))
    mock_process.returncode = 1

    settings = MagicMock()
    settings.fabric_channel = "rwa-channel"
    settings.fabric_chaincode = "rwa-token"
    settings.fabric_grpc_timeout = 30

    wallet = MagicMock()
    client = FabricClient(settings, wallet)

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(AssetNotFoundException):
            await client.evaluate_transaction.__wrapped__(client, "GetAsset", "RWA-INEXISTANT-001", identity_label="admin-bnp")

def test_convert_keys_camel_to_snake():
    settings = MagicMock()
    wallet = MagicMock()
    client = FabricClient(settings, wallet)
    input_data = {"assetID": "x", "actorMSP": "y", "blockNumber": 5}
    result = client._convert_keys(input_data)
    assert "asset_id" in result
    assert "actor_msp" in result or "actor_m_s_p" in result
    assert result.get("asset_id") == "x"
