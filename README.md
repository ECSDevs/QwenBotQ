# QQ 娱乐机器人

使用 Nonebot2 + NapCatQQ 驱动的娱乐型 QQ 机器人

## 功能特性

- **AI 对话**：接入 OpenAI 兼容 API，支持多模型、自定义提示词、工具调用与联网搜索（可选）。
- **会话上下文**：持久化对话上下文，接近上限时自动总结以继续长对话。
- **识图搜图**：图片搜索功能，可选 ExHentai 源（需 Cookies）。
- **撤回图片缓存**：对监听会话中被撤回的图片自动保存，支持超级用户检索与打包下载。
- **E-Hentai 下载**：内置 `ehentaix` 库，支持图库搜索、缩略图与整本下载。
- **娱乐功能**：积分/签到系统、绑定账号、抽奖等。
- **21点对战**：多人实时 21 点押注对战，支持大厅创建/加入/匹配，要牌、停牌、加倍与黑杰克 1.5 倍赔付，对局超时自动结算。
- **B站动态订阅**：订阅 UP 主动态并推送至指定群/用户（可选）。
- **自动更新**：独立于主插件的插件定时检查远端仓库，发现新提交后私信提醒超管，超管回复 `!update` 确认才拉取并重启（可选，配置 `autoupdate` 段后生效）。
- **超级用户管理**：私聊命令管理监听会话、撤回图、拉黑、续费等。

## 部署

### 环境要求

- Python 3.11
- MongoDB
- NapCatQQ / 其他 Onebot V11 协议驱动，设置正向 Websocket 连接
- Git
- OpenAI Format Api Key （若启用 AI 功能）

### 安装步骤

1. 克隆项目仓库

```bash
git clone https://github.com/originalFactor/QwenBotQ.git
cd QwenBotQ
```

2. 安装依赖

```bash
pip install poetry
poetry install
```

3. 编辑配置文件

`.env` 按需复制并填写：

```bash
cp .env.example .env
vim .env
```

`config.yml` 位于仓库根目录，**首次启动会自动按默认值生成，已有文件中缺失的字段也会自动补全为默认值**（不会覆盖已填写的取值），因此不复制示例也能直接运行。各字段的说明与示例见 `config.example.yml`；需要立即填写的项（MongoDB、API Key 等）可在启动生成后直接编辑 `config.yml`。

> 说明：补全使用 `ruamel.yaml` 的 round-trip 写回，只会追加缺失的键，你原有的注释、引号与排版都会保留。

4. 运行Bot

```bash
poetry run python bot.py
```

### 自动更新（可选）

在 `config.yml` 中填写 `autoupdate` 段后，机器人会每隔 `interval` 秒 `git fetch` 远端。若远端领先本地，会私信提醒所有超管（含领先提交数与提交摘要），超管回复 `!update` 后才会执行 `git pull --ff-only` 并重启（重启沿用当前启动命令）。同一批提交只提醒一次，不会反复骚扰；`!update` 也可随时手动触发，已是最新时只回复提示、不重启。该插件与主插件分开加载，主插件导入失败时仍能提醒并拉取修复。

注意：

- 只做快进拉取。本地有未提交改动或与远端分叉时拉取会失败，只在私聊与日志中报告，不会重启。
- 不会自动安装依赖。若远端改动涉及 `pyproject.toml`/`poetry.lock`，请手动执行 `poetry install` 后再确认更新，否则可能因缺少依赖启动失败。
- 机器人尚未连接（如刚启动）时提醒发送失败会在下个检查周期重试。
- 如需关闭，删除 `config.yml` 中的 `autoupdate` 段或设置 `enable: false`；关闭后 `!update` 会提示未启用。

## 开发与维护

`AGENTS.md`（根目录与 `EHentaiX/` 各有一份）是面向 AI 助手的维护说明，包含项目结构、常用命令、架构边界与约定。开发者修改代码时，应与代码同步更新 `AGENTS.md` 与 `README.md`，确保描述与实际行为一致。

## ⚖️ License Migration Notice

**Important:** This project has officially transitioned its licensing from **GPLv3** to **MIT** effective **February 10, 2026**.

### Dual-License Breakdown

- **Legacy Code:** All versions, tags, and commits submitted **prior to February 10, 2026**, remain licensed under the [GNU General Public License v3.0 (GPLv3)](https://www.gnu.org/licenses/gpl-3.0.html).
- **Current & Future Code:** All new versions, features, and commits submitted **on or after February 10, 2026**, are distributed under the [MIT License](https://mit-license.org/).

This transition is intended to provide maximum flexibility for our users and to encourage broader integration within the ecosystem.

## License

- [GPLv3 License](LICENSE-GPLv3) (Before 2026/2/11)
- [MIT License](LICENSE) (After 2026/2/11)
