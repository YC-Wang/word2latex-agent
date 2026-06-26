from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from word2latex_agent import WordToLatexAgent
from word2latex_agent.docx_reader import read_docx_blocks, read_docx_paragraphs, split_into_sections
from word2latex_agent.models import FigureBlock, TableBlock

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
            self.assertEqual(
                [block.text for block in sections[0].blocks if hasattr(block, "text")],
                ["This is the opening paragraph."],
            )

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

    def test_table_conversion_preserves_order_and_large_tables_are_externalized(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Results"),
                    ("Normal", "Opening paragraph."),
                    ("Normal", "Table 1 Results Summary"),
                    {
                        "rows": [
                            ["Metric", "Value", "Delta", "Unit"],
                            ["Accuracy", "91", "3", "%"],
                            ["Recall", "88", "2", "%"],
                            ["Precision", "90", "4", "%"],
                            ["F1", "89", "3", "%"],
                        ]
                    },
                    ("Normal", "Closing paragraph."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)

            section_tex = result.section_files[0].read_text(encoding="utf-8")
            self.assertEqual(len(result.table_files), 1)
            self.assertIn(r"Opening paragraph.", section_tex)
            self.assertIn(r"\input{tables/", section_tex)
            self.assertIn(r"Closing paragraph.", section_tex)
            self.assertLess(section_tex.index("Opening paragraph."), section_tex.index(r"\input{tables/"))
            self.assertLess(section_tex.index(r"\input{tables/"), section_tex.index("Closing paragraph."))

            table_tex = result.table_files[0].read_text(encoding="utf-8")
            self.assertIn(r"\begin{table}[htbp]", table_tex)
            self.assertIn(r"\caption{Table 1 Results Summary}", table_tex)
            self.assertIn(r"\label{tab:results_table_1_results_summary}", table_tex)

    def test_caption_detection_and_generated_labels(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Analysis"),
                    ("Normal", "Figure 1 Model Overview"),
                    ("Normal", "Body paragraph after figure."),
                    ("Normal", "Table 2 Metrics"),
                    {"rows": [["Name", "Value"], ["BLEU", "0.71"]]},
                ],
            )

            blocks = read_docx_blocks(source)
            self.assertTrue(any(isinstance(block, FigureBlock) for block in blocks))
            self.assertTrue(any(isinstance(block, TableBlock) for block in blocks))

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")

            self.assertIn(r"\caption{Figure 1 Model Overview}", section_tex)
            self.assertIn(r"\label{fig:analysis_figure_1_model_overview}", section_tex)
            self.assertIn(r"\caption{Table 2 Metrics}", section_tex)
            self.assertIn(r"\label{tab:analysis_table_2_metrics}", section_tex)


if __name__ == "__main__":
    unittest.main()
