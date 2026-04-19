from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.features.fraud_detection.fraud_detection import FraudDetector
from backend.features.fraud_detection.neo4j_sync import Neo4jClient


def _make_mock_record(data: dict):
    record = MagicMock()
    record.__getitem__.side_effect = lambda key: data[key]
    return record


class AsyncIteratorMock:
    """Wraps a list into an async iterator for 'async for' compatibility."""
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


def _make_session_cm(mock_session: AsyncMock, mock_driver: MagicMock) -> None:
    """Wire mock_driver.session() to behave as an async context manager."""
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)


@pytest.fixture
def detector_with_driver():
    detector = FraudDetector()
    # neo4j driver.session() is a sync call returning an async CM — use MagicMock
    mock_driver = MagicMock()
    detector._driver = mock_driver
    return detector, mock_driver


async def test_detect_circular_flow_returns_results(detector_with_driver):
    detector, mock_driver = detector_with_driver

    mock_session = AsyncMock()
    _make_session_cm(mock_session, mock_driver)

    mock_session.run.return_value = AsyncIteratorMock([
        _make_mock_record({"SuspiciousActor": "CN=actor1,OU=BNP", "CycleLength": 3, "TotalVolume": 5000000.0}),
    ])

    results = await detector.detect_circular_flow(depth=4)

    assert len(results) == 1
    assert results[0]["actor_dn"] == "CN=actor1,OU=BNP"
    assert results[0]["cycle_length"] == 3
    assert results[0]["total_volume"] == 5000000.0
    assert results[0]["pattern"] == "CIRCULAR_FLOW"


async def test_detect_circular_flow_no_driver():
    detector = FraudDetector()
    results = await detector.detect_circular_flow()
    assert results == []


async def test_detect_smurfing_returns_results(detector_with_driver):
    detector, mock_driver = detector_with_driver

    mock_session = AsyncMock()
    _make_session_cm(mock_session, mock_driver)

    mock_session.run.return_value = AsyncIteratorMock([
        _make_mock_record({"SmurfCore": "CN=smurf1,OU=BNP", "num_transfers": 8, "avg_amount": 12000.0}),
        _make_mock_record({"SmurfCore": "CN=smurf2,OU=AMF", "num_transfers": 12, "avg_amount": 8500.0}),
    ])

    results = await detector.detect_smurfing()

    assert len(results) == 2
    assert results[0]["pattern"] == "SMURFING"
    assert results[1]["transfer_count"] == 12


async def test_detect_layering_returns_results(detector_with_driver):
    detector, mock_driver = detector_with_driver

    mock_session = AsyncMock()
    _make_session_cm(mock_session, mock_driver)

    mock_session.run.return_value = AsyncIteratorMock([
        _make_mock_record({
            "OriginalSender": "CN=sender,OU=BNP",
            "FinalRecipient": "CN=sink,OU=OFFSHORE",
            "LayerCount": 5,
            "InitialAmount": 1000000.0,
            "FinalAmount": 850000.0,
            "TotalDrift": 150000.0,
        }),
    ])

    results = await detector.detect_layering(min_hops=3)

    assert len(results) == 1
    assert results[0]["pattern"] == "LAYERING"
    assert results[0]["layer_count"] == 5
    assert results[0]["total_drift"] == 150000.0


async def test_detect_transfer_concentration_returns_results(detector_with_driver):
    detector, mock_driver = detector_with_driver

    mock_session = AsyncMock()
    _make_session_cm(mock_session, mock_driver)

    mock_session.run.return_value = AsyncIteratorMock([
        _make_mock_record({
            "Aggregator": "CN=aggregator,OU=SHELL",
            "unique_senders": 7,
            "total_transfers": 21,
            "total_received": 3500000.0,
            "avg_per_sender": 500000.0,
        }),
    ])

    results = await detector.detect_transfer_concentration()

    assert len(results) == 1
    assert results[0]["pattern"] == "TRANSFER_CONCENTRATION"
    assert results[0]["unique_senders"] == 7


async def test_run_full_scan_calls_all_patterns(detector_with_driver):
    detector, _ = detector_with_driver

    circular_results = [{"actor_dn": "actor1", "cycle_length": 3, "total_volume": 1000.0, "pattern": "CIRCULAR_FLOW"}]
    smurfing_results = [{"actor_dn": "smurf1", "transfer_count": 8, "average_amount": 5000.0, "pattern": "SMURFING"}]

    detector.detect_circular_flow = AsyncMock(return_value=circular_results)
    detector.detect_smurfing = AsyncMock(return_value=smurfing_results)
    detector.detect_layering = AsyncMock(return_value=[])
    detector.detect_transfer_concentration = AsyncMock(return_value=[])

    results = await detector.run_full_scan()

    assert "circular_flow" in results
    assert "smurfing" in results
    assert "layering" in results
    assert "transfer_concentration" in results
    assert len(results["circular_flow"]) == 1
    assert len(results["smurfing"]) == 1


async def test_neo4j_client_run_fraud_scan_no_driver():
    client = Neo4jClient()
    results = await client.run_fraud_scan()

    assert results["circular_flow"] == []
    assert results["smurfing"] == []
    assert results["layering"] == []
    assert results["transfer_concentration"] == []


async def test_neo4j_client_fraud_scan_wired_to_detector():
    client = Neo4jClient()
    mock_driver = AsyncMock()
    client._driver = mock_driver
    client._fraud_detector._driver = mock_driver

    expected = {
        "circular_flow": [],
        "smurfing": [],
        "layering": [],
        "transfer_concentration": [],
    }
    client._fraud_detector.run_full_scan = AsyncMock(return_value=expected)

    results = await client.run_fraud_scan()
    assert results == expected
    client._fraud_detector.run_full_scan.assert_awaited_once()


async def test_detect_circular_flow_depth_clamped(detector_with_driver):
    detector, mock_driver = detector_with_driver

    mock_session = AsyncMock()
    _make_session_cm(mock_session, mock_driver)
    mock_session.run.return_value = AsyncIteratorMock([])

    await detector.detect_circular_flow(depth=100)
    call_kwargs = mock_session.run.call_args[1]
    assert call_kwargs.get("depth", 0) <= 6


async def test_detect_circular_flow_neo4j_error_returns_empty(detector_with_driver):
    detector, mock_driver = detector_with_driver

    mock_session = AsyncMock()
    _make_session_cm(mock_session, mock_driver)
    mock_session.run.side_effect = Exception("Neo4j connection refused")

    results = await detector.detect_circular_flow()
    assert results == []
