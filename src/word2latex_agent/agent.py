"""Core agent primitives for Word-to-LaTeX conversion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ConversionResult:
    """Represents the output of a document conversion run."""

    input_path: Path
    output_path: Path
    latex: str


class WordToLatexAgent:
    """Minimal service interface for document-to-LaTeX conversion."""

    def convert(self, input_path: str | Path, output_path: str | Path) -> ConversionResult:
        source = Path(input_path)
        destination = Path(output_path)

        latex = self._render_placeholder_latex(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(latex, encoding="utf-8")

        return ConversionResult(
            input_path=source,
            output_path=destination,
            latex=latex,
        )

    def _render_placeholder_latex(self, source: Path) -> str:
        stem = source.stem.replace("_", r"\_")
        return "\n".join(
            [
                r"\documentclass{article}",
                r"\usepackage[utf8]{inputenc}",
                r"\begin{document}",
                rf"\section*{{Converted from {stem}}}",
                "Conversion pipeline placeholder.",
                r"\end{document}",
                "",
            ]
        )
