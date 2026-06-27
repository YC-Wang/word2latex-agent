"""Template discovery and rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import parse_simple_yaml

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
SUPPORTED_TEMPLATES = [
    "generic_article",
    "generic_report",
    "copernicus",
    "agu",
    "springer",
    "nature",
]


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    """Resolved template assets and metadata."""

    name: str
    path: Path
    metadata: dict[str, object]
    main_template: str
    preamble_template: str


def list_templates() -> list[str]:
    """Return supported template names in stable order."""
    return list(SUPPORTED_TEMPLATES)


def load_template(template_name: str) -> TemplateDefinition:
    """Load a template definition from disk."""
    if template_name not in SUPPORTED_TEMPLATES:
        supported = ", ".join(SUPPORTED_TEMPLATES)
        raise ValueError(f"Unknown template '{template_name}'. Supported templates: {supported}")

    template_path = TEMPLATES_DIR / template_name
    metadata_path = template_path / "metadata.yaml"
    main_path = template_path / "main.tex.j2"
    preamble_path = template_path / "preamble.tex.j2"

    if not metadata_path.exists() or not main_path.exists() or not preamble_path.exists():
        raise ValueError(f"Template '{template_name}' is incomplete at {template_path}")

    metadata = parse_simple_yaml(metadata_path.read_text(encoding="utf-8"))
    return TemplateDefinition(
        name=template_name,
        path=template_path,
        metadata=metadata,
        main_template=main_path.read_text(encoding="utf-8"),
        preamble_template=preamble_path.read_text(encoding="utf-8"),
    )


def render_template(template_text: str, values: dict[str, str]) -> str:
    """Render a minimal placeholder-based template."""
    rendered = template_text
    for key, value in values.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered
