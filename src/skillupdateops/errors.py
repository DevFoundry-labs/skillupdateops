"""Typed errors and stable CLI exit codes."""


class SkillOpsError(Exception):
    """Base error for expected, actionable failures."""


class ConfigurationError(SkillOpsError):
    """Configuration is missing or invalid."""


class SecurityError(SkillOpsError):
    """An unsafe filesystem or source operation was rejected."""


class SourceError(SkillOpsError):
    """A source could not be acquired reproducibly."""


class ApprovalError(SkillOpsError):
    """A required exact-hash approval is absent or invalid."""


class PolicyBlocked(SkillOpsError):
    """Policy prevents a workflow transition."""


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CHANGES = 2
EXIT_BLOCKED = 3
EXIT_DRIFT = 4
