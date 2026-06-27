"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import WordToLatexAgent
from .config import load_config
from .overleaf_sync import OverleafSyncError, sync_to_overleaf
from .qa_checker import check_project
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
    parser.add_argument(
        "--check",
        type=Path,
        help="Validate an existing generated LaTeX project and write QA_REPORT.md",
    )
    parser.add_argument(
        "--sync-overleaf",
        type=Path,
        help="Push an existing generated LaTeX project to the configured Overleaf Git remote",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show sync commands without executing them",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.list_templates:
        for template_name in list_templates():
            print(template_name)
        return

    if args.check is not None:
        result = check_project(args.check)
        print(
            f"{result.status} failures={len(result.failures)} warnings={len(result.warnings)} report={result.report_path}"
        )
        return

    if args.sync_overleaf is not None:
        config = load_config(args.config)
        try:
            result = sync_to_overleaf(args.sync_overleaf, config, dry_run=args.dry_run)
        except OverleafSyncError as error:
            raise SystemExit(str(error)) from error
        if result.dry_run:
            print("DRY-RUN")
            for command in result.commands:
                print(" ".join(command))
        print(result.message)
        return

    if args.input is None or args.output is None:
        raise SystemExit(
            "--input and --output are required unless --list-templates, --check, or --sync-overleaf is used"
        )

    agent = WordToLatexAgent(config_path=args.config, template_name=args.template)
    result = agent.convert(input_path=args.input, output_dir=args.output)
    print(f"Created LaTeX project at {result.output_dir}")
    print(f"Main file: {result.main_tex_path}")
