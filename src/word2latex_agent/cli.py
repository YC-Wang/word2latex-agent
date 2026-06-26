"""Command-line entry point for the Word-to-LaTeX agent."""

from __future__ import annotations

from pathlib import Path

import click

from .agent import WordToLatexAgent


@click.command()
@click.option("--input", "input_path", required=True, type=click.Path(path_type=Path))
@click.option("--output", "output_path", required=True, type=click.Path(path_type=Path))
def main(input_path: Path, output_path: Path) -> None:
    """Convert a Word document into LaTeX."""
    agent = WordToLatexAgent()
    result = agent.convert(input_path=input_path, output_path=output_path)
    click.echo(f"Wrote LaTeX output to {result.output_path}")


if __name__ == "__main__":
    main()
