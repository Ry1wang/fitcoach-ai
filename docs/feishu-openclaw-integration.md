# FitCoach AI × 飞书集成配置指南

> 前置条件：Mac Mini 上 Docker Compose 全部服务正常运行

---

## 一、环境变量

文件：`.env`（参照 `.env.example`）

| 字段 | 说明 |
|------|------|
| `BOT_API_KEY` | 自定义随机字符串，OpenClaw 调用脚本时使用。运行 `openssl rand -hex 32` 生成 |
| `BOT_USER_ID` | 机器人账号的 UUID，注册账号后从返回值中获取（见第四步） |

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
"agents": {
  "defaults": {
    "model": {
      "primary": "zai/glm-4.7"
    },
    "workspace": "/Users/xw_uu/.openclaw/workspace"
  }
}
```

### 3.2 创建 SKILL.md（路由规则）

OpenClaw 通过 workspace 下的 SKILL.md 文件向 agent 注入工具说明。

```bash
mkdir -p ~/.openclaw/workspace/skills/fitcoach
```

新建文件 `~/.openclaw/workspace/skills/fitcoach/SKILL.md`：

```markdown
---
name: ask_fitcoach
description: 查询健身、力量训练、运动康复、营养饮食相关知识，答案来自专业健身书籍的 RAG 检索
metadata.openclaw.requires.bins: ["python3"]
---

适用问题类型：健身训练、动作要领、训练计划、运动康复、伤病预防、营养饮食。

当检测到此类问题时，执行以下命令（将问题原文放入 heredoc）：

```bash
BOT_API_KEY=<BOT_API_KEY的值> python3 /Users/xw_uu/fitcoach-ai/mcp/ask-fitcoach.py <<'EOF'
用户问题原文
EOF
```

将命令输出原文返回给用户，不要加工或改写。
其他问题（天气、编程、日常对话等）直接回答，不使用此工具。
```

> 将 `<BOT_API_KEY的值>` 替换为 `.env` 中 `BOT_API_KEY` 的实际值；路径改为项目在 Mac Mini 上的实际路径。

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

# 上传 PDF
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/book.pdf"
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
