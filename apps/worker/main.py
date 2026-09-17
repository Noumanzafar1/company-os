import argparse
import json
import os
import signal
import threading
from datetime import UTC, datetime
from pathlib import Path

from company_os.persistence.database import check_runtime, make_engine, transaction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--stop-file", type=Path, default=Path(".local/worker.stop"))
    args = parser.parse_args()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    engine = make_engine(os.environ["WORKER_DATABASE_URL"], pool_size=1)
    stopfile = args.stop_file
    stopfile.unlink(missing_ok=True)
    try:
        while not stop.is_set():
            with transaction(engine) as conn:
                check_runtime(conn, "company_worker")
            print(
                json.dumps(
                    {
                        "service": "worker",
                        "status": "healthy",
                        "mode": "foundation",
                        "measured_at": datetime.now(UTC).isoformat(),
                    }
                ),
                flush=True,
            )
            if args.once:
                break
            for _ in range(15):
                if stop.wait(1) or stopfile.exists():
                    stop.set()
                    break
    finally:
        engine.dispose()
        print('{"service":"worker","status":"stopped"}', flush=True)


if __name__ == "__main__":
    main()
