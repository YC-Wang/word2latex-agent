# word2latex-agent

Version 0.1 converts a `.docx` file into an Overleaf-ready LaTeX project.

## Features

- reads `.docx` input directly from the Office XML package
- detects Word headings and body paragraphs
- groups content into sections
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
pytest
```

## Notes

- Headings are detected from Word paragraph styles such as `Heading 1`.
- Paragraph text is escaped for common LaTeX special characters.
- If a document starts with body text before any heading, that content is placed
  into a default `Introduction` section.
