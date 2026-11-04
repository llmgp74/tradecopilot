"""Command line entry point for serving the API and exporting its schema."""

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn
import yaml

from tradecopilot_agent.config import get_settings
from tradecopilot_agent.server.app import create_app


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

    export = subcommands.add_parser(
        "openapi", help="Write the OpenAPI document to a file."
    )
    export.add_argument(
        "--output",
        type=Path,
        default=Path("docs/openapi.yaml"),
        help="Destination path.",
    )

    args = parser.parse_args()
    if args.command == "serve":
        _serve(reload=args.reload)
    elif args.command == "openapi":
        _export_openapi(args.output)


def _export_openapi(output: Path) -> None:
    """Write the application's OpenAPI document as YAML.

    Args:
        output: Destination file. Parent directories are created.
    """
    schema = create_app().openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(schema, sort_keys=False), encoding="utf-8")


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
