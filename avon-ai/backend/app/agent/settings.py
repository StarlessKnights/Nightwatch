from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    enabled: bool = True
    base_url: str = "https://integrate.api.nvidia.com/v1"
    api_key: SecretStr = SecretStr("")
    routine_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    reasoning_model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b"
    timeout_s: float = Field(default=20, ge=1, le=60)
    min_interval_s: float = Field(default=15, ge=1, le=3600)
    max_tokens: int = Field(default=2048, ge=256, le=8192)
    audit_path: Path = Path(__file__).resolve().parents[3] / "data" / "agent" / "audit.sqlite3"

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return cls(enabled=os.getenv("AVON_AGENT_ENABLED", "true").lower() in ("true", "1", "yes"),
                   api_key=os.getenv("NVIDIA_API_KEY", ""),
                   **{name: os.environ[env] for name, env in {
                       "base_url": "AVON_AGENT_BASE_URL", "routine_model": "AVON_AGENT_ROUTINE_MODEL",
                       "reasoning_model": "AVON_AGENT_REASONING_MODEL", "timeout_s": "AVON_AGENT_TIMEOUT_S",
                       "min_interval_s": "AVON_AGENT_MIN_INTERVAL_S", "max_tokens": "AVON_AGENT_MAX_TOKENS",
                   }.items() if env in os.environ})
