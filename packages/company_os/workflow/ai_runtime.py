"""One model call at a time through Phase 6A containment and fenced commands."""

import threading
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from company_os.ai.contracts import AIResult, AIRoute, AITask, ContextPack, ProviderCall, Validation
from company_os.ai.validation import cost, validate_output
from company_os.application import ai_gateway as gateway
from company_os.application import runtime
from company_os.persistence.ai import get, insert, update
from company_os.persistence.business import BusinessError
from company_os.persistence.database import transaction
from company_os.persistence.runtime import clock
from company_os.persistence.runtime import get as runtime_get
from company_os.persistence.runtime import update as runtime_update
from company_os.workflow.isolation import execute


def run_ai(
    engine: Engine,
    scope: tuple[UUID, UUID, int],
    job: dict[str, Any],
    run: dict[str, Any],
    shutdown: threading.Event | None = None,
) -> bool:
    for _ in range(2):
        try:
            with transaction(engine, *scope) as conn:
                runtime.fenced(conn, job)
                route = AIRoute.model_validate(get(conn, "ai_routes", run["route_id"])["body"])
                task = AITask.model_validate(run["task"])
                call = gateway.reserve_call(conn, job, run, route)
                context = ContextPack.model_validate(
                    get(conn, "context_packs", run["context_id"])["body"]
                )
                prompt = get(conn, "ai_registry", route.prompt_version)["body"]["text"]
                schema = get(conn, "ai_registry", route.schema_version)["body"]
                seconds = min(
                    float(task.timeout_seconds),
                    max(0.1, (task.deadline_at - clock(conn)).total_seconds()),
                )
                envelope = ProviderCall(
                    execution_id=call["id"],
                    input_hash=call["request_key"],
                    task=task,
                    context=context,
                    route=route,
                    scenario=run["scenario"],
                    ordinal=call["ordinal"],
                    prompt=prompt,
                    output_schema=schema,
                    hard_timeout_seconds=0.5 if run["scenario"] == "timeout" else seconds,
                )
        except BusinessError as error:
            with transaction(engine, *scope) as conn:
                runtime.fenced(conn, job)
                current = get(conn, "agent_runs", run["id"], lock=True)
                update(
                    conn,
                    "agent_runs",
                    current,
                    state="uncertain" if error.code == "UNCERTAIN_MODEL_CALL" else "failed",
                    error_code=error.code,
                )
                runtime.failed(conn, job, error.code)
            return True
        stopped = threading.Event()
        invalidation: list[str] = []

        def watch(
            stopped: threading.Event = stopped, invalidation: list[str] = invalidation
        ) -> None:
            while not stopped.is_set():
                try:
                    with transaction(engine, *scope) as conn:
                        conn.execute(text("SET LOCAL statement_timeout='2s'"))
                        current_job = runtime.fenced(conn, job)
                        if current_job["cancel_requested_at"]:
                            invalidation.append("CANCELLED")
                        elif not gateway.context_current(conn, run):
                            invalidation.append("STALE_CONTEXT")
                except (BusinessError, SQLAlchemyError):
                    invalidation.append("LEASE_LOST")
                if invalidation:
                    return
                stopped.wait(0.1)

        watcher = threading.Thread(target=watch, daemon=True, name="ai-fence-watch")
        watcher.start()

        def control(invalidation: list[str] = invalidation) -> str | None:
            return (
                "SHUTDOWN"
                if shutdown and shutdown.is_set()
                else invalidation[0]
                if invalidation
                else None
            )

        try:
            outcome = execute(envelope, control)
        finally:
            stopped.set()
            watcher.join(timeout=3)
        try:
            with transaction(engine, *scope) as conn:
                current_job = runtime.fenced(conn, job)
                current = get(conn, "agent_runs", run["id"], lock=True)
                call = get(conn, "model_runs", call["id"], lock=True)
                response = (
                    outcome.result.response if outcome.code == "RESULT" and outcome.result else None
                )
                price = get(conn, "ai_registry", route.price_config_version)["body"]
                actual = None
                if response and response.usage:
                    try:
                        if (
                            response.usage.input_tokens + response.usage.cache_creation_tokens
                            > task.max_input_tokens
                            or response.usage.output_tokens > task.max_output_tokens
                        ):
                            raise ValueError("INVALID_USAGE")
                        actual = cost(response.usage, price)
                        if actual > call["estimated_usd"]:
                            raise ValueError("INVALID_USAGE")
                    except ValueError:
                        actual = None
                # Definitive rejection without usage is not assumed free. Keep the
                # pessimistic hold; a separately counted retry still needs capacity.
                uncertain = response is None or response.status == "uncertain" or actual is None
                reservation = runtime_get(
                    conn, "budget_reservations", call["reservation_id"], lock=True
                )
                if uncertain:
                    runtime_update(conn, "budget_reservations", reservation, state="uncertain")
                else:
                    runtime.settle(
                        conn,
                        call["reservation_id"],
                        actual if actual is not None else Decimal(0),
                        provider=route.primary_provider,
                        task_type=task.task_type,
                        rate_version="ai:" + str(route.price_config_version),
                    )
                update(
                    conn,
                    "model_runs",
                    call,
                    status=response.status if response else "uncertain",
                    ended_at=clock(conn),
                    response_meta={
                        "usage": response.usage.model_dump()
                        if response and response.usage
                        else None,
                        "provider_request_id": response.request_id if response else None,
                        "reported_model": response.reported_model if response else None,
                        "forced": outcome.forced,
                    },
                    confirmed_usd=actual,
                    latency_ms=Decimal(str(outcome.elapsed_ms)),
                    error_code=response.error if response else outcome.code,
                )
                valid_context = (
                    gateway.context_current(conn, run) and not current_job["cancel_requested_at"]
                )
                if not response or not valid_context:
                    update(
                        conn,
                        "agent_runs",
                        current,
                        state="uncertain" if not response else "quarantined",
                        error_code=outcome.code if not response else "STALE_CONTEXT",
                    )
                    runtime.failed(conn, job, outcome.code if not response else "STALE_CONTEXT")
                    return True
                if (
                    response.status == "failed"
                    and response.error in {"rate_limit", "provider_overloaded"}
                    and call["ordinal"] < task.max_model_calls
                    and run["scenario"] != "fallback_denied"
                ):
                    update(
                        conn, "agent_runs", current, state="retry_wait", error_code=response.error
                    )
                    runtime.failed(
                        conn, job, response.error, transient=True, retry_after=response.retry_after
                    )
                    return True
                proposal, validation, repairable = (
                    validate_output(response.output, context)
                    if response.status == "completed"
                    else (
                        None,
                        Validation(
                            schema_valid=False,
                            evidence=False,
                            policy=True,
                            semantic=False,
                            defects=(response.error or response.status,),
                        ),
                        False,
                    )
                )
                if repairable and call["ordinal"] < task.max_model_calls and not uncertain:
                    runtime.audit(conn, "ai.repair_required", call["id"], run["correlation_id"])
                    continue
                result_status: Any = (
                    "proposed"
                    if proposal and not uncertain
                    else "refused"
                    if response.status == "refused"
                    else "incomplete"
                    if response.status == "incomplete"
                    else "quarantined"
                )
                if uncertain and proposal:
                    proposal = None
                    validation = Validation(
                        schema_valid=True,
                        evidence=True,
                        policy=False,
                        semantic=True,
                        defects=("INVALID_OR_UNKNOWN_USAGE",),
                    )
                result = AIResult(
                    task_id=run["id"],
                    status=result_status,
                    result=proposal,
                    claim_evidence_map=proposal.claims if proposal else (),
                    unknowns=proposal.unknowns if proposal else (),
                    uncertainties=proposal.uncertainties if proposal else (),
                    provider=route.primary_provider,
                    model_id=route.primary_model_id,
                    reported_model_version=response.reported_model,
                    route_version=run["route_id"],
                    prompt_version=route.prompt_version,
                    schema_version=route.schema_version,
                    usage=response.usage,
                    estimated_usd=call["estimated_usd"],
                    confirmed_usd=actual,
                    price_version=route.price_config_version,
                    reservation_id=call["reservation_id"],
                    latency_ms=outcome.elapsed_ms,
                    validation=validation,
                    provider_request_id=response.request_id,
                )
                saved = insert(
                    conn,
                    "ai_results",
                    {"agent_run_id": run["id"], "body": result.model_dump(mode="json")},
                )
                update(
                    conn,
                    "agent_runs",
                    current,
                    state="accepted" if result_status == "proposed" else result_status,
                    result_id=saved["id"],
                    error_code="UNAPPROVED_FALLBACK"
                    if run["scenario"] == "fallback_denied"
                    else None,
                )
                runtime.audit(conn, "ai.output_" + result_status, run["id"], run["correlation_id"])
                runtime.finish(conn, job, "succeeded")
                return True
        except BusinessError as error:
            if error.code != "STALE_FENCE":
                raise
            with transaction(engine, *scope) as conn:
                runtime.audit(
                    conn,
                    "ai.stale_completion",
                    run["id"],
                    run["correlation_id"],
                    outcome="rejected",
                )
            return True
    return True
