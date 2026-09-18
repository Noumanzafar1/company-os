"""Closed Phase 4 scope, additive to the accepted Phase 3 allowlists."""

from company_os.persistence.runtime import TABLES

RUNTIME_TABLES = TABLES | {"company_runtime_caps"}
RUNTIME_SUFFIXES = {
    "/attention",
    "/attention/{identifier}/snooze",
    "/jobs",
    "/jobs/{identifier}",
    "/jobs/{identifier}/retry",
    "/jobs/{identifier}/cancel",
    "/events",
    "/incidents",
    "/runtime-health",
    "/runtime/synthetic",
}
RUNTIME_PATHS = {"/webhooks/fake/{connection_token}", "/service/jobs/{identifier}/result"} | {
    "/v1/workspaces/{workspace_id}" + path for path in RUNTIME_SUFFIXES
}
