"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import WordToLatexAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a Word document to LaTeX.")
    parser.add_argument("--input", required=True, type=Path, help="Path to the input .docx file")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directory where the Overleaf-ready project will be created",
    )
    parser.add_argument(
        "--config",
        default=Path("config.yaml"),
        type=Path,
        help="Optional YAML configuration file",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent = WordToLatexAgent(config_path=args.config)
    result = agent.convert(input_path=args.input, output_dir=args.output)
    print(f"Created LaTeX project at {result.output_dir}")
    print(f"Main file: {result.main_tex_path}")
