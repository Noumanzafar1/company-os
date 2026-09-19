import argparse
import json
import os
import signal
import threading
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from company_os.persistence.database import check_runtime, make_engine, rows, transaction
from company_os.workflow.runtime import maintenance, pulse, run_one


@contextmanager
def lanes(
    stop: threading.Event, capacity: int
) -> Iterator[tuple[ThreadPoolExecutor, ThreadPoolExecutor]]:
    with (
        ThreadPoolExecutor(max_workers=1) as safety,
        ThreadPoolExecutor(max_workers=capacity) as normal,
    ):
        try:
            yield safety, normal
        finally:
            stop.set()


def stopping(stop: threading.Event, stop_file: Path) -> bool:
    if stop_file.exists():
        stop.set()
    return stop.is_set()


def slot(
    scope: tuple[UUID, UUID, int],
    owner: str,
    safety: bool,
    stop: threading.Event,
    stop_file: Path,
) -> bool:
    # Command, renewal and cancellation watch use independent short transactions.
    engine = make_engine(os.environ["WORKER_DATABASE_URL"], pool_size=3)
    try:
        with transaction(engine) as conn:
            check_runtime(conn, "company_worker")
        if stopping(stop, stop_file):
            return False
        return run_one(
            engine,
            scope,
            owner,
            safety=safety,
            shutdown=stop,
            stop_claim=lambda: stopping(stop, stop_file),
        )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--stop-file", type=Path, default=Path(".local/worker.stop"))
    args = parser.parse_args()
    capacity = int(os.environ.get("LONG_EXECUTION_CAPACITY", "4"))
    if not 1 <= capacity <= 4:
        raise ValueError("LONG_EXECUTION_CAPACITY must be between 1 and 4")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    engine = make_engine(os.environ["WORKER_DATABASE_URL"], pool_size=1)
    instance = str(uuid4())
    args.stop_file.unlink(missing_ok=True)
    try:
        with transaction(engine) as conn:
            check_runtime(conn, "company_worker")
        with lanes(stop, capacity) as (safety_pool, normal_pool):
            pending: list[tuple[Future[bool], str]] = []
            cycle = 0
            while not stopping(stop, args.stop_file):
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
                        with transaction(engine, *scope) as conn:
                            pulse(conn, "long_pool", instance + ":" + str(capacity))
                unfinished = []
                for future, lane in pending:
                    if future.done():
                        future.result()  # Fail visibly; recovery is durable.
                    else:
                        unfinished.append((future, lane))
                pending = unfinished
                for lane, pool, lane_capacity in [
                    ("safety", safety_pool, 1),
                    ("normal", normal_pool, capacity),
                ]:
                    free = lane_capacity - sum(1 for _, kind in pending if kind == lane)
                    for index in range(free if scopes else 0):
                        if stopping(stop, args.stop_file):
                            break
                        pending.append(
                            (
                                pool.submit(
                                    slot,
                                    scopes[index % len(scopes)],
                                    instance + ":" + lane + ":" + str(index),
                                    lane == "safety",
                                    stop,
                                    args.stop_file,
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
                                "mode": "phase-6a-synthetic",
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
                stopping(stop, args.stop_file)
    finally:
        engine.dispose()
        print('{"service":"worker","status":"stopped"}', flush=True)


if __name__ == "__main__":
    main()
