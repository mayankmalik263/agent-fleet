"""Validate workspace directories. Runs may only use directories inside the configured roots."""

from pathlib import Path

from ..core.config import Settings, get_settings
from ..core.errors import ValidationFailedError


def resolve_workspace_path(raw: str | None, settings: Settings | None = None) -> str | None:
    """Return the canonical path, or raise if it is outside every allowed root."""
    if raw is None or not raw.strip():
        return None
    settings = settings or get_settings()
    candidate = Path(raw.strip()).expanduser()
    if not candidate.is_absolute():
        raise ValidationFailedError("workspace_path must be an absolute path", details={"field": "workspace_path"})
    # resolve() follows symlinks and removes "..", so a link or traversal cannot escape a root.
    resolved = candidate.resolve(strict=False)
    if not resolved.is_dir():
        raise ValidationFailedError(
            "workspace_path does not exist or is not a directory", details={"field": "workspace_path"}
        )
    for root in settings.workspace_roots:
        if resolved == root.resolve() or resolved.is_relative_to(root.resolve()):
            return str(resolved)
    raise ValidationFailedError(
        "workspace_path is outside the allowed workspace roots. Add its parent folder to "
        "AGENT_FLEET_ALLOWED_WORKSPACE_ROOTS in .env.",
        details={"field": "workspace_path"},
    )
