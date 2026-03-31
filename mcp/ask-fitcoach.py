#!/usr/bin/env python3
"""Read question from stdin, call FitCoach RAG API, print response to stdout."""
import json
import os
import sys
import urllib.request
import urllib.error

question = sys.stdin.read().strip()
if not question:
    print("错误：未收到问题", file=sys.stderr)
    sys.exit(1)

api_key = os.environ.get("BOT_API_KEY", "")
url = os.environ.get("FITCOACH_URL", "http://localhost:8000/v1/chat/completions")

payload = json.dumps({
    "model": "fitcoach-rag",
    "messages": [{"role": "user", "content": question}],
}).encode()

req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    },
)

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    print(data["choices"][0]["message"]["content"])
except urllib.error.HTTPError as e:
    print(f"FitCoach API 错误 {e.code}: {e.read().decode()}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"调用失败: {e}", file=sys.stderr)
    sys.exit(1)
