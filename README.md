# word2latex-agent

This repository is a single-document Word-to-LaTeX project template. Clone one
copy per manuscript, place the Word file at `input/report.docx`, and run
`python run.py` to generate an Overleaf-ready LaTeX project.

## Features

- reads `.docx` input directly from the Office XML package
- detects Word headings and body paragraphs
- groups content into sections while preserving block order
- converts Word tables into LaTeX `table` environments
- moves large tables into `tables/*.tex` and includes them from section files
- extracts embedded DOCX images into `figures/` and emits LaTeX figure environments
- matches nearby figure captions when possible and falls back to `TODO: Add caption`
- converts simple author-year citations into `natbib` commands
- parses a trailing References/Bibliography section into best-effort BibTeX entries
- falls back to placeholder BibTeX entries for citations that are not matched to parsed references
- writes an Overleaf-ready `preamble.tex` with common document packages
- detects OMML equations and converts simple displayed equations to LaTeX
- preserves unsupported equations with a clear TODO placeholder
- supports configurable project title, author, date, and document class
- supports selectable output templates, including generic article/report layouts
- includes placeholder publisher template folders for Copernicus, AGU, Springer, and Nature
- includes a LaTeX project QA checker that writes `QA_REPORT.md`
- supports pushing generated projects to Overleaf via Git, with dry-run mode
- supports a single end-to-end command that can convert, check, and sync
- writes `main.tex` plus `sections/*.tex`
- creates an Overleaf-ready output folder
- exposes a CLI through `run.py`

## Project Structure

```text
.
|-- output/
|   `-- .gitkeep
|-- input/
|   `-- report.docx
|-- src/
|   `-- word2latex_agent/
|       |-- __init__.py
|       |-- agent.py
|       |-- cli.py
|       |-- config.py
|       |-- docx_reader.py
|       |-- latex_writer.py
|       `-- models.py
|-- templates/
|   |-- generic_article/
|   |-- generic_report/
|   |-- copernicus/
|   |-- agu/
|   |-- springer/
|   `-- nature/
|-- tests/
|   |-- fixtures.py
|   `-- test_conversion.py
|-- config.yaml
|-- requirements.txt
|-- run.py
`-- README.md
```

## Setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## Usage

For the standard single-document workflow:

```powershell
python run.py
```

Run the full workflow in one command:

```powershell
python run.py --check --sync-overleaf
```

Manual mode is still available:

```powershell
python run.py --input path/to/report.docx --output path/to/output
```

List available templates:

```powershell
python run.py --list-templates
```

Override the template from the command line:

```powershell
python run.py --template copernicus
```

Run QA checks against an existing generated project:

```powershell
python run.py --check output
```

Push a generated project to Overleaf:

```powershell
python run.py --sync-overleaf output
```

Preview the exact Git commands without executing them:

```powershell
python run.py --sync-overleaf output --dry-run
```

Expected output:

```text
output/
|-- main.tex
|-- preamble.tex
|-- QA_REPORT.md
|-- references.bib
|-- figures/
|   `-- figure_001.png
|-- tables/
|   `-- table_01_01_table_1_results_summary.tex
`-- sections/
    |-- section_01_introduction.tex
    `-- section_02_method.tex
```

## Configuration

Default behavior lives in `config.yaml`:

```yaml
template: generic_article
workflow:
  default_input_file: "input/report.docx"
  default_output_folder: "output"
  default_template: "generic_article"
  dry_run: false
project:
  title: "Converted Word Document"
  author: "word2latex-agent"
  date: \today
latex:
  include_toc: true
overleaf:
  enabled: false
  project_id: ""
  git_remote: ""
  branch: main
```

To override the class explicitly, add for example:

```yaml
latex:
  document_class: "report"
```

Supported template names:

- `generic_article`
- `generic_report`
- `copernicus`
- `agu`
- `springer`
- `nature`

Template status:

- `generic_article` and `generic_report` are fully implemented.
- `copernicus`, `agu`, `springer`, and `nature` are placeholder structures that
  can later be replaced with the official publisher class files and formatting.

The generated `main.tex` always includes:

- `\documentclass{...}`
- `\input{preamble}`
- `\title{...}`, `\author{...}`, `\date{...}`
- `\begin{document}` and `\maketitle`
- section inputs from `sections/`
- `\bibliographystyle{plainnat}` and `\bibliography{references}`
- `\end{document}`

## Testing

```powershell
python -m unittest
```

## End-to-End Workflow

The main workflow command runs in this order:

1. Parse the input DOCX.
2. Generate the LaTeX project structure.
3. Extract figures and tables.
4. Generate `references.bib`.
5. Run the QA checker when `--check` is enabled.
6. Sync to Overleaf when `--sync-overleaf` is enabled and QA is `PASS` or `WARN`.

Recommended manuscript workflow:

1. Clone this repository for a new manuscript.
2. Replace `input/report.docx` with the manuscript Word file.
3. Run `python run.py`.
4. Review `output/`.
5. Optionally run `python run.py --check` or `python run.py --check --sync-overleaf`.

At the end of the run, the CLI prints a workflow summary with:

- generated files
- number of sections
- number of figures
- number of tables
- number of citations
- QA status
- Overleaf sync status

You can inspect command-line options with:

```powershell
python run.py --help
```

## QA Checker

The QA checker validates:

- `main.tex`, `preamble.tex`, and `references.bib` exist
- all `\input{...}` targets exist
- all `\includegraphics{...}` targets exist
- all `\ref{...}`-style references resolve to labels
- duplicate `\label{...}` entries are reported
- all `\citep{...}` and `\citet{...}` keys exist in `references.bib`
- unused BibTeX entries are reported
- TODO placeholders are reported

The checker writes `QA_REPORT.md` and prints one of:

- `PASS`
- `WARN`
- `FAIL`

## Overleaf Git Sync

Add your Overleaf Git remote to `config.yaml`:

```yaml
overleaf:
  enabled: true
  project_id: "YOUR_PROJECT_ID"
  git_remote: "https://git.overleaf.com/YOUR_PROJECT_ID"
  branch: main
```

Typical setup:

1. Open the Overleaf project.
2. Copy the Git URL from Overleaf's Git integration UI.
3. Paste it into `overleaf.git_remote` in `config.yaml`, or set `overleaf.project_id`.
4. Run `python run.py --sync-overleaf output --dry-run`.
5. If the commands look correct, run `python run.py --sync-overleaf output`.

The sync command:

- verifies the output directory and `main.tex`
- initializes Git in the generated project if needed
- refuses to proceed if an existing project repo has uncommitted changes
- adds an `overleaf` remote when missing
- commits generated files
- pushes to the configured branch

Failure handling:

- missing `git_remote` produces a clear error
- authentication failures produce a clear error
- dry-run mode prints the exact Git commands without executing them

## Notes

- Headings are detected from Word paragraph styles such as `Heading 1`.
- Paragraph text is escaped for common LaTeX special characters.
- Large tables are externalized when they have at least 5 rows or 4 columns.
- Embedded images are saved with stable filenames such as `figure_001.png`.
- Figure captions starting with `Figure` or `Fig.` are matched to nearby images when possible.
- If figure caption matching is uncertain, the generated figure uses `TODO: Add caption`.
- Table captions starting with `Table` are attached to the next Word table when possible.
- Stable labels are generated with `fig:` and `tab:` prefixes.
- The Overleaf-oriented preamble includes `graphicx`, `natbib`, `booktabs`,
  `longtable`, `amsmath`, `amssymb`, `hyperref`, and `geometry`.
- Each template folder contains `main.tex.j2`, `preamble.tex.j2`,
  `metadata.yaml`, and `README.md`.
- Displayed equations are labeled with the `eq:` prefix.
- Supported OMML equation conversions are intentionally limited to simple text,
  fractions, superscripts, and subscripts.
- Unsupported equations are preserved as `% TODO: Equation could not be converted`.
- Supported citation forms include `(Wang et al., 2024)`, `Wang et al. (2024)`,
  and multi-citations such as `(Coppola et al., 2021; Davolio et al., 2016)`.
- Citation keys are generated as lowercase `lastname + year`, such as `wang2024`.
- If the manuscript includes a `References` or `Bibliography` section, the agent
  attempts to parse lines in the form `Authors, YEAR: Title. Journal, Volume, pages.`
  into BibTeX entries with `author`, `title`, `journal`, `year`, `volume`, and `pages`.
- Climate-style `and Coauthors` text is normalized to BibTeX-friendly `and others`.
- Generated bibliography keys are stable best-effort keys such as `hersbach2020era5`.
- Page ranges are normalized from forms like `1999-2049` to `1999--2049`.
- If a reference item cannot be parsed, the agent still falls back to placeholder
  BibTeX entries for unmatched in-text citations.
- `QA_REPORT.md` is generated only when the checker is run.
- If a document starts with body text before any heading, that content is placed
  into a default `Introduction` section.
- Official publisher templates are not implemented yet.
- Overleaf Git sync does not implement any AI rewriting or conflict resolution.
