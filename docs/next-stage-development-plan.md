# 下一阶段开发计划

## 1. 执行原则

- 严格按里程碑顺序推进：`M1 -> M2 -> M3 -> M4 -> M4.5 -> M4.6 -> M5 -> M6`
- 每完成一个里程碑，必须执行代码验收
- 登录系统放在最后一阶段
- 前端美化和左侧历史会话布局修正放在最后一阶段
- 未完成长期记忆前，不进入标准函数调用工具层开发
- `M4.5` 起进入 GitHub 托管规范：每次有效代码更新都必须先完成本地验收，再进入 GitHub 托管并通过 CI

## 2. 当前总体状态

- `M1`：已完成，已验收
- `M2`：已完成，已验收
- `M3`：已完成，已验收
- `M4`：已完成，已验收
- `M4.5`：未开始
- `M4.6`：未开始
- `M5`：未开始
- `M6`：未开始

## 3. 里程碑状态

### M1：长期记忆数据底座

- 状态：`已完成`
- 验收：`已通过`

已完成内容：

- 引入 `users` 数据表
- 为 `sessions` 增加 `user_id`
- 增加 `user_memory` 长期记忆存储
- 在记忆模型中引入 `scope` 和 `source_type`
- 保留默认用户以兼容当前未登录链路

验收记录：

- `pytest backend/tests/test_smoke.py -q`
- `backend/scripts/integration_check.py`

### M2：长期记忆主链路接入

- 状态：`已完成`
- 验收：`已通过`

已完成内容：

- 将用户长期记忆注入聊天主链路
- 从 `session_memory.stable_profile` 自动提炼长期记忆
- 新会话可继承同一用户的长期背景
- 长期记忆支持手动查询、写入、删除
- 增加长期记忆候选池 `user_memory_candidates`
- 实现“安全直写 + 待确认候选”双通道
- 增加候选记忆查询、批准、拒绝接口
- 增加更细粒度的长期记忆冲突分流
- 为验收补充稳定的 `mock_llm` 记忆提取链路

本阶段接口：

- `GET /api/memory/user`
- `PUT /api/memory/user`
- `DELETE /api/memory/user/{key}`
- `GET /api/memory/user/candidates`
- `POST /api/memory/user/candidates/{candidate_id}/approve`
- `POST /api/memory/user/candidates/{candidate_id}/reject`

验收记录：

- `backend/scripts/integration_check.py`
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -q`

本轮验收结果：

- 跨会话长期记忆可读取
- 短期状态不会无脑继承到新会话
- 候选记忆批准链路通过
- 候选记忆拒绝链路通过
- `smoke test` 通过
- 集成检查通过

### M3：标准工具调用层

- 状态：`已完成`
- 验收：`已通过`

计划目标：

- 将当前“规则触发 + 本地执行”升级为标准函数调用工具层
- 统一工具定义：`name / description / input_schema / output_schema / execute`
- 引入工具调用日志
- 加入工具失败降级策略
- 明确工具结果与长期记忆的边界

当前执行切分：

- `M3.1`：工具定义抽象统一与调用日志落库 `已完成`
- `M3.2`：模型驱动的工具选择主链路接入 `已完成`
- `M3.3`：工具失败降级与工具结果分级写入边界 `已完成`
- `M3.4`：代码验收与回归验证 `已完成`

已完成内容：

- 工具层从“直接规则触发执行”重构为“工具选择 -> 工具执行 -> 结果回传”的两阶段结构
- 统一工具定义，补齐 `selection_mode / input_schema / output_schema`
- 新增 `ToolChoice`、`ToolSelectionResult`、`ToolExecutionLog` 模型
- 聊天主链路接入模型驱动的工具选择，并保留规则兜底
- 新增 `tool_execution_logs` 落库与查询能力
- 工具执行结果新增 `status / error_message`，支持 `success / failed / skipped`
- 聊天主链路增加工具失败降级，工具异常不会中断普通对话
- 明确工具结果与长期记忆边界：当前长期记忆同步仅接收 `user/manual` 来源事实，不将工具结果直接写入长期记忆
- 新增 `GET /api/sessions/{session_id}/tool-logs` 用于验收和排查

验收记录：

- `backend/scripts/integration_check.py`
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -q`

本轮验收结果：

- JD 自动识别后可进入工具选择与执行链路
- 工具调用记录会回传到会话消息中
- 工具执行日志可稳定落库并查询
- 工具状态字段 `status` 已进入接口输出
- 工具执行失败时主对话链路可继续工作
- `smoke test` 通过
- 集成检查通过

### M4：登录、鉴权与前端收尾

- 状态：`已完成`
- 验收：`已通过`

计划目标：

- 用户注册、登录、鉴权接入
- 多用户会话隔离
- 多用户长期记忆隔离
- 前端左侧历史会话区域高度与布局修正
- 前端统一美化收尾

已完成内容：

- 已接入用户注册、登录、`Bearer Token` 鉴权与当前用户解析
- 已补充支持 `QQ 邮箱` 与 `中国大陆手机号` 两种注册登录入口
- 已将会话列表、会话详情、长期记忆、候选池、工具日志切换为按登录用户隔离
- 已保留默认本地用户兼容路径，避免历史单用户链路直接失效
- 前端已接入登录、注册、退出登录与本地登录态恢复
- 前端历史会话侧栏已改为固定高度加内部滚动，避免左侧区域无限拉长

本阶段验收结果：

- `frontend: npm run build` 通过
- `backend/scripts/integration_check.py` 通过
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py backend/tests/test_auth_isolation.py -q` 通过

#### M4-auth：手机号验证码注册登录补强

- 状态：`已完成`
- 验收：`已通过`

目标：

- 将当前认证能力收敛为“仅支持中国大陆手机号注册登录”
- 引入短信验证码链路，替代当前直接账号注册登录方式
- 注册时通过后端查库严格判定手机号是否已注册
- 登录时通过后端查库严格判定手机号是否存在
- 为后续接入真实短信服务保留稳定接口

执行切分：

- `M4-auth.1`：数据层收敛为手机号账号
- `M4-auth.2`：验证码表与验证码服务
- `M4-auth.3`：短信发送通道与 mock 能力
- `M4-auth.4`：发送验证码接口
- `M4-auth.5`：手机号注册流程
- `M4-auth.6`：手机号登录流程
- `M4-auth.7`：前端认证页改造
- `M4-auth.8`：安全与风控补强
- `M4-auth.9`：测试与验收

计划内容：

- 仅保留 `11 位大陆手机号` 作为当前主账号标识
- 注册流程改为：手机号 + 验证码 + 查库判重 + 创建用户 + 登录态签发
- 登录流程改为：手机号 + 验证码 + 查库确认存在 + 登录态签发
- 新增验证码发送、过期、冷却、错误次数、一次性消费能力
- 短信发送先走 `mock`，部署前再接真实短信服务
- 前端改为手机号输入框、验证码输入框、发送按钮和倒计时

验收要求：

- 未注册手机号可完成验证码注册
- 已注册手机号再次注册会被后端拒绝
- 已注册手机号可完成验证码登录
- 未注册手机号不能直接登录
- 错误验证码、过期验证码、已消费验证码均会失败
- 前端 `npm run build` 通过
- 后端 `integration_check` 与 `pytest` 通过

已完成结果：

- 当前认证主链路已收敛为“仅支持中国大陆手机号验证码注册登录”
- 已新增验证码发送接口、验证码存储表、验证码冷却与过期控制
- 注册流程已支持后端查库判定手机号是否已注册
- 登录流程已支持后端查库判定手机号是否存在
- 前端认证页已改造为手机号输入、验证码发送、验证码登录/注册和倒计时
- 当前短信发送为 `mock` 模式，开发环境可直接返回验证码用于联调

本阶段验收结果：

- `frontend: npm run build` 通过
- `backend/scripts/integration_check.py` 通过
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py backend/tests/test_auth_isolation.py -q` 通过

### M4.5：GitHub 托管、CI 基线与版本回滚机制

- 状态：`进行中`
- 验收：`未开始`

目标：

- 在 `M5` 开始前完成项目 GitHub 托管准备与首次托管
- 建立“每次代码更新都先验收、再推送、可追踪、可回滚”的工程化基线
- 先落地 `CI`，先定义 `CD` 规则但暂不启用自动部署
- 为后续 `M5` 和部署阶段提供稳定的版本管理与回滚能力

GitHub 仓库：

- 远程仓库：`https://github.com/JulyHan001/-agent`

执行切分：

- `M4.5.1`：仓库清理与 Git 托管准备 `进行中`
- `M4.5.2`：Git 分支与版本管理规范 `已完成`
- `M4.5.3`：GitHub 首次托管 `进行中`
- `M4.5.4`：GitHub Actions CI 基线接入 `进行中`
- `M4.5.5`：CI 准入门禁固化 `进行中`
- `M4.5.6`：版本回滚与里程碑 Tag 机制
- `M4.5.7`：CD 规则预定义但暂不启用

计划内容：

- 清理不应入库内容：
- `.venv`
- `node_modules`
- 本地 `SQLite` 数据文件
- 日志、缓存、临时文件
- 本地 `.env`
- 补齐仓库工程化基础文件：
- `.gitignore`
- `.env.example`
- `README` 中的启动、测试、验收说明
- 建立 GitHub 托管规范：
- `main` 作为受保护主干分支
- 日常开发使用 `feature/*` 分支
- 不允许未通过 CI 的代码进入 `main`
- 建立每次更新后的固定流程：
- 本地改代码
- 本地执行阶段验收
- 提交到 `feature/*` 分支
- 推送到 GitHub
- 触发 GitHub Actions CI
- CI 全绿后再合并到 `main`
- 每完成一个稳定阶段后创建里程碑 Tag，便于后续回滚
- 先落地 `CI`，`CD` 仅先定义门禁规则，不在本阶段做生产自动部署

验收要求：

- 项目完成首次 GitHub 托管
- `main` 受保护，未通过 CI 不允许合并
- 本地与 GitHub 上的 CI 流程可稳定运行
- 至少完成一次从本地修改到 GitHub CI 通过的完整演练
- 可基于 Tag 或历史提交执行版本回滚
- 本阶段验收命令：
- `backend/scripts/integration_check.py`
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py backend/tests/test_auth_isolation.py -q`
- `frontend npm run build`

当前进展：

- 已完成开发计划文档并入 GitHub 托管、CI/CD 门禁与回滚规范
- 已初始化本地 Git 仓库并接入远程仓库 `origin`
- 已补强根目录 `.gitignore` 与前端子目录 `.gitignore`
- 已将 GitHub Actions CI 调整为当前阶段的基线门禁：
- `repo-hygiene-check`
- `backend-test`
- `integration-check`
- `frontend-build`
- 已完成一轮本地验收：
- `backend/scripts/integration_check.py` 通过
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py backend/tests/test_auth_isolation.py -q` 通过
- `frontend npm run build` 通过
- 已完成本地首次提交：`147d47c chore: initialize github managed project baseline`
- 已完成首次推送，当前主干提交：`9293f51 chore: merge remote bootstrap commit`
- 待完成 GitHub 侧 CI 绿灯验证与 `main` 保护配置

### M4.6：PostgreSQL 持久化升级（M5 前置）

- 状态：`未开始`
- 验收：`未开始`

目标：

- 在 `M5` 开始前，将当前 `SQLite` 持久化底座升级为 `PostgreSQL`
- 为后续 `LangGraph` 图状态、checkpoint、中断恢复、多用户长期状态提供稳定数据底座
- 避免在 `M5` 完成后再做大规模数据层迁移

执行切分：

- `M4.6.1`：数据库访问层抽象改造
- `M4.6.2`：PostgreSQL 连接配置接入
- `M4.6.3`：建表与迁移机制建立
- `M4.6.4`：SQLite 历史数据迁移
- `M4.6.5`：现有核心链路 PostgreSQL 回归
- `M4.6.6`：CI 增加数据库迁移检查

计划内容：

- 将当前 `sqlite3 + 本地文件` 存储切换为 `PostgreSQL`
- 覆盖以下核心数据：
- `users`
- `sessions`
- `messages`
- `session_memory`
- `user_memory`
- `user_memory_candidates`
- `tool_execution_logs`
- `auth_verification_codes`
- 建立数据库迁移机制
- 补齐历史数据迁移脚本
- 在 CI 中新增数据库初始化与迁移检查
- 确保 `M1-M4-auth` 既有能力在 PostgreSQL 上全部可用

验收要求：

- 本地 PostgreSQL 可正常启动并被后端连接
- 核心链路回归通过：
- 手机号注册/登录
- 多用户隔离
- 多会话隔离
- 短期记忆
- 长期记忆
- 候选池
- 工具日志
- JD 分析
- CI 新增数据库迁移检查并通过
- 本阶段验收命令：
- `backend/scripts/integration_check.py`
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py backend/tests/test_auth_isolation.py -q`
- `frontend npm run build`

### M5：LangGraph 图式运行时、标准工具调用与记忆边界治理

- 状态：`未开始`
- 验收：`未开始`

计划目标：

- 以 `LangGraph` 作为 `M5` 的主编排运行时，承接后续工具调用、人工审核、恢复执行与可视化能力
- 把当前“模型辅助选择 + 后端本地执行”升级为标准原生工具调用闭环
- 支持单轮多步工具链路，而不是只执行一次工具
- 支持任务中断、人工审核后继续执行、跨轮恢复执行
- 让 `ReAct / Plan-and-Solve / Reflection` 在统一图式运行时内按场景启用
- 建立工具结果进入记忆层的正式边界和治理规则
- 保持可回退、可观测、可验收

执行范式约定：

- `ReAct`：默认工具调用范式，适用于日常对话、JD 分析、简历改写建议等单轮或短链路任务
- `Plan-and-Solve`：复杂任务模式，适用于多步骤求职任务拆解、阶段性任务推进、跨工具链路执行
- `Reflection`：高风险输出审查模式，适用于会影响用户决策、简历内容、长期记忆写入的高风险产出
- `Interrupt`：人工审核与恢复执行机制，适用于需要用户确认后才能继续、且任务可能跨轮或跨天推进的场景

当前执行切分：

- `M5.0`：前置冻结与兼容基线
- `M5.1`：LangGraph 底座与统一图状态
- `M5.2`：ReAct 默认工具调用范式接入
- `M5.3`：标准原生工具调用闭环
- `M5.4`：Plan-and-Solve 复杂任务模式
- `M5.5`：Reflection 高风险输出审查模式
- `M5.6`：Interrupt、人工审核与恢复执行
- `M5.7`：工具结果与用户长期记忆边界治理
- `M5.8`：可观测性、workflow 可视化与排查能力
- `M5.9`：测试、灰度、回退与收尾

#### M5.0：前置冻结与兼容基线

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 冻结 `M3/M4` 已稳定链路，新增 `langgraph_runtime` 功能开关，默认关闭
- 明确 `LangGraph` 只负责编排、checkpoint、interrupt、resume，不直接替代现有 `SessionService / ToolService / MemoryService / LLMService` 的能力层职责
- 梳理现有工具资产，确认首批纳入图式运行时的工具
- 首批仅纳入 `analyze_jd` 和 `resume_tailor`
- 保留当前 `M3` 工具链路作为回退路径，直到 `M5` 整体验收通过

验收要求：

- 功能开关可切换
- 新旧工具链路可并存
- 当前聊天链路不回归

#### M5.1：LangGraph 底座与统一图状态

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 新增图式运行时目录，例如 `backend/app/graphs/`
- 设计统一图状态 `GraphState`，至少覆盖：`user_id / session_id / turn_id / messages / short_term_memory / long_term_memory / tool_candidates / tool_results / execution_mode / approval_state / checkpoints / trace_id`
- 接入 `LangGraph` checkpointer，为中断恢复、人工审核、跨轮推进打基础
- 定义节点类型边界：`planner_node / react_reason_node / tool_select_node / tool_execute_node / reflect_node / respond_node / memory_gate_node / interrupt_node`
- 保持现有服务层为节点可复用能力提供方，而不是在图里重复实现业务逻辑

验收要求：

- 图状态可完成一次空跑或最小聊天链路
- checkpointer 可正常保存与恢复基础状态
- 现有服务层可被图节点复用

#### M5.2：ReAct 默认工具调用范式接入

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 以 `ReAct` 作为默认执行模式接入 `LangGraph`
- 对普通聊天、JD 分析、简历改写建议类任务，默认走 `reason -> decide_tool -> execute -> observe -> respond`
- 模型在图中原生决定是否调用工具、调用哪个工具、传什么参数
- 保留规则兜底入口，但降级为 fallback，而不是主通路
- 先支持单轮内有限步数的 `ReAct` 循环

验收要求：

- `analyze_jd` 能由模型在 `ReAct` 链路中原生触发
- 不再依赖当前手工 JD 识别作为唯一主入口
- `ReAct` 模式下无工具回复也可稳定结束

#### M5.3：标准原生工具调用闭环

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 实现标准闭环：用户消息 -> 模型返回 tool call -> 后端执行工具 -> 工具结果回填模型 -> 模型生成最终回答
- 统一工具注册结构：`name / description / input_schema / output_schema / execute / selection_mode / memory_policy / risk_level`
- 新增统一执行上下文，例如 `user_id / session_id / trace_id / turn_id / auth_context`
- 工具执行返回结构统一为：`status / normalized_output / raw_output / error / duration_ms`
- 引入 `tool_call_id`、`step_index`、`tool_result_message`
- 工具结果不直接拼接最终回答，必须先回填模型

验收要求：

- JD 输入能完整走完标准单步工具闭环
- `analyze_jd` 与 `resume_tailor` 均通过统一注册中心执行
- 工具结果回填后二次回复可稳定生成

#### M5.4：Plan-and-Solve 复杂任务模式

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 在图式运行时中加入 `Plan-and-Solve` 模式，用于复杂求职任务
- 先让模型生成结构化计划，再按步骤执行工具或子任务
- 适用于“完整投递准备”“多岗位比较”“阶段性求职推进”这类多步问题
- 支持计划步骤状态流转，例如 `planned / running / blocked / completed`
- 增加最大步骤限制、重复步骤检测和失败中止规则

验收要求：

- 至少跑通一个 2 步以上的复杂任务案例
- 计划生成、步骤执行、步骤收束链路可稳定运行
- 多步调用不会进入无限循环

#### M5.5：Reflection 高风险输出审查模式

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 为高风险产出增加 `Reflection` 审查节点
- 高风险场景包括：会影响简历内容、用户求职决策、长期记忆写入的输出
- 在主回复生成后追加审查步骤，检查事实依据、推断过度、表达风险、记忆写入风险
- 对审查失败的结果支持重写、降级或要求人工确认
- 为不同工具和输出类型补充 `risk_level` 与审查触发规则

验收要求：

- 高风险输出可触发 `Reflection` 审查
- 审查失败时不会直接把未经审查结果返回给用户
- 普通低风险聊天不会被无谓放大成本

#### M5.6：Interrupt、人工审核与恢复执行

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 在 `LangGraph` 中接入 `Interrupt` 机制
- 对需要用户确认才能继续的步骤，允许在图节点中断并等待用户输入
- 支持人工审核后恢复执行，而不是从头重跑整条链路
- 支持参数缺失转为追问节点，而不是盲执行
- 为高风险工具或高风险动作预留 `confirm_required` 能力
- 为长任务保留跨轮、跨天恢复入口

验收要求：

- 缺参追问可以中断并在补充参数后恢复
- 人工确认后可从 checkpoint 继续执行
- 长任务恢复时不会丢失关键上下文状态

#### M5.7：工具结果与用户长期记忆边界治理

- 状态：`未开始`
- 验收：`未开始`

目标：

- 明确标准工具调用完成后，哪些工具结果只能用于当前轮对话，哪些工具结果允许进入长期记忆候选流程
- 防止工具输出直接污染 `user_memory`，避免把外部任务信息、短期上下文或模型推断错误写成用户长期画像
- 建立“默认拒绝、白名单放行、候选池确认”的长期记忆治理规则，为后续多工具链路提供稳定边界

核心原则：

- 默认情况下，工具结果不得直接写入用户长期记忆 `user_memory`
- 工具结果只能先作为当前轮上下文使用，供回复生成和短期会话理解消费
- 只有满足白名单、稳定性、置信度和冲突检查的工具事实，才允许进入 `user_memory_candidates`
- 工具来源事实默认进入候选池，不允许自动直写 `user_memory`
- 用户长期记忆的主写入来源仍以 `user` 和 `manual` 为主，`tool` 来源仅作为受限补充来源

本阶段要完成的能力：

- 为工具结果新增记忆治理元数据：
- `memory_policy`
- `memory_scope`
- `memory_fact_whitelist`
- `memory_confidence`
- `memory_source_trace`
- 在工具注册中心中定义每个工具的记忆策略：
- `no_memory`
- `session_only`
- `candidate_only`
- 为工具输出增加“事实归一化层”，把原始工具结果转换成可判定的候选事实结构
- 在长期记忆同步前增加工具事实过滤层，阻止未授权工具或未授权字段进入 `user_memory`
- 将允许进入长期记忆流程的工具事实统一写入 `user_memory_candidates`，不直写 `user_memory`
- 为工具候选事实保留来源追踪信息，确保后续可审计、可解释、可回滚

允许进入候选池的事实类型白名单：

- `target_role`
- `primary_stack`
- `project_experience`
- `preference`
- `constraint`
- `job_search_stage`

明确禁止进入用户长期记忆的内容：

- 任意 JD 分析结果
- 任意岗位要求、岗位关键词、岗位能力缺口
- 任意公司、岗位、面试轮次的外部任务信息
- 当前轮临时目标、当前周计划、当前次投递准备重点
- 工具生成的推断性评价，例如“更适合某岗位”“可能缺乏某能力”
- 未经过字段白名单过滤的原始工具输出
- 低置信度或来源不可解释的工具抽取结果

首批工具策略要求：

- `analyze_jd`：`no_memory`
- 仅用于当前轮回复和任务上下文
- 不允许进入 `user_memory` 或 `user_memory_candidates`
- `resume_tailor`：`no_memory`
- 仅用于当前轮改写建议
- 不允许进入 `user_memory` 或 `user_memory_candidates`
- 未来若新增 `resume_parse`、`profile_extract` 一类工具：
- 默认 `candidate_only`
- 仅白名单字段允许进入候选池
- 不允许自动直写长期记忆

进入候选池的判定策略：

- 工具本身必须声明允许产生长期事实，且策略为 `candidate_only`
- 事实字段必须命中长期事实白名单
- 事实内容必须描述“用户自身稳定属性”，而不是外部任务或短期上下文
- 事实置信度必须达到设定阈值，例如 `>= 0.85`
- 如果与现有 `user_memory` 冲突，必须进入候选池，不允许覆盖
- 即使不冲突，也仍然进入候选池，由用户确认后再写入长期记忆
- 候选事实必须附带来源信息：
- `source_type = tool`
- `source_tool = resume_parse`
- `source_trace_id`
- `reason`

数据与模型层改造要求：

- 扩展工具执行结果结构，支持记忆治理元数据
- 扩展候选记忆结构，支持工具来源标识
- 为工具候选事实保留来源工具名、来源回合、来源日志 id
- 在记忆同步服务中新增工具事实过滤与归一化模块
- 保持现有 `user` / `manual` 长期记忆写入链路不受影响

验收标准：

- `analyze_jd` 的输出不会进入 `user_memory`
- `analyze_jd` 的输出不会进入 `user_memory_candidates`
- `resume_tailor` 的输出不会进入 `user_memory`
- 允许产出长期事实的白名单工具，其结果只能进入候选池，不能直写长期记忆
- 工具候选事实能正确保留来源工具、来源链路和置信度信息
- 与现有长期记忆冲突的工具事实不会直接覆盖旧值
- 历史基于 `user/manual` 的长期记忆链路不回归
- 工具记忆边界相关测试通过
- 集成检查通过
- `smoke test` 通过

本阶段验收命令：

- `backend/scripts/integration_check.py`
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -q`

#### M5.8：可观测性、workflow 可视化与排查能力

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 扩展 `tool_execution_logs`，增加 `tool_call_id / step_index / model_decision / raw_arguments / normalized_arguments / duration_ms / fallback_reason / graph_node / execution_mode`
- 增加图执行轨迹视图或调试接口
- 区分 `ReAct / Plan-and-Solve / Reflection / Interrupt` 四类执行模式
- 提供 workflow 可视化基础数据，让开发和用户都能看出流程当前走到哪一步
- 保证排查时能看出为什么选了这个工具、为什么失败、为什么中断、为什么结束循环

验收要求：

- 一次多步调用能完整还原执行轨迹
- 一次中断恢复链路能完整追踪
- 排查信息足够支持问题定位

#### M5.9：测试、灰度、回退与收尾

- 状态：`未开始`
- 验收：`未开始`

计划内容：

- 单测覆盖图状态流转、工具注册、参数校验、失败降级、循环终止、记忆边界
- 集成测试覆盖单工具链路、多工具链路、缺参追问、人工审核恢复、失败回退
- 前端联调验证真实对话路径，而不只是脚本调用
- 先通过开关灰度启用 `M5`，稳定后再考虑替换 `M3` 为默认链路
- 若 `LangGraph` 链路不稳定，可快速回退到 `M3` 或纯聊天链路

本阶段验收要求：

- `backend/scripts/integration_check.py`
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -q`

## 4. 每阶段必做验收

每完成一个阶段，都要至少执行：

- `backend/scripts/integration_check.py`
- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_smoke.py -q`

若新增了新的核心链路，必须同步补测试，而不是只复用旧测试。

## 5. 工程化执行规范

### 5.1 代码更新与托管规则

- 从 `M4.5` 起，每次有效代码更新都必须进入 GitHub 托管
- 不再允许“本地改完但不入库长期停留”的开发方式
- 每次代码更新必须遵循以下顺序：
- 本地完成开发
- 执行本地验收
- 提交到 Git 分支
- 推送 GitHub
- 等待 GitHub CI 通过
- CI 通过后再合并到 `main`
- 若本地验收未通过，不允许推送用于合并的正式代码
- 若 GitHub CI 未通过，不允许合并到 `main`

### 5.2 版本回滚规则

- 每个已验收阶段必须创建里程碑 Tag
- 后续若新增功能导致大面积错误，可回滚到最近一个稳定 Tag
- 回滚基线以“最后一个通过完整验收并进入主干的版本”为准
- `main` 分支只保留通过 CI 的可追踪版本

### 5.3 CI 准入规范

- `CI` 是主干合并门禁
- 任何未通过 `CI` 的代码不得进入 `main`
- 当前阶段 `CI` 必须通过的项目：
- `repo-hygiene-check`
- `backend-test`
- `integration-check`
- `frontend-build`
- `M4.6` 完成后新增：
- `db-migration-check`
- `CI` 通过标准：
- 所有必跑 Job 全部绿色
- 不允许关键测试 `skip`
- 不允许前端 build 失败
- 不允许核心链路测试缺失
- 只要任一 Job 失败，CI 即判定失败

### 5.4 CD 准入规范

- `CD` 是生产发布门禁
- `CD` 不等于“CI 通过就自动上线”
- 当前阶段只定义 `CD` 规则，不启用生产自动部署
- 未来 `CD` 的前置条件：
- 对应提交的 `CI` 全绿
- 数据库迁移脚本已评审通过
- 有发布说明
- 有回滚方案
- 生产环境变量齐全
- 镜像或发布产物构建成功
- 未来 `CD` 的通过标准：
- 部署前检查通过
- 数据库迁移成功
- 服务启动成功
- 健康检查通过
- 发布后 smoke test 通过
- 无阻断级错误
- 任一项失败即中止发布或触发回滚

### 5.5 CI/CD 规则演进机制

- 后续每新增一个核心功能，都必须同步补齐：
- 开发计划中的验收项
- `CI` 中的专项检查或测试
- `CD` 中的发布后回归项
- 固定基线长期保留：
- 后端测试
- 集成检查
- 前端 build
- 数据库迁移检查
- 仓库卫生检查
- 专项门禁按功能扩展：
- 改认证，补认证专项测试
- 改记忆，补记忆专项测试
- 改工具调用，补工具链路专项测试
- 改 LangGraph/interrupt/checkpoint，补图运行时专项测试
- 原则上不允许“只加功能，不加验收门禁”

## 6. 下一步

下一步严格进入 `M4.5`：

- 仓库清理与 GitHub 托管准备
- 首次推送到 `https://github.com/JulyHan001/-agent`
- GitHub Actions CI 基线接入
- 版本回滚与阶段 Tag 机制落地

`M4.5` 完成后严格进入 `M4.6`：

- `SQLite` 升级为 `PostgreSQL`
- 数据迁移与回归验证
- CI 增加数据库迁移检查

`M4.6` 完成并验收通过后再进入 `M5`：

- 标准原生工具调用接入
- 多步工具编排
- 参数校验与缺参追问
- 工具结果与用户长期记忆边界治理
- 可观测性、灰度与收尾

`M5` 稳定后再进入 `M6`：

- Docker Compose 部署链路
- 域名、HTTPS、生产环境变量
- CD 自动化发布
