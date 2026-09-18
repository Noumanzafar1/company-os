import argparse
import json
import os
import signal
import threading
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

from company_os.persistence.database import check_runtime, make_engine, rows, transaction
from company_os.workflow.runtime import maintenance, run_one


def slot(scope: tuple[UUID, UUID, int], owner: str, safety: bool) -> bool:
    # One command connection plus one short lease-renewal connection per slot.
    engine = make_engine(os.environ["WORKER_DATABASE_URL"], pool_size=2)
    try:
        with transaction(engine) as conn:
            check_runtime(conn, "company_worker")
        return run_one(engine, scope, owner, safety=safety)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--stop-file", type=Path, default=Path(".local/worker.stop"))
    args = parser.parse_args()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    engine = make_engine(os.environ["WORKER_DATABASE_URL"], pool_size=1)
    instance = str(uuid4())
    args.stop_file.unlink(missing_ok=True)
    try:
        with transaction(engine) as conn:
            check_runtime(conn, "company_worker")
        with (
            ProcessPoolExecutor(max_workers=1) as safety_pool,
            ProcessPoolExecutor(max_workers=4) as normal_pool,
        ):
            pending: list[tuple[Future[bool], str]] = []
            cycle = 0
            while not stop.is_set() and not args.stop_file.exists():
                with transaction(engine) as conn:
                    contexts = rows(conn, "SELECT * FROM app.runtime_workspaces()")
                scopes = [
                    (r["principal_id"], r["workspace_id"], r["authz_epoch"]) for r in contexts
                ]
                # Round robin across authorized workspaces; both lanes independently rotate.
                if scopes:
                    scopes = scopes[cycle % len(scopes) :] + scopes[: cycle % len(scopes)]
                if cycle % 15 == 0:
                    for scope in scopes:
                        maintenance(engine, scope, instance)
                unfinished = []
                for future, lane in pending:
                    if future.done():
                        future.result()  # Fail visibly; recovery is durable.
                    else:
                        unfinished.append((future, lane))
                pending = unfinished
                for lane, pool, capacity in [
                    ("safety", safety_pool, 1),
                    ("normal", normal_pool, 4),
                ]:
                    free = capacity - sum(1 for _, kind in pending if kind == lane)
                    for index in range(free if scopes else 0):
                        pending.append(
                            (
                                pool.submit(
                                    slot,
                                    scopes[index % len(scopes)],
                                    instance + ":" + lane + ":" + str(index),
                                    lane == "safety",
                                ),
                                lane,
                            )
                        )
                if cycle % 15 == 0:
                    print(
                        json.dumps(
                            {
                                "service": "worker",
                                "status": "healthy",
                                "mode": "phase-4-fake",
                                "workspaces": len(scopes),
                            }
                        ),
                        flush=True,
                    )
                if args.once:
                    for future, _ in pending:
                        future.result()
                    break
                cycle += 1
                stop.wait(1)
    finally:
        engine.dispose()
        print('{"service":"worker","status":"stopped"}', flush=True)


if __name__ == "__main__":
    main()
