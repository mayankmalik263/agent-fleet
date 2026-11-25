"""Application settings. All values come from environment variables with the AGENT_FLEET_ prefix."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/backend/agent_fleet/core/config.py -> repository root is four levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "backend"
DATA_DIR = REPO_ROOT / "data"


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_FLEET_", env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Persistence. data_dir holds per-run files (MCP config, agent definitions) and default workspaces.
    data_dir: Path = DATA_DIR
    database_url: str = f"sqlite:///{(DATA_DIR / 'agent_fleet.sqlite3').as_posix()}"
    sqlite_busy_timeout_ms: int = 15_000

    # REST API
    api_host: str = "127.0.0.1"
    api_port: int = 8420
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    log_level: str = "INFO"

    # Local runner
    runner_name: str = "local-runner"
    runner_poll_seconds: float = 2.0
    runner_lease_seconds: int = 90
    runner_max_concurrent_runs: int = Field(default=1, ge=1, le=8)
    run_timeout_seconds: int = Field(default=1800, ge=30)
    run_max_attempts: int = Field(default=2, ge=1, le=5)
    max_concurrent_agents: int = Field(default=4, ge=1, le=20)

    # Claude Code runtime
    claude_path: str | None = None
    claude_detect_timeout_seconds: float = 20.0
    allowed_workspace_roots: str = ""
    allow_web_tools: bool = False
    # Test runners (pytest, npm test) execute project code; add them only for trusted workspaces.
    edit_bash_allowlist: str = "git status,git diff *,git log *"
    keep_api_key_env: bool = False

    # Commercial use of the local Claude Code connector stays off until provider terms are reviewed.
    commercial_mode: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return _split(self.cors_origins)

    @property
    def workspace_roots(self) -> list[Path]:
        roots = [Path(p).expanduser().resolve() for p in _split(self.allowed_workspace_roots)]
        return [self.data_dir / "workspaces", *roots]

    @property
    def edit_bash_patterns(self) -> list[str]:
        return _split(self.edit_bash_allowlist)

    @property
    def api_base_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
