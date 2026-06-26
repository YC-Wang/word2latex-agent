from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from word2latex_agent import WordToLatexAgent
from word2latex_agent.docx_reader import read_docx_paragraphs, split_into_sections

from .fixtures import make_docx


class ConversionTests(unittest.TestCase):
    def test_docx_reader_detects_headings_and_paragraphs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.docx"
            make_docx(
                source,
                [
                    ("Heading1", "Introduction"),
                    ("Normal", "This is the opening paragraph."),
                    ("Heading1", "Method"),
                    ("Normal", "This is the method paragraph."),
                ],
            )

            paragraphs = read_docx_paragraphs(source)
            sections = split_into_sections(paragraphs)

            self.assertEqual(
                [item.style for item in paragraphs],
                ["Heading 1", "Normal", "Heading 1", "Normal"],
            )
            self.assertEqual([section.title for section in sections], ["Introduction", "Method"])
            self.assertEqual(sections[0].paragraphs, ["This is the opening paragraph."])

    def test_agent_generates_overleaf_ready_project(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Introduction"),
                    ("Normal", "Paragraph with 100% coverage & details."),
                    ("Heading1", "Method"),
                    ("Normal", "Another paragraph."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)

            main_tex = result.main_tex_path.read_text(encoding="utf-8")
            first_section = result.section_files[0].read_text(encoding="utf-8")

            self.assertEqual(result.main_tex_path, output_dir / "main.tex")
            self.assertEqual(len(result.section_files), 2)
            self.assertIn(r"\tableofcontents", main_tex)
            self.assertIn(r"\input{sections/section_01_introduction}", main_tex)
            self.assertIn(r"\section{Introduction}", first_section)
            self.assertIn(r"Paragraph with 100\% coverage \& details.", first_section)


if __name__ == "__main__":
    unittest.main()
