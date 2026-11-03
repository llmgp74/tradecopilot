import argparse
import threading
import webbrowser

import uvicorn

from tradecopilot_agent.config import get_settings


def main() -> None:
    """Run the TradeCopilot command line interface."""
    parser = argparse.ArgumentParser(prog="tradecopilot")
    subcommands = parser.add_subparsers(dest="command", required=True)

    serve = subcommands.add_parser("serve", help="Run the server.")
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Restart the server when the code changes.",
    )

    args = parser.parse_args()
    if args.command == "serve":
        _serve(reload=args.reload)


def _serve(*, reload: bool) -> None:
    """Start the server and open the browser once it is listening.

    Args:
        reload: Restart the server when the code changes.
    """
    settings = get_settings()
    url = f"http://{settings.host}:{settings.port}"
    if not reload:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    uvicorn.run(
        "tradecopilot_agent.server.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=reload,
    )
