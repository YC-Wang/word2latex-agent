import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from word2latex_agent import WordToLatexAgent
from word2latex_agent.citations import build_reference_lookup, convert_text_citations, parse_reference_line
from word2latex_agent.cli import WORKFLOW_TARGET, build_parser, main as cli_main
from word2latex_agent.docx_reader import extract_reference_section, read_docx_blocks, read_docx_paragraphs, split_into_sections
from word2latex_agent.models import EquationBlock, FigureBlock, ImageBlock, ParagraphBlock, QAIssue, QAResult, Section, TableBlock
from word2latex_agent.overleaf_sync import SyncResult
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
            self.assertIn(r"\input{sections/01_introduction}", main_tex)
            self.assertIn(r"\input{sections/02_method}", main_tex)
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

    def test_reference_line_parses_into_bibtex_fields(self) -> None:
        entry = parse_reference_line(
            "Hersbach, H., and Coauthors, 2020: The ERA5 global reanalysis. "
            "Quarterly Journal of the Royal Meteorological Society, 146, 1999-2049."
        )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.key, "hersbach2020era5")
        self.assertEqual(entry.author, "Hersbach, H. and others")
        self.assertEqual(entry.title, "The ERA5 global reanalysis")
        self.assertEqual(entry.journal, "Quarterly Journal of the Royal Meteorological Society")
        self.assertEqual(entry.year, "2020")
        self.assertEqual(entry.volume, "146")
        self.assertEqual(entry.pages, "1999--2049")

    def test_reference_section_is_extracted_from_body_sections(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.docx"
            make_docx(
                source,
                [
                    ("Heading1", "Introduction"),
                    ("Normal", "See Hersbach et al. (2020)."),
                    ("Heading1", "References"),
                    (
                        "Normal",
                        "Hersbach, H., and Coauthors, 2020: The ERA5 global reanalysis. "
                        "Quarterly Journal of the Royal Meteorological Society, 146, 1999-2049.",
                    ),
                ],
            )

            sections, reference_lines = extract_reference_section(
                split_into_sections(read_docx_blocks(source))
            )

            self.assertEqual([section.title for section in sections], ["Introduction"])
            self.assertEqual(len(reference_lines), 1)
            self.assertIn("The ERA5 global reanalysis", reference_lines[0])

    def test_reference_section_generates_bibtex_and_resolves_citation_keys(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Heading1", "Introduction"),
                    ("Normal", "See Hersbach et al. (2020) for details."),
                    ("Heading1", "References"),
                    (
                        "Normal",
                        "Hersbach, H., and Coauthors, 2020: The ERA5 global reanalysis. "
                        "Quarterly Journal of the Royal Meteorological Society, 146, 1999-2049.",
                    ),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")
            bibliography = result.bibliography_path.read_text(encoding="utf-8")

            self.assertIn(r"\citet{hersbach2020era5}", section_tex)
            self.assertNotIn(r"\section{References}", section_tex)
            self.assertIn("@article{hersbach2020era5,", bibliography)
            self.assertIn("author = {Hersbach, H. and others}", bibliography)
            self.assertIn("title = {The ERA5 global reanalysis}", bibliography)
            self.assertIn("journal = {Quarterly Journal of the Royal Meteorological Society}", bibliography)
            self.assertIn("volume = {146}", bibliography)
            self.assertIn("pages = {1999--2049}", bibliography)

    def test_extract_reference_section_handles_singular_reference_heading_and_bibliography_style(self) -> None:
        sections, reference_lines = extract_reference_section(
            [
                Section(
                    title="1. Introduction",
                    blocks=[ParagraphBlock(text="See Hersbach et al. 2020.", style="Normal")],
                ),
                Section(
                    title="Reference",
                    blocks=[
                        ParagraphBlock(
                            text="Hersbach, H., and Coauthors, 2020: The ERA5 global reanalysis. "
                            "Quarterly Journal of the Royal Meteorological Society, 146, 1999-2049.",
                            style="Normal",
                        )
                    ],
                ),
                Section(
                    title="Supplementary",
                    blocks=[
                        ParagraphBlock(
                            text="Bibliography Chou, C., L.-F. Huang, L. Tseng, J.-Y. Tu, and P.-H. Tan, 2009: "
                            "Annual Cycle of Rainfall in the Western North Pacific and East Asian Sector. "
                            "Journal of Climate, 22, 2073-2094.",
                            style="EndNote Bibliography",
                        )
                    ],
                ),
            ]
        )

        self.assertEqual([section.title for section in sections], ["1. Introduction"])
        self.assertEqual(len(reference_lines), 2)
        self.assertTrue(reference_lines[0].startswith("Hersbach, H."))
        self.assertTrue(reference_lines[1].startswith("Chou, C."))

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

    def test_convert_text_citations_uses_reference_lookup_when_available(self) -> None:
        entry = parse_reference_line(
            "Hersbach, H., and Coauthors, 2020: The ERA5 global reanalysis. "
            "Quarterly Journal of the Royal Meteorological Society, 146, 1999-2049."
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        lookup = build_reference_lookup(
            [entry]
        )
        converted, citations = convert_text_citations(
            "See Hersbach et al. (2020) and (Hersbach et al., 2020).",
            lookup,
        )

        self.assertIn(r"\citet{hersbach2020era5}", converted)
        self.assertIn(r"\citep{hersbach2020era5}", converted)
        self.assertEqual([citation.key for citation in citations], ["hersbach2020era5"])

    def test_convert_text_citations_accepts_optional_comma_and_two_authors(self) -> None:
        converted, citations = convert_text_citations(
            "See (Hersbach et al. 2020; Cho and Lu 2017) and Yang and Lo (2023)."
        )

        self.assertIn(r"\citep{hersbach2020,cho2017}", converted)
        self.assertIn(r"\citet{yang2023}", converted)
        self.assertEqual(
            sorted(citation.key for citation in citations),
            ["cho2017", "hersbach2020", "yang2023"],
        )

    def test_numbered_headings_are_detected_from_plain_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.docx"
            make_docx(
                source,
                [
                    ("Normal", "1. Introduction"),
                    ("Normal", "Opening paragraph."),
                    ("Normal", "2. Method"),
                    ("Normal", "Method paragraph."),
                ],
            )

            sections = split_into_sections(read_docx_blocks(source))

            self.assertEqual([section.title for section in sections], ["Introduction", "Method"])

    def test_front_matter_abstract_and_keywords_stay_in_main_tex(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Normal", "A Scientific Report Title"),
                    ("Normal", "Alice Example, Bob Example"),
                    ("Normal", "1Example University, City"),
                    ("Normal", "Abstract"),
                    ("Normal", "This is the abstract paragraph."),
                    ("Normal", "Keywords: climate, downscaling, latex"),
                    ("Normal", "1. Introduction"),
                    ("Normal", "Body paragraph."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            main_tex = result.main_tex_path.read_text(encoding="utf-8")
            section_tex = result.section_files[0].read_text(encoding="utf-8")

            self.assertIn(r"\title{A Scientific Report Title}", main_tex)
            self.assertIn(r"\author{Alice Example, Bob Example}", main_tex)
            self.assertIn(r"\begin{abstract}", main_tex)
            self.assertIn("This is the abstract paragraph.", main_tex)
            self.assertIn(r"\end{abstract}", main_tex)
            self.assertIn(r"\textbf{Keywords:} climate, downscaling, latex", main_tex)
            self.assertIn("1Example University, City", main_tex)
            self.assertNotIn(r"\begin{abstract}", section_tex)
            self.assertNotIn("Keywords:", section_tex)

    def test_only_top_level_sections_create_files_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Normal", "1. Introduction"),
                    ("Normal", "Intro paragraph."),
                    ("Normal", "1.1 Background"),
                    ("Normal", "Background paragraph."),
                    ("Normal", "2. Results"),
                    ("Normal", "Results paragraph."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            first_section = result.section_files[0].read_text(encoding="utf-8")
            main_tex = result.main_tex_path.read_text(encoding="utf-8")

            self.assertEqual([path.name for path in result.section_files], ["01_introduction.tex", "02_results.tex"])
            self.assertIn(r"\input{sections/01_introduction}", main_tex)
            self.assertIn(r"\input{sections/02_results}", main_tex)
            self.assertIn(r"\section{Introduction}", first_section)
            self.assertIn(r"\subsection{Background}", first_section)
            self.assertIn("Background paragraph.", first_section)

    def test_empty_top_level_sections_are_preserved_as_split_anchors(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Normal", "1. Introduction"),
                    ("Normal", "1.1 Background"),
                    ("Normal", "Background paragraph."),
                    ("Normal", "2. Results"),
                    ("Normal", "2.1 Findings"),
                    ("Normal", "Findings paragraph."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            first_section = (output_dir / "sections" / "01_introduction.tex").read_text(encoding="utf-8")
            second_section = (output_dir / "sections" / "02_results.tex").read_text(encoding="utf-8")

            self.assertEqual(
                [path.name for path in result.section_files],
                ["01_introduction.tex", "02_results.tex"],
            )
            self.assertIn(r"\section{Introduction}", first_section)
            self.assertIn(r"\subsection{Background}", first_section)
            self.assertIn("Background paragraph.", first_section)
            self.assertIn(r"\section{Results}", second_section)
            self.assertIn(r"\subsection{Findings}", second_section)
            self.assertIn("Findings paragraph.", second_section)

    def test_split_level_subsection_creates_subsection_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            config_path = temp_path / "config.yaml"
            make_docx(
                source,
                [
                    ("Normal", "1. Introduction"),
                    ("Normal", "Intro paragraph."),
                    ("Normal", "1.1 Background"),
                    ("Normal", "Background paragraph."),
                    ("Normal", "2. Results"),
                    ("Normal", "Results paragraph."),
                ],
            )
            config_path.write_text(
                "\n".join(
                    [
                        "section_splitting:",
                        "  split_level: subsection",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = WordToLatexAgent(config_path=config_path).convert(source, output_dir)

            self.assertEqual(
                [path.name for path in result.section_files],
                ["01_introduction.tex", "02_background.tex", "03_results.tex"],
            )

    def test_split_level_none_keeps_body_in_main_tex(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            config_path = temp_path / "config.yaml"
            make_docx(
                source,
                [
                    ("Normal", "1. Introduction"),
                    ("Normal", "Intro paragraph."),
                    ("Normal", "1.1 Background"),
                    ("Normal", "Background paragraph."),
                ],
            )
            config_path.write_text(
                "\n".join(
                    [
                        "section_splitting:",
                        "  split_level: none",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = WordToLatexAgent(config_path=config_path).convert(source, output_dir)
            main_tex = result.main_tex_path.read_text(encoding="utf-8")

            self.assertEqual(result.section_files, [])
            self.assertIn(r"\section{Introduction}", main_tex)
            self.assertIn(r"\subsection{Background}", main_tex)
            self.assertNotIn(r"\input{sections/", main_tex)

    def test_figures_heading_is_not_treated_as_caption(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.docx"
            make_docx(
                source,
                [
                    ("Normal", "Figures"),
                    {"image": {"filename": "image_1.png", "bytes": b"png"}},
                    ("Normal", "Figure 1. Proper caption."),
                ],
            )

            blocks = read_docx_blocks(source)
            images = [block for block in blocks if isinstance(block, ImageBlock)]
            figure_placeholders = [block for block in blocks if isinstance(block, FigureBlock)]

            self.assertEqual(len(images), 1)
            self.assertEqual(images[0].caption, "Figure 1. Proper caption.")
            self.assertFalse(any(block.caption == "Figures" for block in figure_placeholders))

    def test_unsupported_figure_format_uses_placeholder_and_warns(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "sample.docx"
            output_dir = temp_path / "sample_project"
            make_docx(
                source,
                [
                    ("Normal", "1. Results"),
                    {"image": {"filename": "image_1.emf", "bytes": b"emf"}},
                    ("Normal", "Figure 1. Unsupported figure."),
                ],
            )

            result = WordToLatexAgent().convert(source, output_dir)
            section_tex = result.section_files[0].read_text(encoding="utf-8")
            qa_result = check_project(output_dir)

            self.assertIn(r"Unsupported figure format: figure\_001.emf", section_tex)
            self.assertIn("% TODO: Convert unsupported figure format for Overleaf", section_tex)
            self.assertNotIn(r"\includegraphics[width=\linewidth]{figures/figure_001.emf}", section_tex)
            self.assertEqual(qa_result.status, "WARN")
            self.assertTrue(
                any("Unsupported figure format for Overleaf" in issue.message for issue in qa_result.warnings)
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
            section_index = main_tex.index(r"\input{sections/01_intro}")
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
        self.assertEqual(args.sync_overleaf, "output/sample_project")
        self.assertTrue(args.dry_run)

    def test_cli_parser_supports_workflow_flags_without_paths(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--check", "--sync-overleaf"])
        self.assertEqual(args.check, WORKFLOW_TARGET)
        self.assertEqual(args.sync_overleaf, WORKFLOW_TARGET)

    @patch("word2latex_agent.cli.sync_to_overleaf")
    def test_full_workflow_runs_convert_check_and_sync(self, mock_sync: object) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "report.docx"
            output_dir = temp_path / "projects" / "report"
            make_docx(
                source,
                [
                    ("Heading1", "Intro"),
                    ("Normal", "Body text."),
                ],
            )
            mock_sync.return_value = SyncResult(
                project_dir=output_dir,
                dry_run=False,
                commands=[["git", "push"]],
                message="Pushed project to Overleaf remote 'https://git.overleaf.com/project' on branch 'main'.",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                cli_main(
                    [
                        "--input",
                        str(source),
                        "--output",
                        str(output_dir),
                        "--template",
                        "generic_article",
                        "--check",
                        "--sync-overleaf",
                    ]
                )

            rendered = stdout.getvalue()
            self.assertIn("Workflow Summary", rendered)
            self.assertIn("QA status: PASS", rendered)
            self.assertIn("Overleaf sync status: SYNCED", rendered)
            self.assertTrue((output_dir / "QA_REPORT.md").exists())
            mock_sync.assert_called_once()

    @patch("word2latex_agent.cli.sync_to_overleaf")
    @patch("word2latex_agent.cli.check_project")
    def test_full_workflow_skips_sync_when_qa_fails(
        self, mock_check_project: object, mock_sync: object
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "report.docx"
            output_dir = temp_path / "projects" / "report"
            make_docx(
                source,
                [
                    ("Heading1", "Figures"),
                    {"image": {"filename": "uncaptioned.png", "bytes": b"\x89PNG\r\n\x1a\nimg"}},
                ],
            )
            mock_check_project.return_value = QAResult(
                project_dir=output_dir,
                report_path=output_dir / "QA_REPORT.md",
                status="FAIL",
                failures=[QAIssue("FAIL", "Forced QA failure", "test")],
                warnings=[],
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                cli_main(
                    [
                        "--input",
                        str(source),
                        "--output",
                        str(output_dir),
                        "--check",
                        "--sync-overleaf",
                    ]
                )

            rendered = stdout.getvalue()
            self.assertIn("QA status: FAIL", rendered)
            self.assertIn("Overleaf sync status: SKIPPED (QA failed)", rendered)
            mock_sync.assert_not_called()

    def test_full_workflow_uses_default_output_folder(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "report.docx"
            config_path = temp_path / "config.yaml"
            make_docx(source, [("Heading1", "Intro"), ("Normal", "Body text.")])
            config_path.write_text(
                "\n".join(
                    [
                        "template: generic_article",
                        "workflow:",
                        f'  default_output_folder: "{(temp_path / "projects").as_posix()}"',
                        '  default_template: "generic_report"',
                        "  dry_run: false",
                        "project:",
                        '  title: "Converted Word Document"',
                        '  author: "word2latex-agent"',
                        "  date: \\today",
                        "latex:",
                        "  include_toc: true",
                        "overleaf:",
                        "  enabled: false",
                        '  project_id: ""',
                        '  git_remote: ""',
                        '  branch: "main"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                cli_main(["--input", str(source), "--config", str(config_path)])

            rendered = stdout.getvalue()
            self.assertIn("Workflow Summary", rendered)
            generated_main = temp_path / "projects" / "main.tex"
            self.assertTrue(generated_main.exists())
            self.assertIn(r"\documentclass{report}", generated_main.read_text(encoding="utf-8"))

    def test_full_workflow_uses_default_input_and_output_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_dir = temp_path / "input"
            output_dir = temp_path / "output"
            config_path = temp_path / "config.yaml"
            input_dir.mkdir()
            make_docx(
                input_dir / "report.docx",
                [
                    ("Heading1", "Intro"),
                    ("Normal", "Body text."),
                ],
            )
            config_path.write_text(
                "\n".join(
                    [
                        "template: generic_article",
                        "workflow:",
                        f'  default_input_file: "{(input_dir / "report.docx").as_posix()}"',
                        f'  default_output_folder: "{output_dir.as_posix()}"',
                        '  default_template: "generic_article"',
                        "  dry_run: false",
                        "project:",
                        '  title: "Converted Word Document"',
                        '  author: "word2latex-agent"',
                        "  date: \\today",
                        "latex:",
                        "  include_toc: true",
                        "overleaf:",
                        "  enabled: false",
                        '  project_id: ""',
                        '  git_remote: ""',
                        '  branch: "main"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                cli_main(["--config", str(config_path)])

            rendered = stdout.getvalue()
            self.assertIn("Created LaTeX project at", rendered)
            self.assertTrue((output_dir / "main.tex").exists())


if __name__ == "__main__":
    unittest.main()
