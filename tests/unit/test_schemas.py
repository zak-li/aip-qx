from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.features.assets.schemas import FreezeRequest, TokenizeRequest, TransferRequest


def test_tokenize_request_valid_oat_bnp():
    req = TokenizeRequest(
        asset_id="RWA-OBL-BANK01-2025-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="OAT BANK01 3.75% 2030",
        issuer_lei="R0MUWSFPU8MPRO8K5P83",
        nominal_value=Decimal("50000000"),
        currency="EUR",
        issuance_date=date(2025, 1, 15),
        justification="Tokenisation OAT emission primaire test validateur",
    )
    assert req.asset_id == "RWA-OBL-BANK01-2025-001"
    assert req.isin == "FR0014004L86"
    assert req.nominal_value == Decimal("50000000")

def test_tokenize_request_isin_too_short():
    with pytest.raises(ValidationError):
        TokenizeRequest(
            asset_id="RWA-OBL-BANK01-2025-001",
            isin="FR001",
            asset_type="OBLIGATION",
            asset_name="Test Asset",
            issuer_lei="R0MUWSFPU8MPRO8K5P83",
            nominal_value=Decimal("1000"),
            currency="EUR",
            issuance_date=date(2025, 1, 1),
            justification="Justification valide pour le test unitaire",
        )

def test_tokenize_request_isin_too_long():
    with pytest.raises(ValidationError):
        TokenizeRequest(
            asset_id="RWA-OBL-BANK01-2025-001",
            isin="FR0014004L861234",
            asset_type="OBLIGATION",
            asset_name="Test Asset",
            issuer_lei="R0MUWSFPU8MPRO8K5P83",
            nominal_value=Decimal("1000"),
            currency="EUR",
            issuance_date=date(2025, 1, 1),
            justification="Justification valide pour le test unitaire",
        )

def test_tokenize_request_invalid_asset_id_format():
    with pytest.raises(ValidationError):
        TokenizeRequest(
            asset_id="invalid-format-123",
            isin="FR0014004L86",
            asset_type="OBLIGATION",
            asset_name="Test Asset",
            issuer_lei="R0MUWSFPU8MPRO8K5P83",
            nominal_value=Decimal("1000"),
            currency="EUR",
            issuance_date=date(2025, 1, 1),
            justification="Justification valide pour le test unitaire",
        )

def test_tokenize_request_negative_nominal_value():
    with pytest.raises(ValidationError):
        TokenizeRequest(
            asset_id="RWA-OBL-BANK01-2025-001",
            isin="FR0014004L86",
            asset_type="OBLIGATION",
            asset_name="Test Asset",
            issuer_lei="R0MUWSFPU8MPRO8K5P83",
            nominal_value=Decimal("-1"),
            currency="EUR",
            issuance_date=date(2025, 1, 1),
            justification="Justification valide pour le test unitaire",
        )

def test_tokenize_request_justification_too_short():
    with pytest.raises(ValidationError):
        TokenizeRequest(
            asset_id="RWA-OBL-BANK01-2025-001",
            isin="FR0014004L86",
            asset_type="OBLIGATION",
            asset_name="Test Asset",
            issuer_lei="R0MUWSFPU8MPRO8K5P83",
            nominal_value=Decimal("1000"),
            currency="EUR",
            issuance_date=date(2025, 1, 1),
            justification="ok",
        )

def test_freeze_request_invalid_regulatory_ref_no_dashes():
    with pytest.raises(ValidationError):
        FreezeRequest(
            asset_id="RWA-OBL-BANK01-2025-001",
            reason="Investigation MIFID II art.69 reglementaire",
            regulatory_ref="AMFINV2026001",
        )

def test_transfer_request_zero_price():
    with pytest.raises(ValidationError):
        TransferRequest(
            asset_id="RWA-OBL-BANK01-2025-001",
            to_owner="sophie.lambert@amf.fr",
            price=Decimal("0"),
            justification="Cession bloc Inv01 portefeuille ESG test",
        )

def test_transfer_request_dn_too_short():
    with pytest.raises(ValidationError):
        TransferRequest(
            asset_id="RWA-OBL-BANK01-2025-001",
            to_owner="abc",
            price=Decimal("1000"),
            justification="Cession bloc Inv01 portefeuille test",
        )
