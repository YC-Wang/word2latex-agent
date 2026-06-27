"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import WordToLatexAgent
from .template_manager import list_templates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a Word document to LaTeX.")
    parser.add_argument("--input", type=Path, help="Path to the input .docx file")
    parser.add_argument(
        "--output",
        type=Path,
        help="Directory where the Overleaf-ready project will be created",
    )
    parser.add_argument(
        "--config",
        default=Path("config.yaml"),
        type=Path,
        help="Optional YAML configuration file",
    )
    parser.add_argument(
        "--template",
        choices=list_templates(),
        help="Optional output template override",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List available output templates and exit",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.list_templates:
        for template_name in list_templates():
            print(template_name)
        return

    if args.input is None or args.output is None:
        raise SystemExit("--input and --output are required unless --list-templates is used")

    agent = WordToLatexAgent(config_path=args.config, template_name=args.template)
    result = agent.convert(input_path=args.input, output_dir=args.output)
    print(f"Created LaTeX project at {result.output_dir}")
    print(f"Main file: {result.main_tex_path}")
