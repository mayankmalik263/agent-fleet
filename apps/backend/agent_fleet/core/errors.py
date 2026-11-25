"""Domain errors. The REST API and the MCP server map these to their own error formats."""


class AgentFleetError(Exception):
    code = "error"
    http_status = 400

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AgentFleetError):
    code = "not_found"
    http_status = 404


class ValidationFailedError(AgentFleetError):
    code = "validation_failed"
    http_status = 422


class InvalidTransitionError(AgentFleetError):
    code = "invalid_transition"
    http_status = 409


class ConflictError(AgentFleetError):
    code = "conflict"
    http_status = 409


class LimitExceededError(AgentFleetError):
    code = "limit_exceeded"
    http_status = 429


class RuntimeUnavailableError(AgentFleetError):
    code = "runtime_unavailable"
    http_status = 503
