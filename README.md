# word2latex-agent

Version 0.2 converts a `.docx` file into an Overleaf-ready LaTeX project with
section, table, and figure-placeholder support.

## Features

- reads `.docx` input directly from the Office XML package
- detects Word headings and body paragraphs
- groups content into sections while preserving block order
- converts Word tables into LaTeX `table` environments
- moves large tables into `tables/*.tex` and includes them from section files
- detects likely figure captions and emits figure placeholders with stable labels
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
latex:
  document_class: "article"
  include_toc: true
```

## Testing

```powershell
python -m unittest
```

## Notes

- Headings are detected from Word paragraph styles such as `Heading 1`.
- Paragraph text is escaped for common LaTeX special characters.
- Large tables are externalized when they have at least 5 rows or 4 columns.
- Figure captions starting with `Figure` or `Fig.` become figure placeholders.
- Table captions starting with `Table` are attached to the next Word table when possible.
- Stable labels are generated with `fig:` and `tab:` prefixes.
- If a document starts with body text before any heading, that content is placed
  into a default `Introduction` section.
- Citation conversion and Overleaf sync are intentionally not implemented yet.
