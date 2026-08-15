# Repository Guidelines

## Core Principles

- 模块职责保持单一，依赖方向清晰，不得形成循环依赖。
- 自研应用的运行时配置统一由项目根目录的 `config.ini` 提供；LiteLLM 与 Caddy 的非秘密原生参数保留在各自配置文件中。代码中不得硬编码密钥、地址、模型名或功能开关。
- 日志集中配置、结构化输出，并在写入前完成脱敏和长度限制。
- HTTP、模型、数据库等昂贵资源在应用生命周期中创建一次并显式关闭，不得在模块导入或每次请求时创建。
- 代码变更应同步更新测试、配置示例与使用文档，不得通过降低检查标准掩盖问题。

## Project Structure & File Classification

仓库是 Python 3.12 的 LiteLLM 网关 MVP：`main.py` 为薄入口，`pyproject.toml` 与 `uv.lock` 管理依赖，Docker Compose 编排运行服务。当前布局如下：

```text
.
├── main.py                         # 薄启动入口
├── pyproject.toml / uv.lock        # 项目与锁定依赖
├── config.ini                      # 本地真实配置，不提交
├── config.example.ini              # 完整脱敏配置模板
├── compose.yaml / Dockerfile        # 本地服务编排与 API 镜像
├── gateway/Caddyfile                # 唯一宿主机入口
├── litellm/config.yaml              # LiteLLM 原生模型配置
├── migrations/                      # business 数据库迁移
├── scripts/                         # 初始化与冒烟验证
├── src/llm_central_gateway/
│   ├── app.py                      # 装配、生命周期与依赖注入
│   ├── settings.py                 # 配置读取、转换和校验
│   ├── logging.py                  # 日志、上下文与脱敏
│   ├── schemas.py                  # 共享数据模型
│   ├── database.py / models.py     # 数据库连接与业务表
│   ├── adapters/                   # LLM、HTTP、数据库适配器
│   ├── api/                        # 路由和传输层
│   └── compose_cli.py              # 安全传递本地配置给 Compose
└── tests/                           # pytest 测试
```

`main.py` 不包含业务逻辑、配置解析、客户端创建或日志实现。传输层只处理协议、鉴权入口、输入验证和响应转换；业务规则放入 `services/`。外部 SDK 细节必须封装在 `adapters/`，避免其类型扩散。不要建立含义模糊的 `utils.py`；按具体职责命名模块。测试结构尽量镜像 `src/`。

## Configuration & Security

`settings.py` 是自研代码读取 `config.ini` 的唯一入口，集中检查文件和字段是否存在，并完成类型、范围、路径及跨字段校验。缺失或非法配置应在启动阶段失败，错误消息只指出字段名，不暴露字段值。相对路径以项目根目录为基准，配置对象应不可变；其他模块只接收已校验的设置对象或明确参数。LiteLLM 与 Caddy 使用各自原生配置文件，但秘密值必须由 `compose_cli.py` 从 `config.ini` 注入，不得另建第二套秘密文件。

创建配置功能时，必须同时将 `config.ini` 加入 `.gitignore` 并提交字段一一对应的 `config.example.ini`。配置 section 按职责划分，字段使用 `UPPER_SNAKE_CASE`。新增、删除或改名配置项时，同步修改设置模型、示例文件和测试。不得提交或输出密钥、Token、Cookie、连接字符串、用户隐私数据、`.venv`、缓存或运行日志。所有外部输入均须在边界处验证；路径、查询和命令使用安全的解析或参数化机制。

## Logging & Resource Lifetimes

使用标准 `logging`，禁止用 `print` 代替运行日志。日志只在 `logging.py` 中初始化，各模块使用 `logging.getLogger(__name__)`。文件日志采用 UTF-8 JSON Lines 和轮转策略；级别、路径、大小、保留数、载荷开关及截断长度均来自配置。事件名使用稳定的点分小写格式，如 `http.request.complete`，时间使用带时区的 UTC，耗时字段统一为 `duration_ms`。

请求和下游调用应共享 `request_id`；Agent 模型与工具调用使用 `run_id`/`parent_run_id`。记录启动、关闭、请求、外部调用、重试、超时和降级的开始、完成与失败事件。默认不记录正文、提示词、模型输出或工具参数。任何级别均不得记录凭据；对象须递归脱敏并限制长度。异常堆栈只在负责重试、响应或终止的边界记录一次。

外部客户端、连接池和持久化后端由 `app.py` 创建、注入并按顺序关闭。模块导入不得读取秘密、连接网络、创建目录、配置日志或启动线程。请求处理器不得重建共享客户端。

## Coding Style & Naming Conventions

使用四空格缩进并遵循 PEP 8。模块、函数和变量使用 `snake_case`，类和数据模型使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。公共函数、类字段和边界接口必须有类型标注；避免无边界的 `Any`。Docstring 说明意图或非显然约束，不重复代码。不得静默捕获 `Exception`；应恢复、转换、重新抛出，或明确说明忽略原因。

项目使用 Ruff 负责格式化和 lint，使用 mypy 严格模式做类型检查；配置统一放在 `pyproject.toml`。

## Testing & Verification

测试使用 `pytest`，文件命名为 `test_*.py`，函数命名为 `test_<behavior>`。单元测试必须离线、可重复且不使用真实密钥；LLM、网络、数据库及遥测调用使用 mock、fake 或受控实例。重点覆盖路由、配置校验、响应规范化、提供商失败与资源清理。配置测试应覆盖缺失、空值、错误类型、越界和相对路径；日志测试应覆盖 JSON 格式、上下文隔离、递归脱敏、截断、轮转及重复初始化。修复缺陷时先添加可复现测试。

当前可用命令均从仓库根目录执行：

- `uv sync --all-groups --no-editable`：同步运行与开发依赖；当前 Python 会跳过隐藏 `.pth`，因此本项目明确使用非 editable 安装。
- `uv run --no-sync python scripts/bootstrap.py`：补全本地秘密并创建两个隔离数据库。
- `uv run --no-sync gateway-compose up -d --build`：启动 Redis、LiteLLM、FastAPI 和 Caddy。
- `uv run --no-sync python scripts/smoke_test.py`：运行免费健康检查；加 `--live` 才会产生一次真实模型费用。
- `uv lock --check`：检查锁文件是否与项目元数据一致。
- `uv run --no-sync ruff format --check . && uv run --no-sync ruff check .`：检查格式和 lint。
- `uv run --no-sync mypy src && uv run --no-sync pytest -q`：运行类型检查和完整测试。

依赖使用 `uv add <package>` 或 `uv add --dev <package>` 添加，不得手工编辑 `uv.lock`。

## Change, Commit & Pull Request Discipline

修改前阅读相关代码、测试、配置和文档，保留用户已有的无关变更。提交应聚焦单一逻辑变更；可使用 `feat:`、`fix:`、`refactor:`、`test:`、`docs:` 或 `chore:` 前缀，例如 `feat: add provider routing fallback`。仓库目前没有历史提交，因此此前不存在其他约定。

Pull Request 应说明动机、主要变更、配置或 API 影响及实际运行的验证命令，并链接相关 issue。行为变化附脱敏后的请求/响应示例；界面变化才需要截图。交付时说明已知限制和必要的后续步骤。
