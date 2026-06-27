import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from word2latex_agent import WordToLatexAgent
from word2latex_agent.citations import convert_text_citations
from word2latex_agent.cli import build_parser
from word2latex_agent.docx_reader import read_docx_blocks, read_docx_paragraphs, split_into_sections
from word2latex_agent.models import EquationBlock, FigureBlock, ImageBlock, TableBlock
from word2latex_agent.overleaf_sync import OverleafSyncError, sync_to_overleaf
from word2latex_agent.qa_checker import check_project
from word2latex_agent.template_manager import list_templates

from .fixtures import make_docx


class ConversionTests(unittest.TestCase):
    def test_supported_templates_are_listed(self) -> None:
        self.assertEqual(
            list_templates(),
            ["generic_article", "generic_report", "copernicus", "agu", "springer", "nature"],
        )

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
            preamble = result.preamble_path.read_text(encoding="utf-8")

            self.assertEqual(result.main_tex_path, output_dir / "main.tex")
            self.assertEqual(len(result.section_files), 2)
            self.assertTrue((output_dir / "sections").is_dir())
            self.assertTrue((output_dir / "figures").is_dir())
            self.assertTrue((output_dir / "tables").is_dir())
            self.assertIn(r"\tableofcontents", main_tex)
            self.assertIn(r"\documentclass{article}", main_tex)
            self.assertIn(r"\input{preamble}", main_tex)
            self.assertIn(r"\begin{document}", main_tex)
            self.assertIn(r"\title{Converted Word Document}", main_tex)
            self.assertIn(r"\author{word2latex-agent}", main_tex)
            self.assertIn(r"\date{\today}", main_tex)
            self.assertIn(r"\maketitle", main_tex)
            self.assertIn(r"\input{sections/section_01_introduction}", main_tex)
            self.assertIn(r"\bibliographystyle{plainnat}", main_tex)
            self.assertIn(r"\bibliography{references}", main_tex)
            self.assertIn(r"\end{document}", main_tex)
            self.assertIn(r"\section{Introduction}", first_section)
            self.assertIn(r"Paragraph with 100\% coverage \& details.", first_section)
            self.assertIn(r"\usepackage{graphicx}", preamble)
            self.assertIn(r"\usepackage{natbib}", preamble)
            self.assertIn(r"\usepackage{booktabs}", preamble)
            self.assertIn(r"\usepackage{longtable}", preamble)
            self.assertIn(r"\usepackage{amsmath}", preamble)
            self.assertIn(r"\usepackage{amssymb}", preamble)
            self.assertIn(r"\usepackage{hyperref}", preamble)
            self.assertIn(r"\usepackage[margin=1in]{geometry}", preamble)

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

    def test_citation_detection_and_bibliography_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Related Work"),
                    (
                        "Normal",
                        "Prior work includes (Wang et al., 2024) and Wang et al. (2024).",
                    ),
                    (
                        "Normal",
                        "Benchmarks were reported in (Coppola et al., 2021; Davolio et al., 2016).",
                    ),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")
            bibliography = result.bibliography_path.read_text(encoding="utf-8")
            preamble = result.preamble_path.read_text(encoding="utf-8")

            self.assertIn(r"\citep{wang2024}", section_tex)
            self.assertIn(r"\citet{wang2024}", section_tex)
            self.assertIn(r"\citep{coppola2021,davolio2016}", section_tex)
            self.assertIn(r"\usepackage{natbib}", preamble)
            self.assertIn("@article{wang2024,", bibliography)
            self.assertIn("@article{coppola2021,", bibliography)
            self.assertIn("@article{davolio2016,", bibliography)

    def test_convert_text_citations_handles_supported_patterns(self) -> None:
        converted, citations = convert_text_citations(
            "See (Wang et al., 2024), Wang et al. (2024), and (Coppola et al., 2021; Davolio et al., 2016)."
        )

        self.assertIn(r"\citep{wang2024}", converted)
        self.assertIn(r"\citet{wang2024}", converted)
        self.assertIn(r"\citep{coppola2021,davolio2016}", converted)
        self.assertEqual(
            sorted(citation.key for citation in citations),
            ["coppola2021", "davolio2016", "wang2024"],
        )

    def test_detects_equations_from_omml(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.docx"
            make_docx(
                source,
                [
                    ("Heading1", "Equations"),
                    {"equation": {"kind": "fraction", "numerator": "a+b", "denominator": "c"}},
                    ("Normal", "Trailing paragraph."),
                ],
            )

            blocks = read_docx_blocks(source)

            self.assertTrue(any(isinstance(block, EquationBlock) for block in blocks))
            equation_block = next(block for block in blocks if isinstance(block, EquationBlock))
            self.assertEqual(equation_block.latex, r"\frac{a+b}{c}")

    def test_preserves_equation_placeholder_when_conversion_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Equations"),
                    {"equation": {"kind": "unsupported"}},
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")

            self.assertIn(r"\begin{equation}", section_tex)
            self.assertIn(r"% TODO: Equation could not be converted", section_tex)
            self.assertIn(r"\end{equation}", section_tex)

    def test_generates_equation_labels_and_preserves_order(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Equations"),
                    ("Normal", "Before equation."),
                    {"equation": {"kind": "superscript", "base": "x", "sup": "2"}},
                    ("Normal", "After equation."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")

            self.assertIn(r"\label{eq:equations_x_2}", section_tex)
            self.assertIn(r"x^{2}", section_tex)
            self.assertLess(section_tex.index("Before equation."), section_tex.index(r"\begin{equation}"))
            self.assertLess(section_tex.index(r"\end{equation}"), section_tex.index("After equation."))

    def test_extracts_embedded_images_and_generates_filenames(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Figures"),
                    {"image": {"filename": "source.png", "bytes": b"\x89PNG\r\n\x1a\nfakepng"}},
                    {"image": {"filename": "photo.jpg", "bytes": b"\xff\xd8\xfffakejpg"}},
                ],
            )

            blocks = read_docx_blocks(source)
            self.assertEqual(sum(isinstance(block, ImageBlock) for block in blocks), 2)

            result = WordToLatexAgent().convert(source, output_dir)

            self.assertEqual([path.name for path in result.figure_files], ["figure_001.png", "figure_002.jpg"])
            self.assertEqual(result.figure_files[0].read_bytes(), b"\x89PNG\r\n\x1a\nfakepng")
            self.assertEqual(result.figure_files[1].read_bytes(), b"\xff\xd8\xfffakejpg")

    def test_generates_includegraphics_and_matches_caption(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Figures"),
                    ("Normal", "Figure 1 Pipeline Overview"),
                    {"image": {"filename": "diagram.png", "bytes": b"\x89PNG\r\n\x1a\ndiagram"}},
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")
            preamble = result.preamble_path.read_text(encoding="utf-8")

            self.assertIn(r"\includegraphics[width=\linewidth]{figures/figure_001.png}", section_tex)
            self.assertIn(r"\caption{Figure 1 Pipeline Overview}", section_tex)
            self.assertIn(r"\label{fig:figures_figure_1_pipeline_overview}", section_tex)
            self.assertIn(r"\usepackage{graphicx}", preamble)

    def test_inserts_todo_caption_when_matching_is_uncertain(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Figures"),
                    {"image": {"filename": "uncaptioned.jpeg", "bytes": b"\xff\xd8\xffjpeg"}},
                    ("Normal", "Body paragraph after image."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")

            self.assertIn(r"\includegraphics[width=\linewidth]{figures/figure_001.jpeg}", section_tex)
            self.assertIn(r"\caption{TODO: Add caption}", section_tex)

    def test_overleaf_template_uses_configured_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            config_path = temp_path / "custom_config.yaml"
            make_docx(
                source,
                [
                    ("Heading1", "Intro"),
                    ("Normal", "Configured project."),
                ],
            )
            config_path.write_text(
                "\n".join(
                    [
                        "project:",
                        '  title: "My Overleaf Project"',
                        '  author: "Test Author"',
                        '  date: "2026-01-15"',
                        "latex:",
                        '  document_class: "report"',
                        "  include_toc: false",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = WordToLatexAgent(config_path=config_path).convert(source, output_dir)
            main_tex = result.main_tex_path.read_text(encoding="utf-8")

            self.assertIn(r"\documentclass{report}", main_tex)
            self.assertIn(r"\title{My Overleaf Project}", main_tex)
            self.assertIn(r"\author{Test Author}", main_tex)
            self.assertIn(r"\date{2026-01-15}", main_tex)
            self.assertNotIn(r"\tableofcontents", main_tex)

    def test_main_tex_has_overleaf_ready_structure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Intro"),
                    ("Normal", "Body text."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            main_tex = result.main_tex_path.read_text(encoding="utf-8")

            documentclass_index = main_tex.index(r"\documentclass{article}")
            preamble_index = main_tex.index(r"\input{preamble}")
            begin_document_index = main_tex.index(r"\begin{document}")
            title_index = main_tex.index(r"\title{Converted Word Document}")
            maketitle_index = main_tex.index(r"\maketitle")
            section_index = main_tex.index(r"\input{sections/section_01_intro}")
            bibliography_style_index = main_tex.index(r"\bibliographystyle{plainnat}")
            bibliography_index = main_tex.index(r"\bibliography{references}")
            end_document_index = main_tex.index(r"\end{document}")

            self.assertLess(documentclass_index, preamble_index)
            self.assertLess(preamble_index, title_index)
            self.assertLess(title_index, begin_document_index)
            self.assertLess(begin_document_index, maketitle_index)
            self.assertLess(maketitle_index, section_index)
            self.assertLess(section_index, bibliography_style_index)
            self.assertLess(bibliography_style_index, bibliography_index)
            self.assertLess(bibliography_index, end_document_index)

    def test_invalid_template_raises_clear_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(source, [("Heading1", "Intro"), ("Normal", "Body.")])

            with self.assertRaisesRegex(ValueError, "Unknown template"):
                WordToLatexAgent(template_name="invalid_template").convert(source, output_dir)

    def test_generic_article_generation_uses_article_class(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(source, [("Heading1", "Intro"), ("Normal", "Body.")])

            result = WordToLatexAgent(template_name="generic_article").convert(source, output_dir)
            main_tex = result.main_tex_path.read_text(encoding="utf-8")

            self.assertIn(r"\documentclass{article}", main_tex)
            self.assertIn(r"\input{preamble}", main_tex)

    def test_generic_report_generation_uses_report_class(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(source, [("Heading1", "Intro"), ("Normal", "Body.")])

            result = WordToLatexAgent(template_name="generic_report").convert(source, output_dir)
            main_tex = result.main_tex_path.read_text(encoding="utf-8")

            self.assertIn(r"\documentclass{report}", main_tex)
            self.assertIn(r"\input{preamble}", main_tex)

    def test_cli_list_templates(self) -> None:
        run_path = Path(__file__).resolve().parents[1] / "run.py"
        completed = subprocess.run(
            [sys.executable, str(run_path), "--list-templates"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            completed.stdout.strip().splitlines(),
            ["generic_article", "generic_report", "copernicus", "agu", "springer", "nature"],
        )

    def test_cli_template_selection_overrides_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            run_path = Path(__file__).resolve().parents[1] / "run.py"
            make_docx(source, [("Heading1", "Intro"), ("Normal", "Body.")])

            completed = subprocess.run(
                [
                    sys.executable,
                    str(run_path),
                    "--input",
                    str(source),
                    "--output",
                    str(output_dir),
                    "--template",
                    "copernicus",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            main_tex = (output_dir / "main.tex").read_text(encoding="utf-8")
            self.assertIn("Created LaTeX project at", completed.stdout)
            self.assertIn(r"\bibliographystyle{copernicus}", main_tex)
            self.assertIn("% Placeholder Copernicus template body.", main_tex)

    def test_cli_parser_accepts_template_argument(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--list-templates"])
        self.assertTrue(args.list_templates)

    def test_qa_checker_reports_missing_required_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "sample_project"
            project_dir.mkdir()
            result = check_project(project_dir)

            self.assertEqual(result.status, "FAIL")
            self.assertTrue(any("main.tex" in issue.message for issue in result.failures))
            self.assertTrue(result.report_path.exists())

    def test_qa_checker_detects_duplicate_labels(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(source, [("Heading1", "Intro"), ("Normal", "Body text.")])

            result = WordToLatexAgent().convert(source, output_dir)
            section_path = result.section_files[0]
            section_path.write_text(
                section_path.read_text(encoding="utf-8") + "\n\\label{dup_label}\n\\label{dup_label}\n",
                encoding="utf-8",
            )

            qa_result = check_project(output_dir)

            self.assertEqual(qa_result.status, "FAIL")
            self.assertTrue(any("Duplicate label" in issue.message for issue in qa_result.failures))

    def test_qa_checker_detects_missing_figures(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Figures"),
                    {"image": {"filename": "diagram.png", "bytes": b"\x89PNG\r\n\x1a\ndiagram"}},
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            result.figure_files[0].unlink()

            qa_result = check_project(output_dir)

            self.assertEqual(qa_result.status, "FAIL")
            self.assertTrue(any("figure file is missing" in issue.message for issue in qa_result.failures))

    def test_qa_checker_detects_missing_citation_keys(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Related Work"),
                    ("Normal", "See (Wang et al., 2024)."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            result.bibliography_path.write_text("", encoding="utf-8")

            qa_result = check_project(output_dir)

            self.assertEqual(qa_result.status, "FAIL")
            self.assertTrue(any("Missing BibTeX entry" in issue.message for issue in qa_result.failures))

    def test_qa_checker_reports_todo_placeholders_and_unused_bibtex(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Figures"),
                    {"image": {"filename": "diagram.png", "bytes": b"\x89PNG\r\n\x1a\ndiagram"}},
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            result.bibliography_path.write_text(
                "@article{unused2024,\n  author = {Unused Author},\n  title = {Unused},\n  journal = {Unused},\n  year = {2024},\n}\n",
                encoding="utf-8",
            )

            qa_result = check_project(output_dir)

            self.assertEqual(qa_result.status, "WARN")
            self.assertTrue(any("TODO placeholder" in issue.message for issue in qa_result.warnings))
            self.assertTrue(any("Unused BibTeX entry" in issue.message for issue in qa_result.warnings))

    def test_cli_check_prints_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            run_path = Path(__file__).resolve().parents[1] / "run.py"
            make_docx(source, [("Heading1", "Intro"), ("Normal", "Body text.")])
            WordToLatexAgent().convert(source, output_dir)

            completed = subprocess.run(
                [sys.executable, str(run_path), "--check", str(output_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("PASS", completed.stdout)
            self.assertTrue((output_dir / "QA_REPORT.md").exists())

    def test_sync_overleaf_requires_git_remote(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "sample_project"
            project_dir.mkdir()
            (project_dir / "main.tex").write_text(r"\documentclass{article}", encoding="utf-8")

            with self.assertRaisesRegex(OverleafSyncError, "git_remote is missing"):
                sync_to_overleaf(project_dir, {"overleaf": {"git_remote": "", "branch": "main"}})

    def test_sync_overleaf_dry_run_shows_exact_commands(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "sample_project"
            project_dir.mkdir()
            (project_dir / "main.tex").write_text(r"\documentclass{article}", encoding="utf-8")

            result = sync_to_overleaf(
                project_dir,
                {"overleaf": {"git_remote": "https://git.overleaf.com/project", "branch": "main"}},
                dry_run=True,
            )

            self.assertTrue(result.dry_run)
            self.assertEqual(
                result.commands,
                [
                    ["git", "init"],
                    ["git", "remote", "add", "overleaf", "https://git.overleaf.com/project"],
                    ["git", "add", "."],
                    ["git", "commit", "-m", "Sync generated Overleaf project"],
                    ["git", "push", "overleaf", "HEAD:main"],
                ],
            )

    @patch("word2latex_agent.overleaf_sync.subprocess.run")
    def test_sync_overleaf_refuses_dirty_existing_repo(self, mock_run: object) -> None:
        with TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "sample_project"
            (project_dir / ".git").mkdir(parents=True)
            (project_dir / "main.tex").write_text(r"\documentclass{article}", encoding="utf-8")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["git", "status", "--porcelain"],
                returncode=0,
                stdout=" M main.tex\n",
                stderr="",
            )

            with self.assertRaisesRegex(OverleafSyncError, "Uncommitted changes exist"):
                sync_to_overleaf(
                    project_dir,
                    {"overleaf": {"git_remote": "https://git.overleaf.com/project", "branch": "main"}},
                )

    @patch("word2latex_agent.overleaf_sync.subprocess.run")
    def test_sync_overleaf_translates_auth_failure(self, mock_run: object) -> None:
        with TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "sample_project"
            project_dir.mkdir()
            (project_dir / "main.tex").write_text(r"\documentclass{article}", encoding="utf-8")

            responses = [
                subprocess.CompletedProcess(args=["git", "init"], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=["git", "remote", "add", "overleaf", "https://git.overleaf.com/project"],
                    returncode=0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(args=["git", "add", "."], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=["git", "commit", "-m", "Sync generated Overleaf project"],
                    returncode=0,
                    stdout="[main abc123] commit",
                    stderr="",
                ),
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["git", "push", "overleaf", "HEAD:main"],
                    stderr="Authentication failed",
                    output="",
                ),
            ]

            mock_run.side_effect = responses

            with self.assertRaisesRegex(OverleafSyncError, "authentication failed"):
                sync_to_overleaf(
                    project_dir,
                    {"overleaf": {"git_remote": "https://git.overleaf.com/project", "branch": "main"}},
                )

    @patch("word2latex_agent.overleaf_sync.subprocess.run")
    def test_sync_overleaf_executes_expected_git_sequence(self, mock_run: object) -> None:
        with TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "sample_project"
            project_dir.mkdir()
            (project_dir / "main.tex").write_text(r"\documentclass{article}", encoding="utf-8")

            mock_run.side_effect = [
                subprocess.CompletedProcess(args=["git", "init"], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=["git", "remote", "add", "overleaf", "https://git.overleaf.com/project"],
                    returncode=0,
                    stdout="",
                    stderr="",
                ),
                subprocess.CompletedProcess(args=["git", "add", "."], returncode=0, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=["git", "commit", "-m", "Sync generated Overleaf project"],
                    returncode=0,
                    stdout="[main abc123] commit",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    args=["git", "push", "overleaf", "HEAD:main"],
                    returncode=0,
                    stdout="",
                    stderr="",
                ),
            ]

            result = sync_to_overleaf(
                project_dir,
                {"overleaf": {"git_remote": "https://git.overleaf.com/project", "branch": "main"}},
            )

            self.assertFalse(result.dry_run)
            self.assertIn("Pushed project to Overleaf remote", result.message)
            self.assertEqual(mock_run.call_count, 5)

    def test_cli_parser_accepts_sync_arguments(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--sync-overleaf", "output/sample_project", "--dry-run"])
        self.assertEqual(args.sync_overleaf, Path("output/sample_project"))
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()
