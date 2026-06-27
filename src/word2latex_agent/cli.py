"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .agent import WordToLatexAgent
from .config import load_config
from .overleaf_sync import OverleafSyncError, sync_to_overleaf
from .qa_checker import check_project
from .template_manager import list_templates

WORKFLOW_TARGET = "__WORKFLOW__"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert the default manuscript in input/report.docx, or a supplied Word file, into an Overleaf-ready LaTeX project."
    )
    parser.add_argument("--input", type=Path, help="Path to the input .docx file. Defaults to input/report.docx.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Directory where the Overleaf-ready project will be created. Defaults to output/.",
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
        nargs="?",
        const=WORKFLOW_TARGET,
        help="Validate an existing generated LaTeX project, or validate the generated workflow output",
    )
    parser.add_argument(
        "--sync-overleaf",
        nargs="?",
        const=WORKFLOW_TARGET,
        help="Push an existing generated LaTeX project, or push the generated workflow output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show sync commands without executing them",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.list_templates:
        for template_name in list_templates():
            print(template_name)
        return

    if args.check not in (None, WORKFLOW_TARGET):
        result = check_project(Path(args.check))
        print(
            f"{result.status} failures={len(result.failures)} warnings={len(result.warnings)} report={result.report_path}"
        )
        return

    if args.sync_overleaf not in (None, WORKFLOW_TARGET):
        try:
            result = sync_to_overleaf(
                Path(args.sync_overleaf),
                config,
                dry_run=_resolve_dry_run(args.dry_run, config),
            )
        except OverleafSyncError as error:
            raise SystemExit(str(error)) from error
        if result.dry_run:
            print("DRY-RUN")
            for command in result.commands:
                print(" ".join(command))
        print(result.message)
        return

    workflow_input = _resolve_input_path(args.input, config)
    workflow_output = _resolve_output_path(args.output, config)
    template_name = args.template or _resolve_default_template(config)
    dry_run = _resolve_dry_run(args.dry_run, config)

    try:
        agent = WordToLatexAgent(config_path=args.config, template_name=template_name)
        conversion_result = agent.convert(input_path=workflow_input, output_dir=workflow_output)
        qa_result = None
        sync_status = "SKIPPED"

        if args.check == WORKFLOW_TARGET:
            qa_result = check_project(conversion_result.output_dir)
            if qa_result.status == "FAIL" and args.sync_overleaf == WORKFLOW_TARGET:
                sync_status = "SKIPPED (QA failed)"
            elif args.sync_overleaf == WORKFLOW_TARGET:
                sync_result = sync_to_overleaf(
                    conversion_result.output_dir,
                    config,
                    dry_run=dry_run,
                )
                sync_status = "DRY-RUN" if sync_result.dry_run else "SYNCED"
                if sync_result.dry_run:
                    print("DRY-RUN")
                    for command in sync_result.commands:
                        print(" ".join(command))
                print(sync_result.message)
        elif args.sync_overleaf == WORKFLOW_TARGET:
            sync_result = sync_to_overleaf(
                conversion_result.output_dir,
                config,
                dry_run=dry_run,
            )
            sync_status = "DRY-RUN" if sync_result.dry_run else "SYNCED"
            if sync_result.dry_run:
                print("DRY-RUN")
                for command in sync_result.commands:
                    print(" ".join(command))
            print(sync_result.message)

        _print_workflow_summary(conversion_result, qa_result.status if qa_result else "SKIPPED", sync_status)
    except OverleafSyncError as error:
        raise SystemExit(str(error)) from error
    except Exception as error:
        raise SystemExit(f"Workflow failed: {error}") from error


def _resolve_input_path(input_path: Path | None, config: dict[str, Any]) -> Path:
    if input_path is not None:
        return input_path
    workflow = config.get("workflow", {})
    default_input_file = "input/report.docx"
    if isinstance(workflow, dict):
        default_input_file = str(workflow.get("default_input_file", "input/report.docx"))
    return Path(default_input_file)


def _resolve_output_path(output_path: Path | None, config: dict[str, Any]) -> Path:
    if output_path is not None:
        return output_path
    workflow = config.get("workflow", {})
    default_output_folder = "output"
    if isinstance(workflow, dict):
        default_output_folder = str(workflow.get("default_output_folder", "output"))
    return Path(default_output_folder)


def _resolve_default_template(config: dict[str, Any]) -> str | None:
    workflow = config.get("workflow", {})
    if isinstance(workflow, dict):
        default_template = workflow.get("default_template")
        if isinstance(default_template, str) and default_template.strip():
            return default_template.strip()
    template = config.get("template")
    if isinstance(template, str) and template.strip():
        return template.strip()
    return None


def _resolve_dry_run(cli_dry_run: bool, config: dict[str, Any]) -> bool:
    if cli_dry_run:
        return True
    workflow = config.get("workflow", {})
    if isinstance(workflow, dict):
        return bool(workflow.get("dry_run", False))
    return False


def _print_workflow_summary(
    conversion_result: Any,
    qa_status: str,
    sync_status: str,
) -> None:
    generated_files = [
        conversion_result.main_tex_path,
        conversion_result.preamble_path,
        conversion_result.bibliography_path,
        *conversion_result.section_files,
        *conversion_result.figure_files,
        *conversion_result.table_files,
    ]
    print(f"Created LaTeX project at {conversion_result.output_dir}")
    print(f"Main file: {conversion_result.main_tex_path}")
    print("Workflow Summary")
    print(f"Generated files: {len(generated_files)}")
    for path in generated_files:
        print(f"- {path}")
    print(f"Sections: {conversion_result.section_count}")
    print(f"Figures: {conversion_result.figure_count}")
    print(f"Tables: {conversion_result.table_count}")
    print(f"Citations: {conversion_result.citation_count}")
    print(f"QA status: {qa_status}")
    print(f"Overleaf sync status: {sync_status}")
