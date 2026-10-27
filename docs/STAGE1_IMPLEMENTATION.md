# 阶段 1 实现记录：数据库与服务骨架

**记录日期：2026-10-22**  
**当前结论：代码、离线测试和真实 PostgreSQL 联调均已完成，阶段 1 已验收。**

## 本阶段做了什么

项目采用 Python-only 单服务：FastAPI 提供 HTTP 接口，PostgreSQL 16 + pgvector 计划由 Docker Compose 在本机启动。当前只实现服务入口、数据库结构和就绪检查；知识导入、RAG、订单、退款及 Agent 均属于后续阶段。

| 文件 | 当前职责 |
|------|----------|
| `docker-compose.yml` | 定义 PostgreSQL 16 + pgvector 容器、健康检查、本地端口和持久化数据卷 |
| `db/init/001_schema.sql` | 首次初始化数据卷时创建 `vector` 扩展、`ai`/`biz` schema 和五张基础表 |
| `app/config.py` | 从项目根目录的 `.env`/环境变量读取 `DATABASE_URL` |
| `app/db/connection.py` | 创建 SQLAlchemy Engine，执行数据库就绪查询 |
| `app/main.py` | 提供 `/health` 和 `/health/db`，数据库不可用时返回统一的 503 响应 |
| `tests/test_health.py` | 测试存活检查及数据库检查成功、失败两条路径；数据库检查被替换为测试函数 |
| `pyproject.toml` | 声明依赖并限制 setuptools 只发现 `app` 包 |

请求链路：`GET /health/db` -> FastAPI 路由 -> `check_database()` -> SQLAlchemy Engine -> psycopg 驱动 -> PostgreSQL。就绪查询同时检查 `vector` 扩展和五张基础表；`GET /health` 不依赖数据库。

## SQLAlchemy 目前用在哪里

`app/db/connection.py` 用 `create_engine()` 创建连接引擎，并用 `@lru_cache(maxsize=1)` 在进程内复用；`pool_pre_ping=True` 检查连接池中的旧连接，`connect_timeout=3` 限制建立连接的等待时间。`engine.connect()` 和 `text()` 执行一条只读 SQL，核对扩展与表是否存在。URL 中的 `postgresql+psycopg` 指定实际的 PostgreSQL 驱动为 psycopg。

这里**还没有 SQLAlchemy ORM 模型、Session、CRUD 或 `create_all()`**。表结构的唯一现有定义是 `db/init/001_schema.sql`；SQLAlchemy 当前是连接管理和就绪检查工具。`pgvector` 的数据库扩展已写入初始化 SQL，Python `pgvector` 包虽已安装，但尚未用于向量读写；Embedding 模型与维度也尚未实测。不要把依赖已安装理解成 RAG 已实现。

## 已验证与未验证

上一轮实际执行的检查：

| 检查 | 结果 |
|------|------|
| `& ./.venv/Scripts/python.exe -m pip install -e ".[dev]"` | 修正 setuptools 包发现配置后成功 |
| `& ./.venv/Scripts/python.exe -m pytest -q` | 3 passed；数据库分支使用替换函数，**不是真实连接测试** |
| `& ./.venv/Scripts/python.exe -m ruff check app tests` | All checks passed |
| `& ./.venv/Scripts/python.exe -m pip check` | No broken requirements found |
| 运行 Uvicorn 后请求 `GET /health` | HTTP 200，返回版本和 `ok` |
| 数据库未运行时请求 `GET /health/db` | HTTP 503，返回 `DATABASE_UNAVAILABLE` |

2026-10-22 安装并启动 Docker Desktop 后，已完成真实联调：Docker Engine 使用 `desktop-linux` 上下文和 WSL2 内核；Compose 拉取 `pgvector/pgvector:0.8.7-pg16-bookworm` 并将容器启动为 healthy；初始化日志显示扩展、两个 schema 和五张表创建成功。容器内查询确认 pgvector 0.8.7 与五张表存在，Python `check_database()` 成功，`GET /health/db` 实际返回 HTTP 200。详细环境状态与检查结论见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

## 已执行的真实数据库验收

1. `docker version`：Client/Server 29.9.2，Docker Desktop 4.96.1，Linux Engine 使用 WSL2 内核。
2. `docker compose version`：5.6.0；`docker compose up -d` 成功创建网络、数据卷和数据库容器。
3. `docker compose ps`：`smartservice-db-1` 为 healthy，端口映射为 `127.0.0.1:5432->5432`。
4. 容器内 SQL 查询：pgvector 0.8.7、`ai`/`biz` schema 和五张表均存在。
5. 项目虚拟环境执行 `check_database()`：成功；实际请求 `/health` 与 `/health/db`：均返回 HTTP 200。

本地 `.env` 已创建并被 `.gitignore` 排除。初始化 SQL 只在新数据卷首次创建时自动执行，排查时不要随意删除现有数据卷。

下一阶段先实测真实 Embedding 的向量维度，再确定向量列约束和索引。退款幂等、唯一约束及并发保护留待阶段 4；目前的退款表不能代表这些业务规则已实现。
