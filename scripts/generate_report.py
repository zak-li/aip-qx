import asyncio
import os
from datetime import datetime, timezone
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.features.audit.trail import ProvenanceRecord
from backend.features.audit.integrity_checker import IntegrityChecker
from backend.features.audit.report_generator import ReportGenerator

async def main():
    print("Prepping dummy data for report...")
    
    asset_id = "RWA-OBL-BNP-2025-001"
    asset_state = {
        "asset_id": asset_id,
        "isin": "FR0014004L86",
        "asset_type": "OBLIGATION",
        "asset_name": "OAT BNP 3.75% 2030",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 50000000,
        "current_value": 50000000,
        "currency": "EUR",
        "status": "GELE",
    }
    
    provenance = [
        ProvenanceRecord(
            tx_id="185861c04e4744c0c10f07ac82011b1534fe3a7642507db322172ab39fa2ad43",
            timestamp=datetime.now(timezone.utc),
            actor_msp="BANK01MSP",
            actor_dn="CN=Admin@bank01.finance-trust.com,OU=admin",
            action="TOKENISE",
            from_owner="",
            to_owner="CN=Admin@bank01.finance-trust.com,OU=admin",
            amount=50000000.0,
            justification="Tokenisation OAT emission primaire",
            block_number=1,
        ),
        ProvenanceRecord(
            tx_id="7a4508a19663ea42115d16ef010048636c3b0670c62a0706731a006a9afe4611",
            timestamp=datetime.now(timezone.utc),
            actor_msp="BANK01MSP",
            actor_dn="CN=Admin@bank01.finance-trust.com,OU=admin",
            action="TRANSFERE",
            from_owner="CN=Admin@bank01.finance-trust.com,OU=admin",
            to_owner="CN=pierre.moreau,OU=AXA-IM",
            amount=24739375.0,
            justification="Cession bloc Inv01 portefeuille ESG",
            block_number=2,
        )
    ]
    
    checker = IntegrityChecker()
    integrity = checker.check(asset_id, provenance)
    
    gen = ReportGenerator()
    generated_by = "Admin@amf-regulateur.finance-trust.com"
    
    tex_content = gen._build_tex(asset_id, asset_state, provenance, integrity, generated_by, "--- TEX SOURCE CODE ---")
    
    tex_path = os.path.join(os.path.dirname(__file__), "..", "report_source.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex_content)
    print(f"LaTeX source generated: {tex_path}")
    
    print("Compiling PDF via ReportGenerator...")
    try:
        pdf_bytes = await gen.generate(asset_id, asset_state, provenance, integrity, generated_by)
        pdf_path = os.path.join(os.path.dirname(__file__), "..", "audit_RWA-OBL-BNP-2025-001.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"PDF generated: {pdf_path}")
    except Exception as e:
        print(f"Error compiling PDF (is pdflatex installed?): {e}")

if __name__ == "__main__":
    asyncio.run(main())
