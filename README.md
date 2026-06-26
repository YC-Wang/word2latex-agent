# word2latex-agent

A Python project scaffold for an AI agent that converts Microsoft Word content
into structured LaTeX output.

## Overview

This repository provides a clean starting point for building a Word-to-LaTeX
agent with:

- a `src/`-based Python package layout
- isolated virtual environment workflow via `.venv`
- lint and test configuration
- GitHub Actions CI
- GitHub issue, PR, and dependency update templates
- starter CLI and agent service classes

## Project Structure

```text
.
|-- .github/
|   `-- workflows/
|       `-- ci.yml
|-- src/
|   `-- word2latex_agent/
|       |-- __init__.py
|       |-- agent.py
|       `-- cli.py
|-- tests/
|   |-- __init__.py
|   `-- test_agent.py
|-- .editorconfig
|-- .gitignore
|-- .python-version
|-- LICENSE
|-- pyproject.toml
|-- README.md
`-- requirements.txt
```

## Quick Start

1. Create a virtual environment:

```powershell
py -3.11 -m venv .venv
```

2. Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

4. Run the test suite:

```powershell
pytest
```

5. Run the starter CLI:

```powershell
python -m word2latex_agent.cli --input sample.docx --output sample.tex
```

## Development Notes

- `requirements.txt` contains the base runtime and dev tooling dependencies.
- `pyproject.toml` defines package metadata and tool configuration.
- The current implementation includes a placeholder conversion pipeline you can
  replace with DOCX parsing, prompt orchestration, and LaTeX post-processing.

## Next Steps

- Add DOCX ingestion using `python-docx` or a document extraction pipeline.
- Add LLM provider integration for semantic restructuring and citation handling.
- Add validation for generated LaTeX and round-trip regression tests.
