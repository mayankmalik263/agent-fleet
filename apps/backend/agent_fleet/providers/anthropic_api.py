"""Future bring-your-own-key provider (design only; not active in local mode).

Design:
- Credentials live in provider_connections.encrypted_credentials as ciphertext. The key-encryption key
  comes from a secret manager (for example a cloud KMS), never from the database or .env.
- At execution time an AgentExecutor decrypts the key in memory, calls the official `anthropic` SDK
  (Messages API with tool use), and maps each response to the same Agent Fleet events the Claude Code
  runtime produces (agent.*, task.*, message.sent, tool.*, execution.usage_reported).
- Usage comes from the API response `usage` field. Costs are computed from published prices and
  labelled as estimates until reconciled with the invoice.

Nothing here runs without credentials, and the dashboard never falls back to this provider silently.
"""

from ..core.enums import ProviderName
from ..core.errors import RuntimeUnavailableError
from .base import ExecutionRuntime, ProviderHealth
from .registry import anthropic_api_health


class AnthropicApiProvider:
    name = ProviderName.ANTHROPIC_API.value
    label = "Anthropic API (bring your own key)"
    model_aliases = ("sonnet", "haiku")

    def health(self, *, refresh: bool = False) -> ProviderHealth:
        return anthropic_api_health()

    def runtime(self) -> ExecutionRuntime:
        raise RuntimeUnavailableError(
            "The Anthropic API provider is not enabled in local mode. No API key is required or used."
        )
