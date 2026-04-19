from unittest.mock import AsyncMock, patch
from dataclasses import replace

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.audit.integrity_checker import IntegrityChecker

async def test_generate_audit_report_pdf_latex(
    test_client: AsyncClient,
    token_sophie_lambert: str,
    async_session: AsyncSession,
    test_org, test_user_thomas, test_amf_org, test_user_sophie,
    sample_provenance, sample_integrity_report,
):
    mock_audit_trail = AsyncMock()
    mock_audit_trail.get_provenance = AsyncMock(return_value=sample_provenance)
    mock_audit_trail.get_asset_state = AsyncMock(return_value={
        "asset_name": "OAT BNP 3.75% 2030",
        "isin": "FR0014004L86",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 50000000,
        "status": "GELE",
    })

    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b"%PDF-1.4 mock pdf content", b""))
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        checker = IntegrityChecker()
        report = checker.check("RWA-OBL-BNP-2025-001", sample_provenance)

    assert report.valid is True
    assert report.total_records == 3

async def test_integrity_report_detects_tampered_record(sample_provenance):
    tampered = replace(sample_provenance[1], amount=99999999.0)
    records = [sample_provenance[0], tampered, sample_provenance[2]]

    checker = IntegrityChecker()
    report_original = checker.check("RWA-OBL-BNP-2025-001", sample_provenance)
    report_tampered = checker.check("RWA-OBL-BNP-2025-001", records)

    assert report_original.records[1].computed_hash != report_tampered.records[1].computed_hash
