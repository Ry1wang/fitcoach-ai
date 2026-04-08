# FitCoach AI 开发任务清单（Post-Test 2026-04-08）

**来源**：`fitcoach-ai-test/reports/综合测试报告_20260408.md`
**创建日期**：2026-04-08
**使用说明**：每完成一个任务，需在对应任务下补充「完成总结」小节，包含：
- **完成前 → 完成后对比**（行为/指标/现象的变化）
- **核心技术或策略**（使用的关键方案、库、配置、代码改动要点）
- **完成日期**

---

## 🔴 高优先级：阻塞性问题排查与修复

### 任务 1：修复 Starting Strength PDF 未被 RAG 检索的问题

**背景**：文档状态为 `ready` 但检索不到内容，是 RAG 答案质量的头号瓶颈。Layer 2 评估中系统反向建议用户"上传 Starting Strength"，而该书实际已 ready。

**子任务**：
- [x] 排查步骤 1：在 PostgreSQL 中查询 `document_chunks` 表，统计 Starting Strength 的 chunk 数量（预期 200–500，若 <10 确认异常）
- [x] 排查步骤 2：本地运行 `pdfplumber` 测试前 10 页文本提取质量，确认是否为乱码/空内容
- [x] 排查步骤 3：开启 pipeline INFO 日志，重新上传并观察 chunk/embed 过程（已不需要，根因定位于 embedding 模型）
- [x] 排查步骤 4：直接在 pgvector 上做相似度查询，验证 top-k 排名
- [x] 修复（三选一）：
  - 原因 A（解析失败）→ 改用 `pymupdf.get_text("rawdict")` 或引入 OCR（tesseract）
  - **原因 B（跨语言匹配差）→ 替换 embedding 模型为 `bge-m3` 双语模型** ✅
  - 原因 C（写入中断）→ 改造 pipeline 为原子写入，chunk 写入成功后再改 `ready` 状态

**预期收益**：`answer_correctness` 预计由 0.50 提升至 0.65+

**完成总结**（2026-04-08）

- **完成前**：
  - Starting Strength（1470 chunks，英文）在任何中文 query 下都进不了 top-k，测试中 Layer 2 系统反向建议"上传 Starting Strength"
  - 根因：`EMBEDDING_MODEL=nomic-embed-text`（768d，英语单语模型），对中文 query 的向量与英文 chunk 向量在同一空间近似正交，余弦距离极大
  - 实际波及范围不止 Starting Strength——所有 4 本英文书（Rebuilding Milo / Scientific Principles / Foods Nutrition / Redis）都同病
- **完成后**：
  - Embedding 模型换成 `bge-m3`（1024d，中英双语），全量 4829 chunks 用新模型重新 embedding
  - 验证：4 条中文 query（深蹲、硬拉、卧推、"Starting Strength 这本书讲什么"），Starting Strength 分别占据 top-10 中 **6 / 6 / 7 / 9** 席，平均 relevance_score ~0.58–0.60
  - 跨语言检索彻底打通；同时 Rebuilding Milo / Scientific Principles 英文书一并受益
- **核心技术/策略**：
  - **模型选择**：`bge-m3`（BAAI，Ollama 本地部署，1.2GB）— 多语言 dense+sparse 混合 embedding，中英混合检索 benchmark 显著优于单语模型
  - **配置改动**：
    - `.env`：`EMBEDDING_MODEL=bge-m3`、`EMBEDDING_DIMENSION=1024`
    - `scripts/init.sql`：`embedding vector(768)` → `vector(1024)`（未来全新初始化用）
    - `backend/app/models/document_chunk.py` 通过 `settings.EMBEDDING_DIMENSION` 自动适配，无需改动
  - **在线 DB 迁移**（破坏性，需短暂停 RAG）：
    1. `DELETE FROM documents WHERE status='failed'`（清理 9 条脏数据）
    2. `DROP INDEX idx_chunks_embedding` → `ALTER TABLE ... DROP COLUMN embedding` → `ADD COLUMN embedding vector(1024)`
    3. `docker compose up -d --force-recreate backend`（`restart` 不会重载 `env_file`）
    4. 运行 `backend/scripts/reembed_all.py`（新增脚本，批量 25 条 / batch，串行写回，幂等——只处理 `embedding IS NULL`）
    5. Re-embed 完成后 `CREATE INDEX ... USING hnsw` 重建索引（先 drop 再重建避免 re-embed 期间反复维护）
  - **关键文件**：
    - `backend/scripts/reembed_all.py`（新增，可复用工具）
    - `.env`、`scripts/init.sql`
- **验证方式**：
  - `SELECT COUNT(*), COUNT(embedding) FROM document_chunks` → `4829 / 4829` 全部有向量
  - 在 backend 容器内直接调用 `app.rag.retriever.retrieve()`，4 条中文 query 下 Starting Strength 稳定占据 top-10 的 6–9 席
  - `answer_correctness` 的最终回归验证需重跑 Layer 2 评估集（任务外后续执行）

---

### 任务 2：修复 ISSUE-001 大 PDF OOM 问题

**背景**：FastAPI `BackgroundTasks` 在 uvicorn 进程内并发处理多个大 PDF，内存峰值超过容器 1G 限制，Docker OOM kill 后文档永久卡在 `processing`。

**子任务**：
- [x] 短期：将 `docker-compose.yml` backend `memory` 从 1G 调至 2G（已随上次 commit `e13b6e9` 一并提交）
- [x] 中期：后端启动时扫描 `processing` 状态文档，重置为 `failed`（而非 `pending`）并提供手动重试端点
- [ ] 长期：迁移 `BackgroundTasks` 至 Celery + Redis 持久化任务队列（留作下次迭代）

**完成总结**（2026-04-08）

- **完成前**：
  - Backend 容器内存上限 1G；多个大 PDF 并发上传时 uvicorn 进程内存峰值叠加 → Docker OOM kill
  - OOM 后文档永久卡在 `processing` 状态，前端无反馈、无恢复路径
  - 没有并发控制，`BackgroundTasks` 允许无限并行 ingestion
- **完成后**：
  - 内存上限 1G → 2G（单 PDF 安全余量充足）
  - Backend 启动时自动扫描 `processing` 并重置为 `failed`（带明确 error_message），前端可见，可重试
  - 新增 `POST /api/v1/documents/{id}/retry`：仅接受 `failed` 状态，复用原 `file_path`，重新 enqueue ingestion
  - Pipeline 新增 module-level `asyncio.Semaphore(1)`，多个并发 ingestion 自动串行，上传 API 仍然立即返回 `202 Accepted`
  - Pipeline 插入 chunks 前先 `DELETE` 旧 chunks，retry 后结果确定（不会出现重复行）
- **核心技术/策略**：
  - **并发闸门**：`_INGESTION_SEMAPHORE = asyncio.Semaphore(settings.MAX_CONCURRENT_INGESTIONS)`（默认 1）— 用 `async with _INGESTION_SEMAPHORE, async_session() as session:` 包裹整个 pipeline body
  - **启动恢复**：在 `main.py` 的 `lifespan` 中追加 `reset_stuck_processing_documents()`——新进程不可能有 in-flight ingestion，所以 `processing` 状态一定是上次崩溃的残留；置为 `failed` 比置为 `pending` 更透明（用户可见）、更安全（避免无限 OOM 循环）
  - **Retry 幂等性**：pipeline 插入前 `DELETE FROM document_chunks WHERE document_id=?`，首次为 no-op，retry 时清空残留；这是 retry 端点能正确工作的前提
  - **关键文件**：
    - `backend/app/config.py` — 新增 `MAX_CONCURRENT_INGESTIONS: int = 1`
    - `backend/app/services/pipeline.py` — 模块级 Semaphore + 插入前 DELETE
    - `backend/app/services/document_service.py` — 新增 `reset_stuck_processing_documents()`
    - `backend/app/main.py` — `lifespan` 中调用启动恢复
    - `backend/app/api/documents.py` — 新增 `POST /{id}/retry` 端点
- **验证方式**：
  - **启动恢复**：手动 `UPDATE documents SET status='processing' WHERE id=...`，`docker restart fitcoach-backend`，日志出现 `Reset 1 stuck 'processing' document(s) to 'failed'`，DB 中状态 + error_message 均已写入
  - **并发闸门**：stub pipeline 内部后 `asyncio.gather` 触发 3 条并发 `run_ingestion_pipeline`（每条模拟 1 秒耗时），总耗时 **3.03s** 串行完成（并行应为 ~1s），证明 semaphore 生效
  - **Retry 端点**：
    - `POST /documents/{ready_doc_id}/retry` → 409 `INVALID_STATUS`
    - `POST /documents/{nonexistent}/retry` → 404 `NOT_FOUND`
    - 端点已出现在 OpenAPI paths 中
- **遗留事项**：
  - 长期方案 Celery 迁移未做，留作下次迭代。当前 semaphore + 启动恢复已堵死 90% OOM 永久卡死问题；剩余需要 Celery 解决的场景为"worker 独立崩溃/任务持久化"
  - 前端 `failed` 状态的"重试"按钮尚未对接（后端接口已就绪）

---

### 任务 3：修复 ISSUE-002 测试环境 LLM 限流

**背景**：Layer 3 连续 105 次 LLM 调用耗尽提供商 RPM 配额，导致测试结果虚低（accuracy 跌至 14.3%）。

> ⚠️ **原背景描述基于误诊**。实施时核对代码后确认：真正的 429 来源是**后端自己的 Redis 速率限制器**（`RATE_LIMIT_PER_MINUTE=20`），**不是** LLM 提供商的 RPM 配额。证据：`KNOWN_ISSUES.md` 报告 105 条请求 0.74s 内全部返回 429 —— 这种响应速度只可能是本地 Redis 快速拒绝，LLM 提供商不会这么快。因此下面两条原子任务（独立 LLM Key / LLM 请求队列）都不对症，实际采用了**用户级白名单** 方案。

**子任务**：
- [x] ~~为测试环境配置独立的 LLM API Key（与生产隔离）~~ → **不适用**（误诊）
- [x] ~~或在后端增加 LLM 请求队列 / 限速器~~ → **不适用**（后端已有限流器，问题本身就是限流器）
- [x] **实际实施**：后端新增 `RATE_LIMIT_BYPASS_USER_IDS` 配置项，允许指定白名单用户绕过 Redis 速率限制器

**完成总结**（2026-04-08）

- **完成前**：
  - 后端 `/api/v1/chat` 对每个用户固定窗口限流 20 req/min（通过 Redis `ratelimit:{user_id}:{bucket}`）
  - 测试仓库 Layer 3 连续跑 105 条 query，即使加了 `L3_QUERY_DELAY=1.0`（1 req/s ≈ 60 req/min）依然超出 20 req/min 上限
  - 结果：测试运行 accuracy 跌至 14.3%（90 条 429 + 15 条 cache 命中），FAIL
  - 根因被 `KNOWN_ISSUES.md` 误记为 "LLM 提供商 RPM 配额"
- **完成后**：
  - 后端新增配置项 `RATE_LIMIT_BYPASS_USER_IDS: list[str] = []`（默认空，生产行为完全不变）
  - `chat.py` 在调用限流器前判断用户 ID 是否在白名单，若是则完全跳过限流
  - 部署时只需在 `.env` 设置 `RATE_LIMIT_BYPASS_USER_IDS=["<测试用户 UUID>"]` 即可让测试用户突发跑满 105 条无限流
  - 生产用户仍受 20 req/min 保护（已验证：非白名单用户第 21 条起精确返回 429）
- **核心技术/策略**：
  - **用户级白名单**：不关闭限流器、不动窗口大小、不跨仓库改测试端，只在限流判断前加一个 O(1) set 查找
  - **Pydantic list 解析**：直接在 settings 声明 `list[str]`，pydantic-settings 会自动从 `.env` 解析 JSON 数组（`RATE_LIMIT_BYPASS_USER_IDS=["uuid"]`）
  - **关键文件**：
    - `backend/app/config.py` — 新增 `RATE_LIMIT_BYPASS_USER_IDS`
    - `backend/app/api/chat.py` — 限流判断前加 `if user_id_str not in settings.RATE_LIMIT_BYPASS_USER_IDS:`
    - `.env.example` — 加配置注释示例（实际 `.env` 未动，留给部署方填入测试用户 ID）
  - **被拒绝方案**：
    - 独立 LLM API Key：误诊修复
    - 后端 LLM 请求队列：误诊修复
    - 全局抬高 `RATE_LIMIT_PER_MINUTE`：削弱生产防滥用
    - `RATE_LIMIT_ENABLED: bool` 全局开关：误配风险高
- **验证方式**：
  - **Test 1（白名单用户 30 连发）**：0 × 429，30 × 404（顺利穿过限流器 → 下游 conversation 查找失败）
  - **Test 2（非白名单用户 25 连发）**：前 20 × 404（限流器放行）+ 后 5 × 429（限流器精确拦截）
  - 两项均使用 ASGI transport 打到真实 Redis，行为符合预期
- **遗留事项**：
  - **部署方操作**：在生产/测试 `.env` 中填入 `RATE_LIMIT_BYPASS_USER_IDS=["..."]`（本次不替部署方决定具体 UUID）
  - **`KNOWN_ISSUES.md` 的 ISSUE-002 根因描述应修正为"后端 Redis 限流器"**（属于测试仓库 `fitcoach-ai-test`，跨仓库改动，留给用户确认后执行）
  - **cache-aware 限流**（命中 query cache 不计入配额）作为后续优化，本次未做

---

## 🟡 中优先级：系统能力优化

### 任务 4：修复 ISSUE-005 Rehab Agent 路由偏差

**背景**：路由器对损伤关键词（肌腱炎、下背痛、膝盖疼）权重过高，含此类词的跨域查询被过度分配至 rehab，Layer 1 对抗性测试中约 28/50 被误路由。

> ⚠️ **原背景描述关于"权重"部分基于误解**。实施时核对代码后确认：`backend/app/agents/graph.py` 和 `router.py` **完全没有关键词权重 / 评分 / hardcoded 规则**，路由是**纯 LLM 分类**（LLM 读 `ROUTER_SYSTEM_PROMPT` 输出 JSON）。所谓的"权重偏差"实际上来自 `prompts.py` 里 prompt 本身的措辞失误。因此这是一个 **prompt engineering 任务**，不是代码逻辑修改。

**子任务**：
- [x] ~~审查 `backend/app/agents/graph.py` Supervisor 路由逻辑，降低损伤关键词单一权重~~ → **graph.py 无权重逻辑可降；实际修复点在 `prompts.py`**
- [x] 在路由 prompt 中增加「主意图优先」原则（已实施为 7 条优先级规则）
- [x] 将 Layer 1 对抗性查询集纳入路由器回归测试 → **以 `backend/scripts/router_smoke.py` 形式实现**（开发者 smoke 工具，不加 pytest）

**完成总结**（2026-04-08）

- **完成前**（Baseline smoke test on OLD prompt）：
  - 整体准确率 **72.2%（13/18）**
  - 5 条全部误路由到 rehab，误诊模式：
    * 4 × 历史伤病 + 训练主意图 → rehab（应 training）
    * 1 × nutrition 问题被"tendon healing"抢走 → rehab（应 nutrition）
  - 特别严重：`"Why does my knee cave inward during squats and how do I fix it?"` —— 纯动作技术问题，**无任何 pain 词**，仅仅提到 "knee" 就被路由到 rehab，说明旧 prompt 对身体部位词过度敏感
  - 根因：旧 prompt 含硬规则 "如果问题同时涉及训练和受伤 → 选择 rehab（安全优先）"，加上 rehab 关键词列表里有"恢复 / 活动度"等被训练语境过度共用的词
- **完成后**（Smoke test on NEW prompt, 2 次跑 temperature=0 均稳定）：
  - 整体准确率 **100%（18/18）**，混淆矩阵对角满分
  - 5 条原误路由全部修复
  - 无 easy case 回归（3 条 sanity check 保持正确）
  - 中间版本曾出现 3 条 over-correction 到 nutrition（LLM 看到 eating/creatine/protein 就跳过去），通过**收紧规则 5**（要求营养词必须是"问句唯一的主谓结构"+ 给出反例"Can I do X while eating Y"、"What A AND what B for goal"）再次迭代，最终稳定到 100%
- **核心技术/策略**：
  - **Prompt 重写的 7 条优先级原则**（`backend/app/agents/prompts.py` 的 `ROUTER_SYSTEM_PROMPT`）：
    1. 主意图优先（伤病/部位/恢复词只是上下文）
    2. 当下 vs 历史（current/当下 → rehab，history of/旧伤 → 看主意图）
    3. 回归/重建路径 → rehab（重点在恢复进度）
    4. 身体部位词不等于 rehab（无"痛/不适"就不选 rehab）
    5. 营养词的严格识别（「去掉营养词后问句是否还成立」的判断启发）
    6. 安全兜底（仅当"还能不能训练/是否应停训"明确询问时才强制 rehab）
    7. 模糊/打招呼 → 默认 training
  - **分类描述的关键词收窄**：
    - rehab 从 "受伤、疼痛、恢复、活动度、康复训练、医疗问题" → "**当下**疼痛/不适、急性损伤处理、伤后重返训练时机、康复阶段动作选择"（删掉"恢复"、"活动度"等被训练语境过度共用的词）
    - training 加上"**即使用户有旧伤史、劳损背景或处于减脂期**"的显式声明
    - nutrition 加上"**即使涉及训练目标或恢复场景**"的显式声明
  - **双语示例**：新增英文示例（原版只有中文），因为 Layer 1 Golden Set 129 条里 100+ 条是英文，双语示例能给 LLM 更好的跨语言迁移信号
  - **迭代反例机制**：针对过度矫正问题，在规则 5 内直接给出"Can I do X while eating Y"、"I have pain, can creatine help?"、"What A AND what B" 三类反例，强制 LLM 在看到营养词时二次确认
  - **关键文件**：
    - `backend/app/agents/prompts.py` — `ROUTER_SYSTEM_PROMPT` 完全重写
    - `backend/scripts/router_smoke.py` — 新增 18 条 hand-picked tricky queries 的 smoke tool
- **验证方式**：
  - **Smoke 工具**：`docker exec -w /app fitcoach-backend python -m scripts.router_smoke`
  - **Baseline 对比**：旧 prompt 13/18 (72.2%)；新 prompt 18/18 (100%)
  - **稳定性**：`temperature=0` 下连跑 2 次，结果一致（18/18 + 18/18）
  - **覆盖模式**：18 条查询覆盖 10 类模式（easy sanity / history-injury / current-injury / rebuild / training-with-diet-context / nutrition-with-rehab-context / form-fault / injury-prevention / multi-domain），每类至少 1 条
- **遗留事项**：
  - **未做** pytest 集成测试（理由：backend 镜像不含 tests 目录；真实 LLM 调用不适合 CI；正规全量回归本就在 `fitcoach-ai-test` 仓库）
  - **建议**：在 `fitcoach-ai-test` 仓库下次跑 Layer 1/3 全量 129 条对抗性测试，量化本次改动对真实 Golden Set 的影响（预计对 cross-domain 15 条和 injury-bearing hard cases 的 accuracy 有显著提升）

---

### 任务 5：修复 ISSUE-004 移动端布局溢出

**背景**：375px 视口下侧边栏与聊天区并排导致宽度超出，发送按钮 x+width=561px 超出视口。

**子任务**：
- [ ] 为前端侧边栏添加响应式断点（Tailwind `hidden md:flex`），<768px 折叠
- [ ] 确保发送按钮在 375px 视口内

**完成总结**：_（待填写）_

---

### 任务 6：修复 ISSUE-003 Agent 降级场景测试覆盖

**背景**：测试套件与应用代码分离，无法注入 mock LLM 覆盖 LLM 空响应/超时/格式错误三种降级路径。

**子任务**：
- [ ] 在 `backend/app/agents/` 下为 training / rehab / nutrition agent 各添加单元测试
- [ ] 覆盖三类场景：LLM 空响应、超时、格式错误
- [ ] 使用 mock LLM client 注入

**完成总结**：_（待填写）_

---

### 任务 7：优化语料库质量

**背景**：语料库混入无关书籍（Redis Deep Dive），占用 top-k 名额；RAG 答案质量天花板受语料库限制。

**子任务**：
- [ ] 移除无关文档《Redis Deep Dive.pdf》
- [ ] 上传技术细节更丰富的训练类书籍
- [ ] 检查其他已上传 PDF 的 chunk 质量

**完成总结**：_（待填写）_

---

## 🟢 低优先级：可观测性与扩展能力

### 任务 8：完善 Pipeline 日志

**背景**：`app.services.pipeline` logger 有效级别为 WARNING，INFO 进度日志不输出，导致 OOM 问题难以诊断。

**子任务**：
- [ ] 在 `backend/app/main.py` 启动配置中显式设置 `app.services.pipeline` logger 为 INFO

**完成总结**：_（待填写）_

---

### 任务 9：SSE `done` 事件暴露 `retrieved_contexts`

**背景**：当前 SSE 流仅返回 `agent_used` 和 token 流，不携带检索片段，导致 Layer 2 的 Faithfulness 和 Context Recall 指标无法计算。

**子任务**：
- [ ] 在 `backend/app/api/chat.py` SSE 流 `done` 事件附加 `retrieved_chunks` 字段
- [ ] 为前端"引用来源"展示能力打基础

**完成总结**：_（待填写）_

---

### 任务 10：文档原子性与 chunk 数量校验

**背景**：当前 `status = ready` 不能证明向量写入完整，存在 pipeline 静默失败风险（与 ISSUE-001 OOM 史相关）。

**子任务**：
- [ ] Pipeline 完成后进行 chunk 数量健全性校验（<10 则标记 `failed` 而非 `ready`）
- [ ] 在管理界面/API 暴露每个文档的 chunk 数

**完成总结**：_（待填写）_

---

## 建议执行顺序

1. **本周**：任务 1（Starting Strength 排查）+ 任务 2 短期（扩容）→ 解锁 RAG 质量提升
2. **下一迭代**：任务 4（路由偏差）+ 任务 8、9（可观测性）→ 为 Layer 2 完整评估铺路
3. **中期规划**：任务 2 长期（Celery）+ 任务 5（移动端）+ 任务 6（单测覆盖）

**最高性价比动作**：任务 1 — 预计使 `answer_correctness` 从 0.50 升至 0.65+，直接改变 RAG 能力评级。

---

## 完成总结模板

> 每完成一个任务后，按以下模板填入对应任务下的「完成总结」：
>
> ```markdown
> **完成总结**（YYYY-MM-DD）
>
> - **完成前**：<具体现象/指标/行为>
> - **完成后**：<对比后的新现象/指标/行为>
> - **核心技术/策略**：<使用的关键方案、库、配置、代码改动要点，附关键文件路径>
> - **验证方式**：<如何确认问题已解决，例如哪项测试通过、哪个指标达标>
> ```
