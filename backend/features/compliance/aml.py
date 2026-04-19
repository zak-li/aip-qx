import json 
import logging 
from pathlib import Path 
from dataclasses import dataclass 
from uuid import UUID 

from sqlalchemy .ext .asyncio import AsyncSession 
from sqlalchemy import select 

from backend .config import Settings 
from backend.features.compliance.models import ComplianceRecord
from backend .constants import (
MAX_AML_SCORE ,SAR_THRESHOLD ,
AML_HIGH_AMOUNT_BONUS_1 ,AML_HIGH_AMOUNT_BONUS_1_THRESHOLD ,
AML_HIGH_AMOUNT_BONUS_2 ,AML_HIGH_AMOUNT_BONUS_2_THRESHOLD 
)

logger =logging .getLogger (__name__ )

@dataclass (slots =True )
class AMLIndicators :
    jurisdiction_risk :float 
    cross_border_activity :float 
    unusual_volume :float 

@dataclass (slots =True )
class AMLResult :
    score :float 
    risk_category :str 
    blocked :bool 
    blocked_reason :str |None 
    indicators :list [str ]
    sar_required :bool 

class AMLScorer :

    def __init__ (self ,settings :Settings ,db :AsyncSession )->None :
        self .settings =settings 
        self .db =db 
        self .fixtures_path =Path ("database/fixtures/json/compliance_kyc_aml.json").resolve ()

    def _load_indicators (self ,user_id :UUID )->AMLIndicators :
        try :
            raw_data =self .fixtures_path .read_text (encoding ="utf-8")
            data =json .loads (raw_data )
            for participant in data .get ("participants",[]):
                if str(participant.get("user_id")).lower() == str(user_id).lower():
                    ind =participant .get ("aml_indicators",{})
                    return AMLIndicators (
                    jurisdiction_risk =float (ind .get ("jurisdiction_risk",0.05 )),
                    cross_border_activity =float (ind .get ("cross_border_activity",0.05 )),
                    unusual_volume =float (ind .get ("unusual_volume",0.05 ))
                    )
        except json .JSONDecodeError as exc :
            logger .error (f"AML Mock Context parsing failed dynamically: {exc }")
        except FileNotFoundError as exc :
            logger .warning (f"AML fixtures file not found: {exc }")

        return AMLIndicators (0.05 ,0.05 ,0.05 )

    async def score (self ,user_id :UUID ,amount :float ,counterparty_id :UUID )->AMLResult :
        indicators =self ._load_indicators (user_id )

        raw_score =(indicators .jurisdiction_risk *0.3 )+(indicators .cross_border_activity *0.4 )+(indicators .unusual_volume *0.3 )

        if amount >AML_HIGH_AMOUNT_BONUS_1_THRESHOLD :
            raw_score +=AML_HIGH_AMOUNT_BONUS_1 
        elif amount >AML_HIGH_AMOUNT_BONUS_2_THRESHOLD :
            raw_score +=AML_HIGH_AMOUNT_BONUS_2 

        final_score =round (raw_score ,4 )

        if final_score <0.30 :
            category ="FAIBLE"
        elif final_score <MAX_AML_SCORE :
            category ="MOYEN"
        elif final_score <=SAR_THRESHOLD :
            category ="ELEVE"
        else :
            category ="CRITIQUE"

        blocked =final_score >MAX_AML_SCORE 
        sar_required =final_score >SAR_THRESHOLD 

        reason =f"Score AML ({final_score }) excède le seuil de tolérance ({MAX_AML_SCORE })"if blocked else None 

        if final_score >0.40 :
            stmt =select (ComplianceRecord ).where (
            ComplianceRecord .participant_id ==user_id 
            ).order_by (ComplianceRecord .created_at .desc ()).limit (1 )
            result =await self .db .execute (stmt )
            record =result .scalar_one_or_none ()
            if record :
                record .aml_score =final_score 
                record .risk_category =category 
                await self .db .commit ()

        return AMLResult (
        score =final_score ,
        risk_category =category ,
        blocked =blocked ,
        blocked_reason =reason ,
        indicators =["Volume anormal configuré","Risque juridiction projeté"],
        sar_required =sar_required 
        )
