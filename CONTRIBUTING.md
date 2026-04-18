# Contributing to ContextWolf

Thank you for your interest in contributing to ContextWolf! This project is maintained
by one person, so pull requests are very welcome - but please be patient, reviews may
take some time.

## Reporting Bugs

Please open a [GitHub Issue](https://github.com/DarkWolfCave/context-wolf/issues) and
include:

- A clear description of the bug
- Steps to reproduce
- Expected vs. actual behavior
- Your Python version, OS, and relevant configuration

## Suggesting Features

Open a [GitHub Issue](https://github.com/DarkWolfCave/context-wolf/issues) with the
label `enhancement`. Describe the use case and why it would be useful.

Note: The WebGUI is a separate private project. Please do not open issues or PRs
related to a graphical interface.

## Development Setup

### Prerequisites

- Python 3.12 or higher
- Docker (for PostgreSQL + pgvector)
- [uv](https://astral.sh/uv) package manager

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Clone and install

```bash
git clone https://github.com/DarkWolfCave/context-wolf.git
cd context-wolf
uv sync --extra all
```

### Start the database

```bash
docker compose up -d
```

This starts PostgreSQL 13+ with the pgvector extension.

### Initial setup

```bash
bash setup.sh
```

Or manually:

```bash
cm init
cm setup-mcp
```

### Run tests

```bash
uv run pytest
```

## Pull Request Guidelines

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. Make your changes. Keep commits focused and use the commit format:
   ```
   type: short description in English
   ```
   Valid types: `feat`, `fix`, `refactor`, `docs`, `chore`, `perf`, `test`

3. Add or update tests where applicable.

4. Open one PR per feature or fix - avoid bundling unrelated changes.

5. Describe what your PR does and why in the PR description.

## Code Style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

Check for issues:

```bash
uv run ruff check .
```

Auto-format:

```bash
uv run ruff format .
```

Please make sure both commands pass before submitting a PR.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
