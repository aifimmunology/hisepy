from dataclasses import dataclass


@dataclass
class AbstractionResult:
    workflow_id: str
    status: str  # "submitted" | "saving" | "polling_build" | "deploying" | "deployed" | "failed"
    abstraction_id: str | None = None
    app_url: str | None = None
    error: str | None = None
