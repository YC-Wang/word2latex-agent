# Contributing

## Development Setup

1. Create and activate a virtual environment:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## Local Checks

Run these before opening a pull request:

```powershell
ruff check .
mypy src
pytest
```

## Pull Requests

- Keep changes focused and reviewable.
- Add or update tests for behavior changes.
- Document any new configuration, environment variables, or workflows.
