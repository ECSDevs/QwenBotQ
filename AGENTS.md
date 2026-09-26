# QwenBotQ Agent Notes

## Purpose and layout

QwenBotQ is a Python NoneBot2 QQ entertainment bot using the OneBot v11 adapter. The root entry point is `bot.py`; the main plugin package is `qwenbotq/`.

- `qwenbotq/ai/`: optional OpenAI-compatible chat and tools integration.
- `qwenbotq/database/`: Beanie/Motor MongoDB documents and database helpers.
- `config/`: root-level standalone package for `config.yml` — Pydantic models, defaults, and the loader. It is independent of `qwenbotq` (importing it never executes `qwenbotq/__init__.py`) so both `qwenbotq` and `autoupdate.py` can share it. `config.yml` is resolved relative to the repository root (the package's parent), not the current working directory; on first load a missing file is generated from the models' defaults, and missing keys in an existing file are deep-filled from those defaults and written back; all `config.yml` IO goes through `ruamel.yaml` round-trip mode (`preserve_quotes` on, so numeric-looking strings stay quoted), so comments and layout survive write-back.
- `qwenbotq/__init__.py`: core only — injects truststore, loads `config.yml`, loads the third-party plugin dependencies (`nonebot_plugin_alconna`, `nonebot_plugin_apscheduler`) and then loads every feature as its **own** NoneBot sub-plugin (`qwenbotq:<feature>`) from the `get_features()` list, so one feature's import error is logged and skipped without taking down the rest. Differs from the feature modules by design; see "Architecture and edit boundaries".
- `qwenbotq/imagesearch/`, `fileserver.py`, `imagecache.py`: image search/download, HTTP file serving, and recalled-image caching.
- `binding.py`, `usersystem.py`, `lottery.py`, `bilinotice.py`, `superuser.py`: feature plugins; several are enabled only when their config section is populated.
- `blackjack.py`、`blackjack_logic.py`：21点多人押注小游戏（`blackjack_logic.py` 为纯规则逻辑，不依赖 NoneBot/数据库，单元测试直接加载；`blackjack.py` 为命令与内存态房间，key=会话ID，无数据库持久化，积分即时扣/退/结算，大厅/对局超时自动退款或强制结算）。
- `lognotice.py`: always-on loguru sink that forwards WARNING and above logs to every configured superuser's private chat. Registered via an `on_startup` hook that captures the running event loop and adds the sink with a self-name filter and a 5-second `(name, message)` dedup window to prevent recursion and flooding. Forwarding is scheduled with `asyncio.run_coroutine_threadsafe` so it works from any thread; sending failures are swallowed silently to avoid recursive logging.
- `autoupdate.py`: root-level plugin loaded by `bot.py` **separately** from `qwenbotq` (before it) and intentionally importing nothing from the `qwenbotq` package, so it still works when the main plugin fails to import. It never updates on its own: it reads the `autoupdate` section through `config.get_autoupdate_config()` (an absent or invalid section disables it without preventing the plugin from loading), and an `on_startup` task (cancelled on `on_shutdown`) runs `git fetch <remote>` then `git rev-list --count HEAD..<remote>/<branch>` every `interval` seconds and, when the remote is ahead, private-messages every superuser with the lead count and commit summary (`get_driver().config.superusers`, the same source the `config` package reads for `supermgr_ids`). The same remote head is reminded only once, and a message that could not be sent is not recorded so it retries on the next cycle. The `!update` command (private-message-only, `permission=SUPERUSER`, `priority=1`, `block=True`, same style as the `!getrecalls` family) re-checks, runs `git pull --ff-only <remote> <branch>` and restarts; it and the poll task share one `asyncio.Lock` to serialise git access. Restart spawns a detached "relauncher" process that waits for the current PID to exit (so ports are released) and then re-runs `[sys.executable, *sys.argv]` from the repository root, after which the current process calls `os._exit(0)`; `restart_command` overrides that. Do **not** rebuild the restart command from the OS process command line (`GetCommandLineW`/`/proc/self/cmdline`): virtualenv launchers record the base interpreter there, so replaying it drops the venv's site-packages. Git runs through `asyncio.to_thread(subprocess.run)` because `bot.py` forces `WindowsSelectorEventLoopPolicy` (no `create_subprocess_exec` on Windows).
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

`config.yml` lives at the repository root and is resolved relative to it (by the `config` package), not the current working directory, so commands may be run from anywhere. A missing file is generated from the models' defaults on first load, and missing keys in an existing file are filled in from those defaults and written back, so no manual copy step is required; `config.example.yml` is a fully commented field reference rather than a required starting point. Runtime deployment normally also needs MongoDB, a OneBot v11 forward WebSocket driver (such as NapCatQQ), and optional API services for enabled features.

Tests are currently live integration scripts rather than isolated unit tests:

```bash
poetry run pytest ehentaix/test_search.py
poetry run python ehentaix/test_exhentai_search.py  # requires local cookies.json
```

A full `poetry run pytest` collection currently fails because `test_exhentai_search.py` executes at import time and immediately opens `cookies.json`; do not interpret that as a product regression. These scripts also require network access.

## Architecture and edit boundaries

`bot.py` initializes NoneBot, registers the OneBot v11 adapter, applies the Windows selector event-loop policy, and loads `autoupdate` followed by `qwenbotq` as two independent plugins. `qwenbotq/__init__.py` is only a core: it loads and validates configuration, loads the third-party plugin dependencies, and then loads each feature as a separate NoneBot sub-plugin via `load_plugin(f"{__package__}.{feature}")` (plugin ids are `qwenbotq:<feature>`; the parent `qwenbotq` plugin must be loaded first, which NoneBot enforces). Add, remove, or reorder features through `get_features()` in that file and keep the fixed/optional gating consistent with the corresponding config models; the call order also determines the order of sections in the `帮助` image.

Failure isolation: a feature that raises while importing is caught by NoneBot's own `load_plugin`, its traceback is logged, the partially created plugin is reverted, and `load_features()` continues with the remaining features before emitting a single warning listing the failed ones (which `lognotice` then forwards to superusers). Two limits remain: (1) `database/`, `bot_utils.py`, `help.py`, `utils.py`, `models_dev.py` and `blackjack_logic.py` are shared plain modules, not plugins, so a failure there still breaks every feature importing it — keep them dependency-light; (2) `on_startup` hooks of all features run in one sequence, so an exception raised there (e.g. the file server port being taken, MongoDB init) still aborts startup for the whole bot; matcher handlers are already isolated per-event by NoneBot. A feature that fails halfway through its module body may still have contributed text to `Help` via `append_help`, since the help sections are registered at import time.

`autoupdate.py` is the one plugin that must stay outside `qwenbotq/` and must not import from it (importing any submodule executes `qwenbotq/__init__.py`); instead it gets its settings from the independent root `config` package (`config.get_autoupdate_config()`, schema in `config/autoupdate.py`) and resolves the git repository relative to its own file. Keep its restart logic independent of NoneBot internals so a broken main plugin can still be updated. A consequence of that decoupling is that its `!update` command is absent from the `帮助` image (which is assembled from `qwenbotq` features); it is documented in `USAGE.md` instead — if you ever want it listed, add the line on the `qwenbotq` side rather than importing `qwenbotq.help` here.

Use `config/` for configuration schema changes (including the `autoupdate` section in `config/autoupdate.py`) and `config.example.yml` for user-facing defaults/documentation. `config/loader.py` derives generation/completion generically from each model's `model_fields`, so a new field with a default is created and back-filled automatically; fields marked `exclude=True` (such as `supermgr_ids`, which is read from NoneBot's superusers) are never written to `config.yml`. It reads and writes `config.yml` with `ruamel.yaml` in round-trip mode, so comment/quote/indent preservation is that library's responsibility (not PyYAML's) — keep using `ruamel.yaml` for any new config IO. Use `qwenbotq/database/` for persistence models/helpers instead of embedding database access in matcher handlers. Keep shared message/reply behavior in `bot_utils.py`. Use relative imports within `qwenbotq` (the root `config` package is imported absolutely); the local `ehentaix` package is imported as an installed dependency.

The bot relies on external services and protocol behavior: MongoDB for persistence, OneBot v11 for messaging, and an HTTP file server whose configured `remote_host`/port must be reachable by the OneBot side. Avoid changing these connection defaults or startup sequencing without checking the deployment documentation.

## Documentation maintenance

`AGENTS.md`, `README.md`, and `USAGE.md` are living documents, both at the repository root and under `EHentaiX/` where applicable. Update them automatically, in the same change that makes the underlying code behave differently — do not wait to be asked. Whenever you modify anything those files describe (project layout, plugins and commands, configuration schema, dependencies, deployment steps, architecture, or the `ehentaix` API), update the corresponding `AGENTS.md`/`README.md`/`USAGE.md` to match. Any add, removal, or behavioral change to a user-facing command must be reflected in `USAGE.md` in the same change. If a change makes an existing statement inaccurate, correct it in the same change. Keep `README.md` user-facing (deployment, features, usage), `USAGE.md` command/usage documentation, and `AGENTS.md` agent-facing (layout, commands, conventions, edit boundaries). The `EHentaiX/README.md` is also the package readme referenced by `pyproject.toml`, so it must stay accurate for consumers of the standalone library.

## Conventions and safety

Match the existing Python style: standard-library imports, third-party imports, then local imports; async APIs for network/bot/database work; `logger` for runtime diagnostics rather than ad-hoc prints. Preserve the existing MIT copyright header in root project Python files. Keep secrets, cookies, tokens, and real deployment config out of tracked files; use `config.example.yml` placeholders and local `config.yml`/`cookies.json` only.

When changing a feature that is conditionally imported, test both the disabled/default configuration and the fully configured path where practical. Be careful with image/download code: it writes under runtime directories and exposes files through the configured HTTP server.
