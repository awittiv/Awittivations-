from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    anthropic_api_key: str
    sqlite_path: str = str(Path(__file__).resolve().parent.parent / "aurax.db")
    use_local_db: bool = True

    # optional — only needed when use_local_db=false
    allium_api_key: str = ""
    graph_api_key: str = ""
    aave_subgraph_id: str = "Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL57s"

    model_config = {"env_file": str(_ENV_FILE)}


settings = Settings()
