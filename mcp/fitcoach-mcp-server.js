#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const FITCOACH_URL =
  process.env.FITCOACH_URL ?? "http://localhost:8000/v1/chat/completions";
const BOT_API_KEY = process.env.BOT_API_KEY ?? "";

const server = new McpServer({ name: "fitcoach", version: "1.0.0" });

server.tool(
  "ask_fitcoach",
  "查询健身、力量训练、运动康复、营养饮食相关知识，答案来自专业健身书籍的 RAG 检索",
  { question: z.string().describe("用户的健身相关问题，原文传入，不要改写") },
  async ({ question }) => {
    const response = await fetch(FITCOACH_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${BOT_API_KEY}`,
      },
      body: JSON.stringify({
        model: "fitcoach-rag",
        messages: [{ role: "user", content: question }],
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`FitCoach API ${response.status}: ${text}`);
    }

    const data = await response.json();
    const reply = data.choices?.[0]?.message?.content ?? "未获取到回复";
    return { content: [{ type: "text", text: reply }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
