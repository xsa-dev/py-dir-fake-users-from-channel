# Repository Guidelines

## Project Structure & Modules
- `run.py`: entry point that wires CLI to the async scanner app (console script `telegram-scanner` is also exposed via `pyproject.toml`).
- `src/telegram_scanner/`: core package; key modules include `config.py` (env loading/validation), `database.py` (SQLite access), `exporter.py` (participant fetch), `analyzer.py` (deleted-user detection), `deleter.py` (safe removal), `reporter.py` (CSV/JSON/text outputs), and `checkpoint_manager.py` (resume support).
- `test/`: unittest suites (`test_database_large.py`, `test_e2e_mock.py`) covering DB and flow scenarios.
- `reports/`, `checkpoints/`, `channel_users.db`, `telegram_scanner_session.session`: runtime artifacts; keep out of commits unless intentionally updating fixtures.

## Setup, Run, and Test Commands
Use Python 3.11+ and prefer uv (Makefile wraps common flows):

```bash
make install           # sync dependencies via uv
make start             # launch the interactive scanner (uv run python run.py)
make test              # run unittest discovery under test/
uv run python run.py   # direct start without Makefile
uv run telegram-scanner   # same entry via console script
```

## Coding Style & Naming
- Follow PEP 8 with 4-space indentation; keep imports ordered stdlib → third-party → local.
- Type hints are present; extend them for new public functions.
- Prefer descriptive, action-oriented function names (`export_channel_participants`, `find_deleted_accounts`).
- Keep side-effectful paths configurable via `config.py`; avoid hardcoded tokens or paths inside modules.

## Testing Guidelines
- Add or update tests in `test/test_*.py`; mirror module names where possible.
- Heavy-volume check in `test_database_large.py` (2M users) is gated by `RUN_HEAVY_TESTS=1`; keep it off by default unless validating performance-critical changes.
- Use `unittest` patterns already present (fixtures via `setUp`, async helpers via asyncio loops where needed).
- Cover new database schema changes and long-running flows with small, deterministic data sets.
- Run `make test` before opening a PR; include new reports or checkpoints only if explicitly required for the test.

## Commit & Pull Request Practices
- Write imperative, concise commit messages (e.g., "Add checkpoint resume prompt", "Fix analyzer username filter").
- For PRs: include a short summary of behavior changes, steps to reproduce/validate, and note impacts on DB schema, checkpoints, or report formats.
- Reference related issues when applicable; attach screenshots or CLI output snippets if the change affects user-facing prompts or reports.

## Configuration & Security
- Copy `.env.example` to `.env`; never commit real API IDs, hashes, or phone numbers.
- Local SQLite files (`channel_users.db`) contain user data—treat them as sensitive and avoid uploading.
- For new settings, add sane defaults in `config.py` and document them in `.env.example`.
