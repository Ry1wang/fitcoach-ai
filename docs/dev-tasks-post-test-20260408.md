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
- [ ] 短期：将 `docker-compose.yml` backend `memory` 从 1G 调至 2G
- [ ] 中期：后端启动时扫描 `processing` 状态文档，重置为 `pending` 并重新触发
- [ ] 长期：迁移 `BackgroundTasks` 至 Celery + Redis 持久化任务队列

**完成总结**：_（待填写）_

---

### 任务 3：修复 ISSUE-002 测试环境 LLM 限流

**背景**：Layer 3 连续 105 次 LLM 调用耗尽提供商 RPM 配额，导致测试结果虚低（accuracy 跌至 14.3%）。

**子任务**：
- [ ] 为测试环境配置独立的 LLM API Key（与生产隔离）
- [ ] 或在后端增加 LLM 请求队列 / 限速器

**完成总结**：_（待填写）_

---

## 🟡 中优先级：系统能力优化

### 任务 4：修复 ISSUE-005 Rehab Agent 路由偏差

**背景**：路由器对损伤关键词（肌腱炎、下背痛、膝盖疼）权重过高，含此类词的跨域查询被过度分配至 rehab，Layer 1 对抗性测试中约 28/50 被误路由。

**子任务**：
- [ ] 审查 `backend/app/agents/graph.py` Supervisor 路由逻辑，降低损伤关键词单一权重
- [ ] 在路由 prompt 中增加"主意图优先"原则
- [ ] 将 Layer 1 对抗性查询集纳入路由器回归测试

**完成总结**：_（待填写）_

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
