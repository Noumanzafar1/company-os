"""Cross-platform local launcher with cooperative shutdown, no background jobs."""

import argparse
import asyncio
from pathlib import Path

import uvicorn


async def serve(port: int, stop_file: Path) -> None:
    stop_file.unlink(missing_ok=True)
    server = uvicorn.Server(
        uvicorn.Config("apps.api.main:app", host="127.0.0.1", port=port, access_log=False)
    )

    async def watch_stop() -> None:
        while not server.should_exit:
            if stop_file.exists():
                server.should_exit = True
                return
            await asyncio.sleep(0.2)

    watcher = asyncio.create_task(watch_stop())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--stop-file", type=Path, default=Path(".local/api.stop"))
    args = parser.parse_args()
    asyncio.run(serve(args.port, args.stop_file))


if __name__ == "__main__":
    main()
