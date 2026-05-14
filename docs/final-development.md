# 求职面试 Agent 最终版开发文档

## 1. 文档定位

本文档描述的是产品最终目标形态，而不是当前仓库已经完成的 `V1` 形态。

当前状态：

- 当前代码已具备 `V1` 最小聊天闭环
- 本文档定义 `V2 ~ V5` 的完整目标架构
- 后续开发应以本文档为主，以 `docs/v1-development.md` 为历史基线

本文档面向：

- 开发实现
- 架构决策
- 联调测试
- 阶段验收
- 后续部署与交付

---

## 2. 产品目标

最终版求职面试 Agent 需要从“能聊天”升级为“能分析、能调用工具、能执行多步骤任务、能检索知识、能持续沉淀数据”的完整系统。

最终系统需要覆盖以下能力：

1. 稳定的求职助手角色与输出格式
2. 简历解析、JD 分析、岗位匹配等工具调用能力
3. 可观测、可控制的多步骤工作流能力
4. 基于知识库的 RAG 检索增强能力
5. 基于生产级向量数据库的检索与数据沉淀能力

最终结果不是一个“泛聊天机器人”，而是一个围绕求职场景的任务型 Agent 系统。

---

## 3. 业务范围

### 3.1 核心业务能力

- 求职规划建议
- 岗位要求拆解
- 简历内容优化
- 项目经历重写
- 面试准备计划生成
- 技术栈学习路线建议
- 简历与 JD 匹配分析
- 面试问答模拟
- 基于知识库的答案增强

### 3.2 核心用户任务

- 输入目标岗位，生成准备路径
- 上传简历，分析问题与优化建议
- 输入 JD，抽取要求并生成匹配结论
- 根据简历和 JD 自动给出差距分析
- 针对某一岗位生成面试题清单与答题框架
- 基于知识库回答求职问题
- 多轮追问并保持上下文

### 3.3 不在最终版首批范围内

- 社交关系或好友系统
- 企业端招聘后台
- 自动投递职位
- 视频面试实时语音能力
- 多租户企业权限体系

---

## 4. 版本演进原则

后续必须严格按以下顺序推进，不跳步：

1. 稳定提示词和输出格式
2. 加入工具调用
3. 加入多步骤工作流
4. 接入 RAG
5. 接入向量数据库

原因如下：

- 不先稳定输出，工具层会放大回答不稳定问题
- 不先有工具层，工作流只能编排空动作
- 不先有工作流，RAG 只能做简单检索，无法形成完整任务链
- 不先验证 RAG 价值，直接上向量数据库只会提前增加工程复杂度

---

## 5. 总体架构

### 5.1 架构目标

最终系统采用前后端分离架构，后端内部继续拆为五层：

- API 层
- 会话层
- Agent 编排层
- 工具与知识层
- 数据存储层

### 5.2 总体链路

```text
Frontend
  -> API Gateway / FastAPI
  -> Session & Context Manager
  -> Agent Orchestrator
      -> Prompt Builder
      -> Tool Registry / Tool Executor
      -> Workflow Engine
      -> RAG Service
  -> LLM Service
  -> Storage Layer
      -> PostgreSQL
      -> Object Storage
      -> Vector Store
```

### 5.3 最终技术选型

#### 前端

- `Next.js`
- `TypeScript`
- 基于当前聊天页逐步升级

#### 后端

- `FastAPI`
- `Python`
- `openai` SDK

#### 结构化存储

- `PostgreSQL`

#### 文件存储

- 本地开发：磁盘目录
- 生产环境：对象存储，如 `MinIO` 或云对象存储

#### 向量存储

- 最终推荐：`PostgreSQL + pgvector`

选择原因：

- 可与业务数据共库存储
- 便于简历、JD、知识文档、会话片段统一管理
- 运维复杂度低于独立向量数据库集群

#### 本地原型检索

- 在进入正式向量库前，允许使用本地内存索引或轻量索引文件做 `RAG` 原型验证

---

## 6. 最终系统模块划分

### 6.1 前端模块

#### `Chat UI`

职责：

- 多轮对话展示
- 结构化消息展示
- 工具执行状态展示
- 引用资料展示
- 错误提示展示

#### `Resume Upload UI`

职责：

- 上传简历文件
- 展示解析结果
- 触发简历分析任务

#### `JD Input UI`

职责：

- 粘贴 JD 文本
- 展示提取结果
- 触发 JD 分析和匹配分析

#### `Task Result UI`

职责：

- 展示结构化任务结果
- 显示差距分析、准备计划、面试题清单等

### 6.2 后端模块

#### `API Routes`

建议新增：

- `POST /api/chat`
- `POST /api/upload/resume`
- `POST /api/analyze/resume`
- `POST /api/analyze/jd`
- `POST /api/analyze/match`
- `POST /api/knowledge/index`
- `GET /api/session/{id}`

#### `Session Manager`

职责：

- 会话 ID 管理
- 对话历史持久化
- 上下文裁剪
- 结构化中间结果挂载

#### `Prompt Builder`

职责：

- 管理 system prompt
- 管理角色边界
- 统一输出格式约束
- 根据任务类型注入不同提示模板

#### `Tool Registry`

职责：

- 注册工具定义
- 暴露工具 schema
- 管理工具可见性
- 校验工具输入输出

#### `Tool Executor`

职责：

- 执行工具调用
- 记录调用结果
- 标准化错误信息

#### `Workflow Engine`

职责：

- 决定当前任务是否进入多步骤执行
- 定义步骤状态机
- 控制最大步数、失败回退、终止条件

#### `RAG Service`

职责：

- 文档切分
- 向量化
- 检索
- 重排序
- 引用组装

#### `Storage Layer`

职责：

- 业务数据持久化
- 文档索引存储
- 向量检索

---

## 7. 最终目录结构建议

```text
求职agent/
  docs/
    v1-development.md
    final-development.md
    development-plan.md
  frontend/
    src/
      app/
        page.tsx
        resume/
        jd/
      components/
        chat/
        resume/
        jd/
        task/
      lib/
        api.ts
        types.ts
  backend/
    app/
      main.py
      api/
        routes/
          chat.py
          resume.py
          jd.py
          knowledge.py
          session.py
      core/
        config.py
        prompts/
          base.py
          chat.py
          resume.py
          jd.py
          workflow.py
      models/
        chat.py
        resume.py
        jd.py
        workflow.py
        knowledge.py
      services/
        llm_service.py
        session_service.py
        prompt_service.py
        workflow_service.py
        rag_service.py
        embedding_service.py
      tools/
        base.py
        registry.py
        resume_parser.py
        jd_parser.py
        match_analyzer.py
        interview_planner.py
      repositories/
        session_repository.py
        resume_repository.py
        knowledge_repository.py
        vector_repository.py
      workers/
        indexing_worker.py
      db/
        models.py
        migrations/
```

---

## 8. 功能设计

### 8.1 能力一：稳定提示词与输出格式

目标：

- 让模型输出更稳定
- 让结果更可消费
- 为后续工具调用和工作流提供稳定协议

实现要求：

- 拆分基础 system prompt 与任务 prompt
- 区分聊天模式、简历模式、JD 模式、匹配模式
- 强制结构化输出模板
- 对关键信息缺失时要求模型先提问澄清

建议输出格式：

- 结论
- 原因
- 建议步骤
- 风险或不足
- 下一步行动

对于工具场景，建议额外返回：

- 是否需要工具
- 需要哪些输入
- 引用来源

### 8.2 能力二：工具调用

目标：

- 把“只会说”升级为“能做分析”

首批工具建议：

1. `parse_resume`
   - 输入：简历原文或解析后的文本
   - 输出：候选人基础信息、技能、项目、经历摘要

2. `analyze_jd`
   - 输入：JD 文本
   - 输出：岗位职责、技能要求、优先项、关键词

3. `match_resume_jd`
   - 输入：简历结构化结果 + JD 结构化结果
   - 输出：匹配度、差距、建议补强项

4. `generate_interview_plan`
   - 输入：目标岗位、技术栈、时间窗口
   - 输出：分阶段准备计划

5. `generate_mock_questions`
   - 输入：目标岗位、技术栈、项目经历
   - 输出：模拟面试题与答题点

工具调用规范：

- 所有工具都必须定义输入 schema
- 所有工具都必须定义标准输出 schema
- 工具错误必须结构化返回
- 工具调用过程必须可记录、可回放

### 8.3 能力三：多步骤工作流

目标：

- 将复杂任务拆成多个明确步骤执行

适合进入工作流的任务：

- 简历与 JD 匹配分析
- 生成个性化面试准备路线
- 从上传简历到输出优化建议

建议工作流形态：

#### 工作流 A：简历分析

1. 获取简历文本
2. 解析简历结构
3. 识别关键问题
4. 生成优化建议
5. 输出结构化结果

#### 工作流 B：JD 匹配分析

1. 获取 JD 文本
2. 解析 JD 结构
3. 获取简历结构
4. 计算匹配与差距
5. 生成行动建议

#### 工作流 C：面试准备计划

1. 确认目标岗位
2. 补齐基础信息
3. 必要时检索知识库
4. 生成阶段计划
5. 输出执行清单

工作流控制要求：

- 每个步骤有明确输入和输出
- 每个步骤有可追踪状态
- 有最大步数限制
- 单步失败可中断并给出原因
- 可在日志中回放完整步骤链路

### 8.4 能力四：RAG

目标：

- 让回答不只依赖通用模型能力，而是结合项目知识库

知识源建议：

- 求职方法论文档
- 面试题库
- 岗位知识卡片
- 技术学习路线文档
- 简历优化规范

RAG 基本流程：

1. 导入知识文档
2. 文档清洗
3. 文本切分
4. 向量化
5. 检索召回
6. 重排序
7. 组装上下文
8. 生成带引用回答

RAG 结果要求：

- 回答中区分“模型推断”和“知识引用”
- 返回引用片段或引用来源
- 不允许把未经检索支持的内容伪装成知识库事实

### 8.5 能力五：向量数据库

目标：

- 将 RAG 从原型能力升级为可持续维护的工程能力

最终要求：

- 支持知识文档持久化
- 支持增量索引
- 支持按文档、标签、来源过滤
- 支持会话级记忆片段检索
- 支持简历和 JD 嵌入结果管理

建议存储对象：

- 知识文档 chunk
- 简历解析 chunk
- JD 解析 chunk
- 历史高价值问答片段

推荐方案：

- 结构化数据：`PostgreSQL`
- 向量数据：`pgvector`

---

## 9. Prompt 体系设计

### 9.1 Prompt 分层

最终系统不再只有一个 `SYSTEM_PROMPT`，而要拆成以下层次：

1. 基础角色 Prompt
2. 任务类型 Prompt
3. 输出格式 Prompt
4. 工具使用规则 Prompt
5. RAG 引用规则 Prompt

### 9.2 基础角色 Prompt 要求

- 限定在求职与面试场景
- 强调结构化表达
- 禁止编造经历和事实
- 对信息不足先提问而不是直接瞎答

### 9.3 输出格式约束

建议最终前端消费的默认结构：

```json
{
  "summary": "一句话结论",
  "analysis": ["分析点1", "分析点2"],
  "actions": ["行动1", "行动2"],
  "risks": ["风险1"],
  "need_more_info": false
}
```

说明：

- 早期可以先让模型输出 Markdown 结构
- 在工具化阶段后，再逐步切到更强的结构化 JSON 约束

### 9.4 工具调用 Prompt 规则

- 何时必须用工具
- 何时禁止用工具
- 工具返回不确定时如何处理
- 工具失败时如何降级回答

### 9.5 RAG Prompt 规则

- 必须优先引用检索结果
- 对知识库未覆盖内容要显式说明
- 区分“检索证据”和“模型补充建议”

---

## 10. 数据模型设计

### 10.1 会话

```text
Session
- id
- user_id(optional)
- title
- created_at
- updated_at
```

### 10.2 消息

```text
Message
- id
- session_id
- role
- content
- message_type
- tool_calls(json)
- citations(json)
- created_at
```

### 10.3 简历

```text
Resume
- id
- session_id(optional)
- filename
- raw_text
- parsed_json
- created_at
```

### 10.4 JD

```text
JobDescription
- id
- session_id(optional)
- raw_text
- parsed_json
- created_at
```

### 10.5 知识文档

```text
KnowledgeDocument
- id
- source_name
- source_type
- content
- metadata(json)
- created_at
```

### 10.6 向量块

```text
VectorChunk
- id
- document_type
- document_id
- chunk_text
- embedding
- metadata(json)
- created_at
```

---

## 11. API 设计

### 11.1 聊天接口

`POST /api/chat`

用途：

- 普通对话
- 工具触发
- 工作流入口

建议扩展请求体：

```json
{
  "session_id": "optional-session-id",
  "messages": [
    {
      "role": "user",
      "content": "帮我分析一下这个 JD"
    }
  ],
  "context": {
    "resume_id": "optional",
    "jd_id": "optional"
  }
}
```

### 11.2 简历上传接口

`POST /api/upload/resume`

用途：

- 上传 PDF / DOCX / TXT 简历
- 返回 `resume_id`

### 11.3 简历分析接口

`POST /api/analyze/resume`

输入：

- `resume_id`

输出：

- 结构化简历结果
- 问题列表
- 优化建议

### 11.4 JD 分析接口

`POST /api/analyze/jd`

输入：

- `raw_text` 或 `jd_id`

输出：

- 结构化 JD 结果

### 11.5 匹配分析接口

`POST /api/analyze/match`

输入：

- `resume_id`
- `jd_id`

输出：

- 匹配度
- 差距项
- 优先补强项

### 11.6 知识索引接口

`POST /api/knowledge/index`

用途：

- 上传知识源
- 触发切分与索引

### 11.7 会话查询接口

`GET /api/session/{id}`

用途：

- 拉取会话历史
- 恢复上下文

---

## 12. 工具层设计

### 12.1 工具抽象接口

每个工具都应统一包含：

- `name`
- `description`
- `input_schema`
- `execute()`
- `output_schema`

### 12.2 工具返回规范

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

失败示例：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INVALID_INPUT",
    "message": "resume text is empty"
  }
}
```

### 12.3 工具注册中心

注册中心必须支持：

- 按名称查找工具
- 返回可用工具清单
- 区分实验工具与正式工具
- 根据任务类型控制工具暴露范围

---

## 13. 工作流设计

### 13.1 工作流模式

最终建议采用“显式状态机 + 受控步骤执行”，而不是完全放权给模型自由 Agent。

理由：

- 更容易调试
- 更容易验收
- 更适合业务型系统
- 可以限制成本和风险

### 13.2 步骤状态

- `pending`
- `running`
- `completed`
- `failed`
- `skipped`

### 13.3 工作流上下文

工作流上下文建议包括：

- 当前任务类型
- 已完成步骤
- 当前工具结果
- 当前检索结果
- 最终汇总草稿

### 13.4 终止条件

- 达到最终结果
- 连续失败达到上限
- 缺失关键输入无法继续
- 超过最大步数

---

## 14. RAG 设计

### 14.1 文档处理流程

1. 文档导入
2. 编码与格式清洗
3. 段落标准化
4. chunk 切分
5. embedding 生成
6. 索引写入

### 14.2 检索流程

1. 根据用户问题生成检索 query
2. 向量召回 top-k
3. 必要时关键词召回
4. 重排序
5. 返回上下文片段
6. 组装引用

### 14.3 RAG 输出约束

- 回答中展示引用来源
- 对来源冲突做提示
- 对没有检索命中的问题允许回退到通用回答

### 14.4 RAG 评估指标

- 命中率
- 引用相关性
- 答案可用性
- 幻觉率

---

## 15. 向量数据库设计

### 15.1 为什么最终接入向量数据库

`RAG` 原型阶段可以先验证“有没有价值”，但最终交付必须具备：

- 持久化
- 可维护
- 可增量更新
- 可过滤
- 可调试

### 15.2 `pgvector` 使用建议

表设计建议：

- `knowledge_chunks`
- `resume_chunks`
- `jd_chunks`
- `memory_chunks`

元数据建议：

- `source_type`
- `source_id`
- `tags`
- `chunk_index`
- `version`

### 15.3 索引策略

- 先保证正确性
- 再做召回数量与性能优化
- 对热点知识源支持增量更新

---

## 16. 上下文与记忆设计

### 16.1 短期上下文

来源：

- 当前会话最近若干轮消息

用途：

- 支撑连续对话与追问

### 16.2 长期记忆

来源：

- 高价值总结
- 用户简历解析结果
- 已分析 JD 结果
- 历史匹配分析结论

用途：

- 减少重复提问
- 在跨轮任务中复用关键结论

### 16.3 上下文策略

建议组合方式：

- 最近消息窗口
- 任务关键结构化结果
- 必要时检索记忆片段
- 必要时检索知识库

---

## 17. 非功能要求

### 17.1 稳定性

- 接口出现异常时有可读错误信息
- 工具失败可降级
- 工作流超步数自动终止

### 17.2 可观测性

- 记录请求日志
- 记录模型调用日志
- 记录工具调用日志
- 记录工作流步骤日志
- 记录检索日志

### 17.3 性能

- 普通聊天响应尽量控制在可接受时延内
- 工具分析任务允许更长耗时，但要可追踪

### 17.4 安全

- 不记录明文密钥
- 文件上传做类型校验
- 对用户输入做长度限制
- 对工具输入做 schema 校验

---

## 18. 测试策略

### 18.1 单元测试

- prompt builder
- tool executor
- workflow state
- rag chunking
- repository

### 18.2 接口测试

- chat
- resume upload
- jd analyze
- match analyze
- knowledge index

### 18.3 集成测试

- 从上传简历到生成优化建议
- 从输入 JD 到输出匹配分析
- 从知识索引到检索回答

### 18.4 回归测试

- 输出格式是否稳定
- 工具是否按预期触发
- 工作流是否按步骤执行
- RAG 是否返回引用

---

## 19. 部署建议

### 19.1 开发环境

- 前端本地启动
- 后端本地启动
- PostgreSQL 本地实例或容器

### 19.2 测试环境

- 独立测试模型配置
- 独立数据库
- 独立知识库索引

### 19.3 生产环境

- 前端静态部署或 Node 服务
- 后端 FastAPI 服务
- PostgreSQL + pgvector
- 对象存储
- 日志与监控

---

## 20. 最终验收标准

最终版交付至少满足以下条件：

1. 普通求职对话稳定
2. 输出格式基本一致
3. 简历分析工具可用
4. JD 分析工具可用
5. 简历与 JD 匹配分析可用
6. 多步骤工作流可观测
7. RAG 可返回引用内容
8. 向量数据库索引可持久化
9. 会话可恢复
10. 核心接口有自动化测试

---

## 21. 与当前仓库的关系

当前仓库已完成：

- `V1` 聊天页
- `V1` 后端接口
- `V1` 基础 prompt
- `V1` 多轮上下文透传

当前仓库尚未完成：

- 结构化输出约束
- 工具注册与执行框架
- 显式工作流引擎
- RAG 服务
- 向量数据库
- 会话持久化
- 文件上传与解析能力

因此后续开发应采用“保留现有 V1 基线，在其上逐层增强”的方式，而不是推倒重写。

---

## 22. 结论

最终版系统的核心不是功能堆叠，而是形成一条稳定的任务执行链：

`用户问题 -> 上下文理解 -> 必要时工具调用 -> 必要时工作流执行 -> 必要时知识检索 -> 结构化输出`

只要这条链路稳定，后续扩展新工具、新知识源和新任务类型都会变得可控。
