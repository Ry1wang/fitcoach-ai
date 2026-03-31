# FitCoach AI × 飞书集成配置指南

> 前置条件：Mac Mini 上 Docker Compose 全部服务正常运行

---

## 一、环境变量

文件：`.env`（参照 `.env.example`）

| 字段 | 说明 |
|------|------|
| `BOT_API_KEY` | 自定义随机字符串，OpenClaw 调用时使用。运行 `openssl rand -hex 32` 生成 |
| `BOT_USER_ID` | 机器人账号的 UUID，注册账号后从返回值中获取（见下方操作步骤） |

修改后重启服务：
```bash
docker compose down && docker compose up -d
```

---

## 二、飞书开放平台

地址：[open.feishu.cn/app](https://open.feishu.cn/app)

1. **创建企业自建应用**，填写名称（如 `FitCoach AI`）、描述、图标

2. **凭证与基础信息** → 记录 `App ID`（格式 `cli_xxx`）和 `App Secret`

3. **权限管理 → 批量导入**，粘贴：
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

4. **应用能力 → 机器人** → 开启，填写机器人名称

5. **事件订阅** → 选择**使用长连接接收事件**（无需公网 URL）→ 添加事件 `im.message.receive_v1`

6. **版本管理与发布** → 创建版本并发布（选择全员可见）

---

## 三、OpenClaw 配置

文件：`~/.openclaw/openclaw.json`（Mac Mini 上，不存在则新建）

```json5
{
  channels: {
    feishu: {
      enabled: true,
      dmPolicy: "allow",
      accounts: {
        main: {
          appId: "cli_xxxxxxxxxx",   // 飞书 App ID
          appSecret: "xxxxxxxxxx",   // 飞书 App Secret
          name: "FitCoach AI",
        },
      },
    },
  },
  models: {
    mode: "merge",
    providers: {
      fitcoach: {
        baseUrl: "http://localhost:8000/v1",
        apiKey: "<BOT_API_KEY 的值>",
        api: "openai-completions",
        models: [
          {
            id: "fitcoach-rag",
            name: "FitCoach RAG",
            contextWindow: 8000,
            maxTokens: 2000,
          },
        ],
      },
    },
  },
  agents: {
    list: [
      {
        id: "main",
        default: true,
        name: "FitCoach AI",
        model: "fitcoach/fitcoach-rag",
      },
    ],
  },
}
```

---

## 四、操作步骤（一次性）

**1. 注册机器人账号**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "feishu-bot", "password": "<强密码>"}'
```
将返回值中的 `id` 字段填入 `.env` 的 `BOT_USER_ID`，然后重启服务。

**2. 用机器人账号上传健身 PDF**
```bash
# 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=feishu-bot&password=<强密码>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 上传 PDF
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/book.pdf"
```
等文档状态变为 `ready` 再继续。

**3. 安装并启动 OpenClaw**
```bash
# 安装（需要 Node.js 22.14+）
npx openclaw onboard --install-daemon

# 编辑 ~/.openclaw/openclaw.json（按上方配置填写）

# 启动
openclaw gateway
```

---

## 五、验证

```bash
# 测试接口连通
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <BOT_API_KEY>" \
  -d '{"model":"fitcoach-rag","messages":[{"role":"user","content":"俯卧撑怎么做？"}]}'
```

在飞书中向机器人发送私信，确认收到回复。

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `401 Unauthorized` | `BOT_API_KEY` 不匹配 | 确认 `.env` 与 `openclaw.json` 中的值一致 |
| `500 Bot user not found` | `BOT_USER_ID` 错误 | 重新执行步骤1，确认 UUID 格式正确 |
| `500 BOT_USER_ID not configured` | `.env` 变量未生效 | 重启 Docker Compose |
| 飞书消息无响应 | OpenClaw 未启动或凭证错误 | 运行 `openclaw gateway status` |
| 回复内容空白 | PDF 未上传到机器人账号 | 用机器人账号重新上传文档 |
