"""Desktop entrypoint. Serves the API on an OS-chosen loopback port."""

import json
import os
import sys
import threading
import time

import uvicorn

from tradecopilot_agent.server.app import create_app


def listening_line(port: int) -> str:
    """Render the one stdout line the desktop shell parses.

    Args:
        port: Bound TCP port.

    Returns:
        Compact JSON with no trailing newline.
    """
    return json.dumps({"event": "listening", "port": port})


def create_server() -> uvicorn.Server:
    """Build a server bound to an ephemeral loopback port.

    Returns:
        A server that has not started yet.
    """
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=0)
    return uvicorn.Server(config)


def parent_gone(initial_parent: int, current_parent: int) -> bool:
    """Report whether the process was reparented after its shell exited.

    Args:
        initial_parent: Parent pid recorded at startup.
        current_parent: Parent pid read now.

    Returns:
        True when the parent changed.
    """
    return current_parent != initial_parent


def _watch_parent(interval: float = 2.0) -> None:
    """Exit when the desktop shell dies without killing this process.

    The shell kills the agent on normal exit. This covers a crash or a quit
    path that skips cleanup, where the OS reparents the agent to launchd or
    init. Windows is excluded because the job object covers it.

    Args:
        interval: Seconds between checks.
    """
    initial_parent = os.getppid()
    while True:
        time.sleep(interval)
        if parent_gone(initial_parent, os.getppid()):
            os._exit(0)


def main() -> None:
    """Run until the parent process kills this process."""
    server = create_server()
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    print(listening_line(port), flush=True)
    if sys.platform != "win32":
        threading.Thread(target=_watch_parent, daemon=True).start()
    thread.join()


if __name__ == "__main__":
    main()
