# Contributing

Thanks for your interest in improving MathMaster AI.

## Before making changes

1. Check the existing README and [architecture notes](docs/ARCHITECTURE.md).
2. For a significant change, open an issue first and describe the problem and proposed approach.
3. Keep changes focused. The application is currently a single Python file, so avoid unrelated edits in the same change.

## Development setup

Use Python 3.11 or newer and a virtual environment.

```bash
python -m venv .venv
# Activate the environment, then:
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Optional OCR dependencies:

```bash
pip install -r requirements-ocr.txt
```

Create a local `.env` based on `.env.example`. Never commit real bot tokens, API keys, databases, or logs.

## Before opening a pull request

- Run a syntax check:

  ```bash
  python -m py_compile "math_bot Math Master.py"
  ```

- Test the affected bot flow manually with a test bot where practical.
- Do not include real credentials, personal data, database files, or log files.
- Update the README or documentation when user-facing behaviour or setup changes.
- Explain what changed, why it changed, and how it was tested.

## Pull request checklist

- [ ] The change has a clear purpose.
- [ ] Existing behaviour is preserved unless the change intentionally updates it.
- [ ] Secrets and personal data are not included.
- [ ] Syntax checks pass.
- [ ] Documentation is updated where needed.
- [ ] Limitations and untested areas are stated honestly.

By contributing, you agree that your contributions may be distributed under the project's chosen license once one is established. Until a license is added, do not assume that the repository grants permission to reuse its code.
