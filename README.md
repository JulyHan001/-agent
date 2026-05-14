# 求职面试 Agent

这是一个按阶段演进的求职助手项目。当前版本已经具备基础聊天、历史会话、会话记忆、JD 分析和简历定制能力，并补上了前后端主链路回归验证。

当前已具备：
- Next.js 聊天界面
- FastAPI 聊天接口
- 历史会话持久化与恢复
- 结构化聊天响应
- 会话记忆分层展示
- `analyze_jd` / `resume_tailor` 工具
- 后端联调脚本
- 前端 E2E 回归测试骨架

## 本地启动

建议环境：
- `Node.js 20+`
- `Python 3.11` 或 `3.12`

### 1. 启动后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

常用配置：
- `SQLITE_PATH`
- `CHAT_CONTEXT_MESSAGE_LIMIT`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `MOCK_LLM`

### 2. 启动前端

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

默认访问地址：
- 前端：[http://127.0.0.1:3000](http://127.0.0.1:3000)
- 后端健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 3. 快捷重启

```powershell
.\restart-backend.ps1
.\restart-frontend.ps1
.\restart-all.ps1
```

## 测试

### 后端联调脚本

```powershell
cd backend
.venv\Scripts\python.exe scripts\integration_check.py
```

### 后端 smoke 测试

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests\test_smoke.py -q
```

### 前端 E2E

前端 E2E 使用 Playwright，设计目标是验证：
- 页面可以打开
- 历史会话和记忆区块可以渲染
- 聊天发送后主链路可用
- JD 分析区块可以展示结果

安装与运行：

```powershell
cd frontend
npm install
npx playwright install chromium
npm run test:e2e
```

为了让 E2E 稳定、不依赖真实模型波动，建议搭配后端 `MOCK_LLM=true` 运行。

## 当前接口

### `GET /health`

返回服务状态。

### `GET /api/sessions`

返回历史会话摘要列表。

### `GET /api/sessions/{session_id}`

返回单个会话及全部消息、记忆信息。

### `GET /api/tools`

返回当前已注册工具及 schema 定义。

### `POST /api/chat`

示例：

```json
{
  "session_id": "optional-session-id",
  "message": "我想准备后端开发实习面试，应该先做什么？"
}
```

### `POST /api/analyze/jd`

用于单独分析 JD。

### `POST /api/tailor/resume`

用于按目标 JD 生成最小简历定制建议。

## GitHub 托管与 CI 约定

当前项目计划先完成 GitHub 托管与 CI 基线，再进入 `M5` 开发。

- 远程仓库：`https://github.com/JulyHan001/-agent`
- 从 `M4.5` 起，每次有效代码更新都必须先完成本地验收，再推送到 GitHub
- 未通过 GitHub Actions CI 的代码，不应合并到 `main`
- 每个稳定里程碑都应创建 Tag，便于后续回滚

当前 CI 基线覆盖：

- `repo-hygiene-check`
- `backend smoke test`
- `backend auth isolation test`
- `backend integration_check`
- `frontend lint`
- `frontend build`

## 下一步

建议按这个顺序继续推进：

1. 完成 `M4.5`：GitHub 托管、CI 基线与版本回滚机制。
2. 完成 `M4.6`：将 `SQLite` 升级为 `PostgreSQL`。
3. 在 `M4.5` 和 `M4.6` 验收通过后进入 `M5`。
4. `M5` 稳定后再进入部署上线与 `CD` 自动化发布。
