import os
from pydantic import BaseModel


class AwittivationsEntity(BaseModel):
    legal_name: str = "Awittivations LLC"
    duns: str
    uei: str    # SAM.gov — required for all federal awards since 2022
    ein: str


def get_entity() -> AwittivationsEntity:
    return AwittivationsEntity(
        duns=os.getenv("AWITTIVATIONS_DUNS", "14-4151378"),
        uei=os.getenv("AWITTIVATIONS_UEI",  "L6H1T8L7ZJC6"),
        ein=os.getenv("AWITTIVATIONS_EIN",   "900158942"),
    )
