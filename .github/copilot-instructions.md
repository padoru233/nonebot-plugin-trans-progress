# Copilot 使用说明

- 这是 Python 3.10+ 的 NoneBot2 插件，源码在 `src/nonebot_plugin_trans_progress/`，测试在 `tests/`。
- 依赖和工具配置由 `pyproject.toml` 管理，使用 `uv sync --locked` 安装锁定依赖。
- 修改后运行 `uv run poe test`；静态类型检查使用 `uvx basedpyright`，风格遵循 Ruff 配置。
- 保持 NoneBot 配置兼容环境变量，不在代码或测试输出中记录认证口令和数据库连接凭据。