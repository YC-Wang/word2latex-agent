# word2latex-agent

Version 0.6 generates a more complete Overleaf-ready LaTeX project template with
configurable metadata, plus section, table, embedded figure, citation, and basic
equation support.

## Features

- reads `.docx` input directly from the Office XML package
- detects Word headings and body paragraphs
- groups content into sections while preserving block order
- converts Word tables into LaTeX `table` environments
- moves large tables into `tables/*.tex` and includes them from section files
- extracts embedded DOCX images into `figures/` and emits LaTeX figure environments
- matches nearby figure captions when possible and falls back to `TODO: Add caption`
- converts simple author-year citations into `natbib` commands
- generates `references.bib` with placeholder BibTeX entries
- writes an Overleaf-ready `preamble.tex` with common document packages
- detects OMML equations and converts simple displayed equations to LaTeX
- preserves unsupported equations with a clear TODO placeholder
- supports configurable project title, author, date, and document class
- writes `main.tex` plus `sections/*.tex`
- creates an Overleaf-ready output folder
- exposes a CLI through `run.py`

## Project Structure

```text
.
|-- examples/
|   `-- sample.docx
|-- output/
|   `-- .gitkeep
|-- prompts/
|   `-- system_prompt.txt
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
|   `-- main.tex.j2
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

Run the converter against the included sample document:

```powershell
python run.py --input examples/sample.docx --output output/sample_project
```

Expected output:

```text
output/sample_project/
|-- main.tex
|-- preamble.tex
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
project:
  title: "Converted Word Document"
  author: "word2latex-agent"
  date: \today
latex:
  document_class: "article"
  include_toc: true
```

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
- Displayed equations are labeled with the `eq:` prefix.
- Supported OMML equation conversions are intentionally limited to simple text,
  fractions, superscripts, and subscripts.
- Unsupported equations are preserved as `% TODO: Equation could not be converted`.
- Supported citation forms include `(Wang et al., 2024)`, `Wang et al. (2024)`,
  and multi-citations such as `(Coppola et al., 2021; Davolio et al., 2016)`.
- Citation keys are generated as lowercase `lastname + year`, such as `wang2024`.
- `references.bib` currently contains placeholder BibTeX entries only.
- If a document starts with body text before any heading, that content is placed
  into a default `Introduction` section.
- Overleaf sync is intentionally not implemented yet.
