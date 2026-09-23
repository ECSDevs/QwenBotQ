# QwenBotQ Agent Notes

## Purpose and layout

QwenBotQ is a Python NoneBot2 QQ entertainment bot using the OneBot v11 adapter. The root entry point is `bot.py`; the main plugin package is `qwenbotq/`.

- `qwenbotq/ai/`: optional OpenAI-compatible chat and tools integration.
- `qwenbotq/database/`: Beanie/Motor MongoDB documents and database helpers.
- `qwenbotq/config_model/`: Pydantic models for `config.yml`.
- `qwenbotq/imagesearch/`, `fileserver.py`, `imagecache.py`: image search/download, HTTP file serving, and recalled-image caching.
- `binding.py`, `usersystem.py`, `lottery.py`, `bilinotice.py`, `superuser.py`: feature plugins; several are enabled only when their config section is populated.
- `blackjack.py`、`blackjack_logic.py`：21点多人押注小游戏（`blackjack_logic.py` 为纯规则逻辑，不依赖 NoneBot/数据库，单元测试直接加载；`blackjack.py` 为命令与内存态房间，key=会话ID，无数据库持久化，积分即时扣/退/结算，大厅/对局超时自动退款或强制结算）。
- `lognotice.py`: always-on loguru sink that forwards WARNING and above logs to every configured superuser's private chat. Registered via an `on_startup` hook that captures the running event loop and adds the sink with a self-name filter and a 5-second `(name, message)` dedup window to prevent recursion and flooding. Forwarding is scheduled with `asyncio.run_coroutine_threadsafe` so it works from any thread; sending failures are swallowed silently to avoid recursive logging.
- `ehentaix/`: local editable `ehentaix` library for E-Hentai searching/downloading, with its own `pyproject.toml` and live integration scripts.
- `downloads/`: runtime cache/download data; do not treat it as source code.

Read `README.md`, `config.example.yml`, and `SECURITY.md` before changing deployment, configuration, or security-sensitive behavior. For E-Hentai API/client changes, also read the relevant `ehentaix/*_API.md` documentation.

## Environment and commands

The root project uses Poetry and supports Python `>=3.10,<3.14` (the README's deployment example uses Python 3.11). Install dependencies with:

```bash
poetry install
```

Common commands:

```bash
poetry run python bot.py       # direct startup
poetry run nb run              # NoneBot CLI startup; run.bat wraps this on Windows
poetry run black --check .     # formatting check
poetry run pyright             # workspace type check (basic mode)
```

Create a local `config.yml` from `config.example.yml` before starting. `qwenbotq.config_model.get_config()` opens `config.yml` relative to the current working directory, so run commands from the repository root. Runtime deployment normally also needs MongoDB, a OneBot v11 forward WebSocket driver (such as NapCatQQ), and optional API services for enabled features.

Tests are currently live integration scripts rather than isolated unit tests:

```bash
poetry run pytest ehentaix/test_search.py
poetry run python ehentaix/test_exhentai_search.py  # requires local cookies.json
```

A full `poetry run pytest` collection currently fails because `test_exhentai_search.py` executes at import time and immediately opens `cookies.json`; do not interpret that as a product regression. These scripts also require network access.

## Architecture and edit boundaries

`bot.py` initializes NoneBot, registers the OneBot v11 adapter, applies the Windows selector event-loop policy, and loads `qwenbotq`. `qwenbotq/__init__.py` loads and validates configuration, imports fixed plugins, and conditionally imports optional plugins. Keep plugin import-time side effects and feature gates consistent with the corresponding config models.

Use `qwenbotq/config_model/` for configuration schema changes and `config.example.yml` for user-facing defaults/documentation. Use `qwenbotq/database/` for persistence models/helpers instead of embedding database access in matcher handlers. Keep shared message/reply behavior in `bot_utils.py`. Use relative imports within `qwenbotq`; the local `ehentaix` package is imported as an installed dependency.

The bot relies on external services and protocol behavior: MongoDB for persistence, OneBot v11 for messaging, and an HTTP file server whose configured `remote_host`/port must be reachable by the OneBot side. Avoid changing these connection defaults or startup sequencing without checking the deployment documentation.

## Documentation maintenance

`AGENTS.md`, `README.md`, and `USAGE.md` are living documents, both at the repository root and under `EHentaiX/` where applicable. Update them automatically, in the same change that makes the underlying code behave differently — do not wait to be asked. Whenever you modify anything those files describe (project layout, plugins and commands, configuration schema, dependencies, deployment steps, architecture, or the `ehentaix` API), update the corresponding `AGENTS.md`/`README.md`/`USAGE.md` to match. Any add, removal, or behavioral change to a user-facing command must be reflected in `USAGE.md` in the same change. If a change makes an existing statement inaccurate, correct it in the same change. Keep `README.md` user-facing (deployment, features, usage), `USAGE.md` command/usage documentation, and `AGENTS.md` agent-facing (layout, commands, conventions, edit boundaries). The `EHentaiX/README.md` is also the package readme referenced by `pyproject.toml`, so it must stay accurate for consumers of the standalone library.

## Conventions and safety

Match the existing Python style: standard-library imports, third-party imports, then local imports; async APIs for network/bot/database work; `logger` for runtime diagnostics rather than ad-hoc prints. Preserve the existing MIT copyright header in root project Python files. Keep secrets, cookies, tokens, and real deployment config out of tracked files; use `config.example.yml` placeholders and local `config.yml`/`cookies.json` only.

When changing a feature that is conditionally imported, test both the disabled/default configuration and the fully configured path where practical. Be careful with image/download code: it writes under runtime directories and exposes files through the configured HTTP server.
