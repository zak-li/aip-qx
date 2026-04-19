import json 
import logging 
from pathlib import Path 
from dataclasses import dataclass 
from uuid import UUID 

from rapidfuzz import fuzz 
from backend .config import Settings 
from backend .constants import SANCTION_MATCH_THRESHOLD 

logger =logging .getLogger (__name__ )

@dataclass (slots =True )
class SanctionMatch :
    list_name :str 
    matched_name :str 
    match_score :float 
    pep_level :int |None 

@dataclass (slots =True )
class SanctionsResult :
    hit :bool 
    matches :list [SanctionMatch ]
    screened_lists :list [str ]

class SanctionsScreener :

    def __init__ (self ,settings :Settings )->None :
        self .settings =settings 
        self .fixtures_path =Path ("database/fixtures/json/compliance_kyc_aml.json").resolve ()

    def _load_lists (self )->dict [str ,list [str ]]:
        try :
            raw_data =self .fixtures_path .read_text (encoding ="utf-8")
            data =json .loads (raw_data )
            return data .get ("sanctions_lists",{})
        except json .JSONDecodeError as exc :
            logger .error (f"Decoding target mapping structurally structurally failed: {exc }")
            return {}
        except FileNotFoundError as exc :
            logger .warning (f"File payload directly bounded absent limits: {exc }")
            return {}

    async def screen (self ,user_id :UUID ,full_name :str ,nationality :str |None =None )->SanctionsResult :
        sanctions_db =self ._load_lists ()

        lists_to_check =[
        "OFAC_SDN","UN_CONSOLIDATED","EU_CONSOLIDATED",
        "UK_HMT","PEP_LEVEL_1","PEP_LEVEL_2","PEP_LEVEL_3"
        ]

        matches :list [SanctionMatch ]=[]
        name_lower =full_name .lower ()
        hit =False 

        for list_name in lists_to_check :
            candidates =sanctions_db .get (list_name ,[])
            pep_lvl =int (list_name [-1 ])if "PEP"in list_name else None 

            for candidate in candidates :
                cand_str =candidate if isinstance (candidate ,str )else str (candidate )

                if name_lower ==cand_str .lower ():
                    matches .append (SanctionMatch (list_name ,cand_str ,100.0 ,pep_lvl ))
                    hit =True 
                    break 

                ratio =fuzz .ratio (name_lower ,cand_str .lower ())
                if ratio >SANCTION_MATCH_THRESHOLD :
                    matches .append (SanctionMatch (list_name ,cand_str ,ratio ,pep_lvl ))
                    hit =True 

        return SanctionsResult (
        hit =hit ,
        matches =matches ,
        screened_lists =lists_to_check 
        )
