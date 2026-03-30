import { useCallback, useRef, useState } from "react";
import client from "../api/client";

const AGENT_LABELS = {
  training: "训练",
  rehab: "康复",
  nutrition: "营养",
};

export default function useChat() {
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [routingInfo, setRoutingInfo] = useState(null); // { agent, refined_query, cached }
  const [error, setError] = useState("");
  const abortRef = useRef(null);

  // ── Load conversation history ───────────────────────────────────────────
  const loadConversation = useCallback(async (convId) => {
    setError("");
    setRoutingInfo(null);
    try {
      const { data } = await client.get(`/conversations/${convId}`);
      setConversationId(convId);
      setMessages(
        data.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          agent_used: m.agent_used,
          sources: m.sources,
          latency_ms: m.latency_ms,
        })),
      );
    } catch {
      setError("加载对话失败");
    }
  }, []);

  // ── Start new conversation ──────────────────────────────────────────────
  const newConversation = useCallback(() => {
    setConversationId(null);
    setMessages([]);
    setRoutingInfo(null);
    setError("");
  }, []);

  // ── Send message with SSE streaming ─────────────────────────────────────
  const sendMessage = useCallback(
    async (text) => {
      if (streaming) return;
      setError("");
      setStreaming(true);
      setRoutingInfo(null);

      // Optimistic user message
      const userMsg = { id: crypto.randomUUID(), role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);

      // Placeholder for assistant response
      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: assistantId, role: "assistant", content: "", sources: null, agent_used: null },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const token = localStorage.getItem("token");
        const res = await fetch("/api/v1/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            conversation_id: conversationId,
            message: text,
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          const body = await res.json().catch(() => null);
          if (res.status === 429) {
            setError(body?.detail?.message || "请求过于频繁，请稍后再试");
          } else if (res.status === 401) {
            localStorage.removeItem("token");
            window.location.href = "/login";
            return;
          } else {
            setError(body?.detail?.message || "请求失败");
          }
          // Remove placeholder
          setMessages((prev) => prev.filter((m) => m.id !== assistantId));
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop(); // keep incomplete part

          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith("data: ")) continue;
            const event = JSON.parse(line.slice(6));

            switch (event.type) {
              case "routing":
                setRoutingInfo({
                  agent: event.agent,
                  label: AGENT_LABELS[event.agent] || event.agent,
                  refined_query: event.refined_query,
                  cached: event.cached || false,
                });
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, agent_used: event.agent } : m,
                  ),
                );
                break;

              case "sources":
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, sources: event.chunks } : m,
                  ),
                );
                break;

              case "token":
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content + event.content }
                      : m,
                  ),
                );
                break;

              case "done":
                if (event.conversation_id) {
                  setConversationId(event.conversation_id);
                }
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, latency_ms: event.latency_ms }
                      : m,
                  ),
                );
                break;

              case "error":
                setError(event.message || "服务异常");
                break;
            }
          }
        }

        // Process any remaining buffered data after stream ends
        if (buffer.trim().startsWith("data: ")) {
          try {
            const event = JSON.parse(buffer.trim().slice(6));
            if (event.type === "done" && event.conversation_id) {
              setConversationId(event.conversation_id);
            }
          } catch {
            // Ignore incomplete final chunk
          }
        }
      } catch (err) {
        if (err.name !== "AbortError") {
          setError("网络连接失败");
          setMessages((prev) => prev.filter((m) => m.id !== assistantId));
        }
      } finally {
        setStreaming(false);
        setRoutingInfo(null);
        abortRef.current = null;
      }
    },
    [conversationId, streaming],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    messages,
    conversationId,
    streaming,
    routingInfo,
    error,
    sendMessage,
    stopStreaming,
    loadConversation,
    newConversation,
    clearError: () => setError(""),
  };
}
