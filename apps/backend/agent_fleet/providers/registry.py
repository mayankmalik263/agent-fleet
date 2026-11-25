"""Known providers and their health. Local Claude Code is implemented; the Anthropic API provider is a
designed extension point that reports its state honestly and never pretends to execute."""

from ..core.config import get_settings
from ..core.enums import ProviderConnectionStatus, ProviderName
from .base import ProviderHealth
from .claude_cli import cached_detect


def claude_code_health(refresh: bool = False) -> ProviderHealth:
    info = cached_detect(refresh)
    if not info.found:
        status = ProviderConnectionStatus.DISCONNECTED
    elif not info.logged_in and info.found and not info.missing_flags:
        status = ProviderConnectionStatus.AUTHENTICATION_REQUIRED
    elif info.ready:
        status = ProviderConnectionStatus.CONNECTED
    else:
        status = ProviderConnectionStatus.DISCONNECTED
    message = "Ready: runs use your local Claude Code login." if info.ready else " ".join(info.problems)
    return ProviderHealth(
        provider=ProviderName.CLAUDE_CODE_LOCAL.value,
        label="Local Claude Code",
        status=status,
        message=message,
        local_mode_supported=True,
        details={
            "version": info.version,
            "executable": info.executable,
            "auth": info.auth,
            "missing_flags": info.missing_flags,
            "integration": "local development / self-hosted connector (not for commercial distribution)",
            "commercial_mode": get_settings().commercial_mode,
        },
    )


def anthropic_api_health() -> ProviderHealth:
    return ProviderHealth(
        provider=ProviderName.ANTHROPIC_API.value,
        label="Anthropic API (bring your own key)",
        status=ProviderConnectionStatus.UNSUPPORTED_IN_LOCAL_MODE,
        message=(
            "Planned extension point. Local mode does not need or store an API key. "
            "See docs/TECHNICAL_SPECIFICATION.md#provider-abstraction."
        ),
        local_mode_supported=False,
    )


def all_providers(refresh: bool = False) -> list[ProviderHealth]:
    return [claude_code_health(refresh), anthropic_api_health()]
