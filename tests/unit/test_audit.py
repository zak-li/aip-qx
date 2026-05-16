from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.features.audit.integrity_checker import IntegrityChecker
from backend.features.audit.report_generator import ReportGenerator


async def test_integrity_checker_3_real_records_all_valid(sample_provenance):
    checker = IntegrityChecker()
    report = checker.check("RWA-OBL-BANK01-2025-001", sample_provenance)
    assert report.valid is True
    assert report.total_records == 3
    assert report.tampered_count == 0

async def test_integrity_checker_detects_tampered_amount(sample_provenance):
    from dataclasses import replace
    tampered = replace(sample_provenance[1], amount=99999999.0)
    records = [sample_provenance[0], tampered, sample_provenance[2]]
    checker = IntegrityChecker()
    report_original = checker.check("RWA-OBL-BANK01-2025-001", sample_provenance)
    report_tampered = checker.check("RWA-OBL-BANK01-2025-001", records)
    original_hash = report_original.records[1].computed_hash
    tampered_hash = report_tampered.records[1].computed_hash
    assert original_hash != tampered_hash

async def test_integrity_checker_detects_wrong_action_order(sample_provenance):
    from dataclasses import replace
    wrong_first = replace(sample_provenance[2], action="GELE")
    wrong_second = replace(sample_provenance[0], action="TOKENISE")
    records = [wrong_first, wrong_second, sample_provenance[1]]
    checker = IntegrityChecker()
    report = checker.check("RWA-OBL-BANK01-2025-001", records)
    assert report.valid is False
    has_action_issue = any(
        "action" in field.lower()
        for rec in report.records
        for field in rec.tampered_fields
    )
    assert has_action_issue is True

async def test_integrity_checker_rejects_unknown_action(sample_provenance):
    from dataclasses import replace
    hacked = replace(sample_provenance[0], action="HACK")
    records = [hacked, sample_provenance[1], sample_provenance[2]]
    checker = IntegrityChecker()
    report = checker.check("RWA-OBL-BANK01-2025-001", records)
    assert report.valid is False
    has_unknown = any(
        "HACK" in field
        for rec in report.records
        for field in rec.tampered_fields
    )
    assert has_unknown is True

async def test_report_generator_returns_pdf_bytes(sample_provenance, sample_integrity_report):
    gen = ReportGenerator()
    asset_state = {
        "asset_name": "OAT BANK01 3.75% 2030",
        "isin": "FR0014004L86",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 50000000,
        "status": "GELE",
    }

    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b"", b""))
    mock_process.returncode = 0

    async def fake_exec(*args, **kwargs):
        return mock_process

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            mock_open.return_value.write = MagicMock()
            mock_open.return_value.read = MagicMock(return_value=b"%PDF-1.4 test content")

            with patch("os.path.exists", return_value=True):
                with patch("os.path.getsize", return_value=100):
                    with patch("shutil.rmtree"):
                        pdf = await gen.generate(
                            "RWA-OBL-BANK01-2025-001", asset_state,
                            sample_provenance, sample_integrity_report,
                            "sophie.lambert@amf.fr",
                        )

    assert pdf is not None

async def test_report_generator_raises_if_pdflatex_missing(sample_provenance, sample_integrity_report):
    gen = ReportGenerator()
    asset_state = {
        "asset_name": "OAT BANK01 3.75% 2030",
        "isin": "FR0014004L86",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 50000000,
        "status": "GELE",
    }

    async def fail_exec(*args, **kwargs):
        raise FileNotFoundError("pdflatex not found")

    with patch("asyncio.create_subprocess_exec", side_effect=fail_exec):
        with patch("shutil.rmtree"):
            with pytest.raises(FileNotFoundError, match="pdflatex"):
                await gen.generate(
                    "RWA-OBL-BANK01-2025-001", asset_state,
                    sample_provenance, sample_integrity_report,
                    "sophie.lambert@amf.fr",
                )

async def test_report_generator_raises_on_compilation_failure(sample_provenance, sample_integrity_report):
    gen = ReportGenerator()
    asset_state = {
        "asset_name": "OAT BANK01 3.75% 2030",
        "isin": "FR0014004L86",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 50000000,
        "status": "GELE",
    }

    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b"! LaTeX Error: line 42\nUndefined control sequence", b""))
    mock_process.returncode = 1

    async def fail_compile(*args, **kwargs):
        return mock_process

    with patch("asyncio.create_subprocess_exec", side_effect=fail_compile):
        with patch("shutil.rmtree"):
            with pytest.raises(RuntimeError, match="pdflatex"):
                await gen.generate(
                    "RWA-OBL-BANK01-2025-001", asset_state,
                    sample_provenance, sample_integrity_report,
                    "sophie.lambert@amf.fr",
                )
