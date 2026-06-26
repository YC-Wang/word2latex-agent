from pathlib import Path

from word2latex_agent import WordToLatexAgent


def test_convert_writes_placeholder_latex(tmp_path: Path) -> None:
    source = tmp_path / "example.docx"
    destination = tmp_path / "out" / "example.tex"
    source.write_bytes(b"placeholder docx bytes")

    result = WordToLatexAgent().convert(source, destination)

    assert result.input_path == source
    assert result.output_path == destination
    assert destination.exists()
    assert r"\documentclass{article}" in result.latex
    assert "Converted from example" in destination.read_text(encoding="utf-8")
