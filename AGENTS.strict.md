# Agent Execution Guide (Strict)

## Package Manager
Use `pip` with editable install:
- `python -m venv .venv && source .venv/bin/activate`
- `python -m pip install -e ".[dev]"`

## Commit Attribution
AI commits MUST include:
```
Co-Authored-By: OpenAI Codex <noreply@openai.com>
```

## Key Conventions
- Python 3.10+, 4-space indentation, line length 100 (`ruff`).
- Names: files/modules `snake_case`, classes `PascalCase`, enums/constants `UPPER_SNAKE_CASE`.
- Keep interfaces in `*/base.py`; shared contracts in `src/types.py`.
- Avoid direct hardware coupling in core logic; mock hardware in tests.
- Never commit secrets, firmware binaries, or generated experiment/raw data.

## Validate Before PR
| Command | Purpose |
|---|---|
| `ruff check src tests` | Lint + import/order/style checks |
| `mypy src` | Static typing checks |
| `pytest` | Full test run with coverage |
| `pytest tests/unit -q` | Fast unit regression |

## Path Map
- Runtime modules: `src/`
- Config: `configs/`
- Tests: `tests/unit`, `tests/integration`
- Architecture reference: `docs/ARCHITECTURE.md`
- Experiment outputs (do not commit): `experiments/results/`, `mlruns/`, `data/raw/`

## Local Skills
- No repository-local skills were detected under `.claude/skills/` or `plugins/*/skills/`.
