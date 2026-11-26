"""unapply: evidence-backed candidate profiles, ranked against hidden job rubrics."""


def main() -> None:
    """Run the command-line entry point."""
    from unapply.cli import main as cli_main

    raise SystemExit(cli_main())
