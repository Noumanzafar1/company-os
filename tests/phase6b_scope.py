AI_TABLES = {
    "agent_runs",
    "model_runs",
    "context_packs",
    "ai_routes",
    "ai_route_states",
    "ai_registry",
    "ai_results",
    "ai_evaluations",
    "ai_evaluation_batches",
    "ai_provider_connections",
    "ai_fixture_sources",
}
AI_PATHS = {
    "/v1/workspaces/{workspace_id}" + suffix
    for suffix in (
        "/ai-tasks",
        "/ai-tasks/{identifier}",
        "/ai-health",
        "/ai-evaluations",
        "/ai-routes/propose",
        "/ai-routes/{identifier}/promote",
        "/ai-tasks/{identifier}/revoke-context",
    )
}
