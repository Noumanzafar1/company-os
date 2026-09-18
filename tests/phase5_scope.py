"""Explicit Phase 5 additions; prior scope assertions remain closed."""

from company_os.persistence.authority import TABLES

AUTHORITY_TABLES = TABLES
AUTHORITY_PATHS = {
    "/v1/workspaces/{workspace_id}" + suffix
    for suffix in {
        "/approvals",
        "/approvals/{identifier}",
        "/approvals/request",
        "/approvals/{identifier}/decide",
        "/approvals/{identifier}/execute",
        "/approvals/{identifier}/revoke",
        "/authority/freeze",
        "/authority/targets",
        "/policies",
        "/policies/activate",
        "/policies/propose",
    }
}
