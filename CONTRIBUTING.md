# Contributing

Thank you for your interest in AIP Qx.

## Before you open a pull request

- Check existing issues and pull requests to avoid duplicating work.
- For significant changes, open an issue first to discuss the approach.
- Keep pull requests focused. One concern per PR.

## Development setup

```bash
git clone https://github.com/zak-li/qx.git
cd qx
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run the test suite before submitting:

```bash
pytest tests/
```

## Code style

- Python: [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Configuration is in `pyproject.toml`.
- Go (chaincode): standard `gofmt`.
- Do not commit secrets, credentials, or generated files.

## Commit messages

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat: add sanctions screening endpoint
fix: handle expired KYC in freeze flow
docs: update environment variable reference
```

## Reporting security issues

Do not open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contributions will be licensed under the [Business Source License 1.1](LICENSE).
