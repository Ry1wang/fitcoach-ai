# FitCoach AI × 飞书集成配置指南

> 前置条件：Mac Mini 上 Docker Compose 全部服务正常运行

---

## 一、环境变量

文件：`.env`（参照 `.env.example`）

| 字段 | 说明 |
|------|------|
| `BOT_API_KEY` | 自定义随机字符串，OpenClaw 调用脚本时使用。运行 `openssl rand -hex 32` 生成 |
| `BOT_USER_ID` | 机器人账号的 UUID，注册账号后从返回值中获取（见第四步） |
| `EMBEDDING_API_KEY` | Ollama 不校验 key，填 `ollama` 即可 |
| `EMBEDDING_BASE_URL` | Docker 容器内访问宿主机 Ollama：`http://host.docker.internal:11434/v1` |
| `EMBEDDING_MODEL` | `nomic-embed-text` |
| `EMBEDDING_DIMENSION` | `768`（nomic-embed-text 输出维度） |

Mac Mini 上 `.env` 相关配置示例：

```env
# Embedding（Ollama nomic-embed-text，运行在宿主机）
EMBEDDING_API_KEY=ollama
EMBEDDING_BASE_URL=http://host.docker.internal:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# Feishu/OpenClaw bot integration
BOT_API_KEY=<openssl rand -hex 32 生成的值>
BOT_USER_ID=<注册机器人账号后从返回值中获取的 UUID>
```

> **注意**：Docker 容器内不能用 `localhost` 访问宿主机服务，必须用 `host.docker.internal`。

修改后重启服务：
```bash
docker compose down && docker compose up -d
```

---

## 二、飞书开放平台

地址：[open.feishu.cn/app](https://open.feishu.cn/app)

> 如果已有飞书自建应用，跳过第 1 步，直接从第 2 步核对配置。

1. （仅首次）**创建企业自建应用**，填写名称（如 `FitCoach AI`）、描述、图标

2. **凭证与基础信息** → 记录 `App ID`（格式 `cli_xxx`）和 `App Secret`，填入 `openclaw.json`

3. **权限管理** → 确认以下权限已开启（可通过批量导入补充缺少的）：
```json
{
  "scopes": {
    "tenant": [
      "im:message",
      "im:message.p2p_msg:readonly",
      "im:message:send_as_bot",
      "im:message:readonly",
      "im:chat.members:bot_access"
    ],
    "user": []
  }
}
```

4. **应用能力 → 机器人** → 确认已开启

5. **事件订阅** → 确认已选**使用长连接接收事件**，且已添加事件 `im.message.receive_v1`

6. 如有改动，**版本管理与发布** → 重新发布版本使配置生效

---

## 三、OpenClaw 配置

### 3.1 `openclaw.json`

文件：`~/.openclaw/openclaw.json`

在现有配置中确认以下内容正确，**不要新增 `mcp` 或 `systemPrompt` 字段**（该版本不支持，会导致 Config invalid）：

```json
"channels": {
  "feishu": {
    "enabled": true,
    "dmPolicy": "allow",
    "accounts": {
      "main": {
        "appId": "cli_xxxxxxxxxx",
        "appSecret": "xxxxxxxxxx",
        "name": "FitCoach AI"
      }
    }
  }
},
"tools": {
  "profile": "coding",
  "allow": ["exec", "shell", "bash"]
},
"agents": {
  "defaults": {
    "model": {
      "primary": "zai/glm-4.7"
    },
    "workspace": "/Users/xw_uu/.openclaw/workspace"
  }
}
```

> **`tools` 字段是让 GLM 执行 SKILL.md bash 命令的关键配置**。不加此字段时，OpenClaw agent 无法调用 shell 工具，`ask-fitcoach.py` 不会被执行。

> ⚠️ **安全隐患**：参见"六、已知限制 → shell 工具权限风险"。

### 3.2 创建 SKILL.md（路由规则）

OpenClaw 通过 workspace 下的 SKILL.md 文件向 agent 注入工具说明。

```bash
mkdir -p ~/.openclaw/workspace/skills/fitcoach
```

运行以下命令创建 `~/.openclaw/workspace/skills/fitcoach/SKILL.md`（将路径和 BOT_API_KEY 替换为实际值）：

```bash
cat > ~/.openclaw/workspace/skills/fitcoach/SKILL.md << 'ENDOFFILE'
---
name: ask_fitcoach
description: 查询健身、力量训练、运动康复、营养饮食相关知识，答案来自专业健身书籍的 RAG 检索
metadata.openclaw.requires.bins: ["python3"]
---

## 强制规则

**只要用户问题涉及以下任何一类，必须执行下方 bash 命令，禁止自行回答：**
- 健身动作、训练技巧、动作要领
- 训练计划、力量训练、体能训练
- 运动康复、伤病预防、拉伸放松
- 营养饮食、蛋白质、增肌减脂

**执行方式**：

第一步：将用户问题中所有的单引号（`'`）替换为 `'\''`，得到转义后的问题文本。

第二步：执行以下命令（`<转义后的问题>` 替换为第一步结果）：

`printf '%s\n' '<转义后的问题>' | BOT_API_KEY=<BOT_API_KEY的值> python3 /path/to/fitcoach-ai/mcp/ask-fitcoach.py`

示例：用户问"it's heavy，怎么练？"→ 转义为 `it'\''s heavy，怎么练？`，命令为：

`printf '%s\n' 'it'\''s heavy，怎么练？' | BOT_API_KEY=<BOT_API_KEY的值> python3 /path/to/fitcoach-ai/mcp/ask-fitcoach.py`

**将命令的输出原文返回给用户，不做任何修改或补充。**

只有天气、编程、闲聊等与健身完全无关的问题才可以直接回答。
ENDOFFILE
```

> - 将 `<BOT_API_KEY的值>` 替换为 `.env` 中 `BOT_API_KEY` 的实际值
> - 将 `/path/to/fitcoach-ai` 替换为项目在 Mac Mini 上的实际路径（运行 `find ~ -name "ask-fitcoach.py"` 查找）
> - 修改后需重启 OpenClaw：`pkill openclaw-gateway && sleep 2 && openclaw gateway &`

---

## 四、操作步骤（一次性）

**1. 注册机器人账号**

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "feishu-bot", "email": "feishu-bot@fitcoachapp.com", "password": "<强密码>"}'
```

- `email` 字段必填，使用任意合法格式即可，无需真实存在
- 将返回值中的 `id` 字段填入 `.env` 的 `BOT_USER_ID`，然后重启服务

**2. 用机器人账号上传健身 PDF**

```bash
# 登录获取 token（username 字段填注册时的 email）
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=feishu-bot@fitcoachapp.com&password=<强密码>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 上传 PDF（必须指定 domain，否则 RAG 检索不到内容）
# domain 可选值：training（训练）、rehab（康复）、nutrition（营养）
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/book.pdf" \
  -F "domain=training"
```

> **重要**：必须指定 `-F "domain=training"`（或 `rehab`/`nutrition`）。不指定 domain 上传的文档，RAG 检索时会因 `content_domain` 为 null 而匹配不到任何内容，导致回复"没有上传任何健身书籍"。
>
> 如果同一本书同时覆盖训练和康复内容（如《囚徒健身》），可以上传两次，分别指定不同的 domain。

查询文档状态：
```bash
curl -s http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; docs=json.load(sys.stdin)['documents']; [print(d['status'], d['chunk_count'], d['filename']) for d in docs]"
```

等文档状态变为 `ready` 再继续。

**3. 安装依赖**

```bash
# 需要 Node.js 22.14+
cd /path/to/fitcoach-ai/mcp && npm install
```

**4. 启动 OpenClaw**

```bash
openclaw gateway
```

---

## 五、验证

> 以下命令在 Mac Mini 上直接执行（宿主机访问 Docker 服务）。容器内部请将端口 `8000` 替换为 nginx 实际映射端口。

```bash
# 测试 FitCoach 接口连通
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <BOT_API_KEY>" \
  -d '{"model":"fitcoach-rag","messages":[{"role":"user","content":"俯卧撑怎么做？"}]}'
```

在飞书中向机器人发送私信：
- 发送健身相关问题（如"深蹲怎么做"）→ 应收到来自 RAG 的专业回答
- 发送普通问题（如"今天天气怎样"）→ 应收到 GLM 直接回答

> **注意**：如果飞书健身问题的回答没有提到书名（如"根据《囚徒健身1》..."），说明 GLM 在用自身训练知识回答，并未调用 `ask-fitcoach.py`。参见下方"已知限制"章节。

---

### shell 工具权限风险

**背景**：`openclaw.json` 中配置 `"allow": ["exec", "shell", "bash"]` 是让 GLM 执行 SKILL.md bash 命令的必要条件，但同时引入了两类安全风险。

**风险一：权限过宽**

`exec/shell/bash` 允许 OpenClaw agent 在 Mac Mini 上执行任意 shell 命令，不限于 `ask-fitcoach.py`。若 GLM 被诱导生成其他命令（提示词注入攻击），攻击者可在宿主机上执行任意操作。

**风险二：命令注入（已缓解）**

早期 SKILL.md 使用 `echo "用户输入"` 双引号拼接，用户发送含 `"` 或 `$(...)` 的消息可突破引号边界。当前版本已改用 `printf '%s\n' '<单引号包裹>'`，并要求 GLM 将输入中的 `'` 转义为 `'\''`。

单引号内 shell 不展开任何字符（`$`、反引号、`\` 均为字面量），只有 `'` 本身需要转义处理。残余风险：若 GLM 未按指令转义单引号，含 `'` 的问题可能导致命令语法错误（命令失败，不执行额外命令）。

**当前缓解措施**

| 措施 | 说明 |
|------|------|
| `printf '%s\n'` 单引号包裹 | 防止 `$`、反引号、双引号等 shell 展开 |
| 飞书 `dmPolicy: allow` 仅限私信 | 减少公开群暴露面 |
| Mac Mini 为本地内网设备 | 攻击需先进入同一网络 |
| FitCoach API 只接受 `BOT_API_KEY` 认证 | 限制了 API 本身的访问 |

**残余风险及根本解决方案**（任选其一）

1. **使用方案 A**（参见上方）：OpenClaw 直接调用 FitCoach API 作为模型提供方，无需 `exec/shell/bash` 权限，彻底消除此风险
2. **限制飞书白名单**：在飞书开放平台将机器人可见范围限制为特定人员，降低恶意输入的可能性
3. **沙箱化**：将 OpenClaw 运行在 Docker 容器中，限制宿主机文件系统访问权限

---

### 书籍内容分布

不同书籍覆盖不同内容，上传时需按实际内容指定 `domain`：

| 书籍 | 推荐 domain | 说明 |
|------|------------|------|
| 《囚徒健身1》| `training` | 6大动作序列（俯卧撑、深蹲、引体向上等）、单臂引体（第10式）|
| 《囚徒健身2》| `training` | 握力、腰部训练等辅助动作 |
| 运动康复类书籍 | `rehab` | 伤病预防与康复 |
| 营养类书籍 | `nutrition` | 饮食与营养补剂 |

> 同一本书如果同时涵盖训练和康复内容，可上传两次分别指定不同 domain。

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `Config invalid: Unrecognized key "mcp"` | 该版本不支持 mcp 字段 | 删除 `openclaw.json` 中的 `mcp` 块 |
| `Config invalid: Unrecognized key "systemPrompt"` | 该版本不支持该字段 | 删除，改用 SKILL.md |
| `Field required: email` | 注册接口 email 为必填 | 补充 email 字段，使用合法格式如 `xxx@fitcoachapp.com` |
| `value is not a valid email address` | 使用了保留域名（如 `.local`） | 改用普通域名，如 `fitcoachapp.com` |
| `401 Unauthorized` | `BOT_API_KEY` 不匹配 | 确认 `.env` 与 SKILL.md 中的值一致 |
| `500 Bot user not found` | `BOT_USER_ID` 错误 | 重新执行步骤1，确认 UUID 格式正确 |
| `500 BOT_USER_ID not configured` | `.env` 变量未生效 | 重启 Docker Compose |
| 飞书消息无响应 | OpenClaw 未启动或凭证错误 | 运行 `openclaw gateway status` |
| `KeyError: 'access_token'` | 登录失败，响应无该字段 | 登录接口 `username` 字段必须填注册时的 **email**，不是用户名 |
| 回复内容空白 | PDF 未上传到机器人账号 | 用机器人账号重新上传文档 |
| 文档状态 `failed`，后端报 `Error code: 404` | `EMBEDDING_BASE_URL` 未配置或指向 `localhost`（容器内不可达） | 设置 `EMBEDDING_BASE_URL=http://host.docker.internal:11434/v1` 并重启 |
| 接口返回"没有上传任何健身书籍" | 上传 PDF 时未指定 `domain`，chunks 的 `content_domain` 为 null，无法被检索 | 重新上传并加上 `-F "domain=training"`（或 `rehab`/`nutrition`） |
| 重新上传并指定 domain 后仍返回空 | Redis 缓存了之前的空结果，cache hit 跳过了 RAG 检索 | 运行 `docker compose exec redis redis-cli FLUSHALL` 清空缓存后重试 |
| 飞书回答不包含书名，内容来自 GLM 训练知识 | GLM 忽略 SKILL.md 的 bash 执行指令，直接从自身知识回答 | 经过调试，确认不是 LLM 能力问题 |
| 询问单臂引体、高阶动作时返回无内容 | 该内容在《囚徒健身1》，未上传或上传时未指定 `domain=training` | 重新上传囚徒健身1并指定正确 domain，清空 Redis 缓存后重试 |
