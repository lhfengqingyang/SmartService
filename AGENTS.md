# SmartService AI 客服项目：长期开发规则

本文件是项目唯一的 Agent 开发规则。阶段计划见 `docs/ROADMAP.md`，实际进度见 `docs/PROJECT_STATUS.md`，接口约定见 `docs/API_CONTRACTS.md`；恢复工作时还需核对实际代码和 Git 状态。

## 一、项目目标

开发一个简化版智能客服系统，包含：

1. 知识库文档上传、解析、分块、向量化和存储。
2. 基于 PostgreSQL + pgvector 的知识检索。
3. 基于可配置对话模型的 RAG 问答，当前本地演示选择千问 `qwen3.7-flash`；回答应包含知识来源，证据不足时明确说明无法确定。
4. 使用 smolagents 实现工具调用，能够查询模拟订单、检查退款资格。
5. 业务逻辑（订单、退款）和 AI 服务（RAG、Agent 编排）均在 Python 中实现。
6. 提供 Swagger API 文档、自动化测试、README 和可复现的本地启动流程。

项目以真实可运行、可演示、可解释为优先，适合作为求职展示项目；不追求一开始就搭建复杂架构。

## 二、固定技术选型

### Python 服务（AI + 业务）
- Python 3.14+（当前环境 3.14.7）
- FastAPI
- smolagents
- 对话模型通过 OpenAI 兼容接口调用；本地演示优先用千问 `qwen3.7-flash`，保留智谱 `glm-4.7-flash` 可切换配置
- 独立的 Embedding 模型或 API，负责文本向量化
- SQLAlchemy、psycopg、pgvector
- pytest

### 数据库与环境
- PostgreSQL 16 + pgvector
- Docker Compose 用于本地数据库启动（需安装 Docker）
- 使用 `ai` 和 `biz` schema 区分 AI 数据与业务数据

在 Windows 上使用一个 VS Code 工作区和项目虚拟环境开发 Python 服务，使用 Docker Desktop 的 WSL 2 后端运行数据库。项目不需要 Java、Maven、第二个服务或第二套开发环境。Windows 的 `.venv` 仅供 Windows Python 使用；若以后选择在 WSL 内运行 Python，需在 WSL 内另建虚拟环境，不复用 Windows 的 `.venv`。

如果本地环境与上述选型存在冲突，先检查并说明实际问题，提出最小改动方案，不要擅自更换技术栈。

## 三、项目架构

```text
SmartService/
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── .gitignore
├── .env.example
├── docs/
│   ├── PROJECT_STATUS.md
│   ├── ROADMAP.md
│   └── API_CONTRACTS.md
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── ai/                  # AI、RAG、Agent 编排
│   │   ├── __init__.py
│   │   ├── rag.py           # RAG 问答逻辑
│   │   ├── agent.py         # smolagents Agent 编排
│   │   ├── tools.py         # Agent 工具定义
│   │   └── embedding.py     # Embedding 调用
│   ├── biz/                 # 业务逻辑（订单、退款）
│   │   ├── __init__.py
│   │   ├── orders.py        # 订单查询
│   │   └── refunds.py       # 退款资格检查与申请
│   ├── db/                  # 数据库模型与连接
│   │   ├── __init__.py
│   │   ├── connection.py    # 数据库连接管理
│   │   ├── models.py        # SQLAlchemy 模型
│   │   └── vector.py       # pgvector 相关
│   └── api/                 # API 路由
│       ├── __init__.py
│       ├── knowledge.py     # 知识库相关接口
│       ├── chat.py          # 问答接口
│       ├── orders.py        # 订单接口
│       └── refunds.py       # 退款接口
├── tests/
│   ├── __init__.py
│   ├── test_rag.py
│   ├── test_orders.py
│   └── test_refunds.py
├── pyproject.toml
├── db/
│   └── init/
│       └── 001_schema.sql
└── data/
    └── knowledge/
```

开始前先检查当前工作区。如果已有文件、代码或 Git 历史，不得直接覆盖；先检查并在原有基础上增量修改。

## 四、核心业务边界

### 1. RAG 知识问答
- 只使用实际检索到的知识片段作为业务知识依据。
- 回答中应尽可能包含文档名称、片段或其他可追溯来源。
- 检索不到可靠证据时，明确表示现有知识库无法确认，不得编造政策。
- 必须使用真实 Embedding 模型或 API，不允许用随机向量冒充真实向量化。
- 不得把模型生成的文字当作真实检索结果或测试证据。

### 2. Agent 工具调用
- Agent 可以调用业务模块的订单查询、退款资格检查等函数。
- Python Agent 通过明确的业务函数或服务接口获取结果；不得绕过业务模块直接修改业务数据。
- 订单信息和退款资格必须以业务模块的实际返回结果为准。
- Agent 不得自行绕过业务规则。
- 对工具调用参数进行校验，并处理超时、异常和无效响应。

### 3. 退款功能
- 只实现模拟退款，不接入真实支付渠道。
- 业务模块负责退款资格判断。
- 创建退款申请前必须设置明确的确认边界，不能因为模型自行决定就直接创建申请。
- 实现必要的幂等机制、数据库约束和并发保护。
- 不要把模拟退款描述成真实退款成功。

### 4. 文件上传与安全
- 第一版只允许 Markdown 和 TXT 文件。
- 校验文件类型、大小和文件名，防止路径穿越。
- 不允许将 API Key、密码、数据库凭据提交到 Git。
- 通过环境变量读取密钥，`.env.example` 只能放占位值。
- 不要在日志、README 或项目文档中输出真实密钥。
- `userId` 等请求参数不能被当作已经完成身份认证的证明；需要说明 MVP 的鉴权限制。

## 五、长期项目上下文管理规则（必须执行）

本项目不能依赖聊天记录保存开发进度。每次开始任务、结束阶段、切换会话时，都必须遵守以下规则。

### 1. AGENTS.md：长期开发规则
在项目根目录维护 `AGENTS.md`，记录：
- 项目目标和固定技术栈。
- 系统架构及各模块职责。
- 业务规则与安全边界。
- 代码规范、测试要求和禁止事项。
- 阶段开发与文档维护规则。

### 2. PROJECT_STATUS.md：当前进度
创建或维护 `docs/PROJECT_STATUS.md`，记录：
- 当前正在进行的阶段。
- 已完成的功能。
- 尚未完成的功能。
- 实际执行过的测试命令、结果及失败信息。
- 当前阻塞问题及排查情况。
- 已知缺陷和技术债务。
- 当前配置方式、接口变化和下一步具体任务。
- 最近一次更新日期。

只有实际实现并验证成功的功能才能标记为完成。

### 3. ROADMAP.md：阶段计划
创建或维护 `docs/ROADMAP.md`，记录：
- 全部开发阶段及顺序。
- 每个阶段的目标。
- 具体任务和验收标准。
- 阶段间依赖关系。

### 4. API_CONTRACTS.md：接口约定
创建或维护 `docs/API_CONTRACTS.md`，记录：
- 服务接口清单。
- 请求参数、响应结构、HTTP 状态码及错误码。
- 数据库表和字段的关键约定。
- Agent 调用工具的参数和返回格式。
- 接口变更的兼容性影响。

### 5. 每次开始任务时
在修改代码前：
1. 阅读 `AGENTS.md`。
2. 阅读 `docs/PROJECT_STATUS.md`。
3. 阅读 `docs/ROADMAP.md`。
4. 如果涉及接口或数据库，再阅读 `docs/API_CONTRACTS.md`。
5. 检查实际代码、Git 状态和相关测试。
6. 对照文档确认当前进度，找出本次任务的范围和依赖。
7. 如果文档与代码冲突，指出冲突并核实，以实际代码、Git 状态和测试结果为优先依据。
8. 对较大任务先简述拟修改的文件、实现内容和验收方式。

### 6. 每个阶段结束时
必须执行以下工作：
1. 运行当前环境实际支持的测试和检查命令。
2. 如实汇报通过、失败、跳过和未执行的测试；未运行的测试不得写成通过。
3. 更新 `docs/PROJECT_STATUS.md`。
4. 如开发计划有变化，更新 `docs/ROADMAP.md`。
5. 如接口、数据库结构或工具协议发生变化，更新 `docs/API_CONTRACTS.md`。
6. 发现新的长期规则或架构约束时，更新本文件。
7. 检查是否有密钥、临时文件、无关改动或不应提交的配置。
8. 汇报修改文件、启动方式、测试结果、已知问题和下一步任务。

### 7. 中断后恢复工作

新开聊天、重启工具或切换 AI 工具后，先读取本文件、项目状态、路线图、相关接口文档和实际代码。发现不一致时，按实际代码与 Git 状态、实际测试结果、项目文档、历史聊天记录的顺序核实；不要要求用户重复提供已写入项目文件的信息。

## 六、开发纪律

- 一次只实现当前阶段的目标。
- 阶段目标、任务、验收标准和依赖以 `docs/ROADMAP.md` 为准，不在本文件中重复维护。
- 不要因为追求架构完整而过早引入 Redis、Kafka、多 Agent、微服务注册中心或前端。
- 优先使用简单、可测试、易维护的实现。
- 依赖安装前先检查现有环境和依赖文件。
- 不要擅自删除已有代码或覆盖用户配置。
- 不要伪造命令执行结果、测试结果、API 响应或模型调用结果。
- 对外部 API、Embedding 维度、Docker 镜像和环境依赖等不确定事项，先实际验证。
- 遇到阻塞问题时，先保留已经完成的工作，提供具体错误和可执行的排查方案。
- 未经确认，不要擅自大规模重构或改变固定技术栈。

## 七、依赖安装方式

使用项目虚拟环境中的 Python 安装依赖：
```powershell
& ".\.venv\Scripts\python.exe" -m pip install <package>
```

不要使用系统级 pip 或全局 Python。
