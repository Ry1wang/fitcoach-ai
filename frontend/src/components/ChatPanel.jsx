import { useEffect, useRef, useState } from "react";
import useChat from "../hooks/useChat";
import MessageBubble from "./MessageBubble";
import StreamingText from "./StreamingText";
import ConversationList from "./ConversationList";

export default function ChatPanel() {
  const {
    messages,
    conversationId,
    streaming,
    routingInfo,
    error,
    sendMessage,
    stopStreaming,
    loadConversation,
    newConversation,
    clearError,
  } = useChat();

  const [input, setInput] = useState("");
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, routingInfo]);

  // Focus input after streaming ends
  useEffect(() => {
    if (!streaming) inputRef.current?.focus();
  }, [streaming]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    sendMessage(text);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Conversation sidebar */}
      <ConversationList
        activeId={conversationId}
        onSelect={loadConversation}
        onNew={newConversation}
      />

      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {/* Message list */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-sm text-gray-400">开始新对话，向你的健身知识助手提问吧</p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
            </div>
          )}

          {/* Streaming indicator */}
          <StreamingText routingInfo={routingInfo} />

          <div ref={bottomRef} />
        </div>

        {/* Error bar */}
        {error && (
          <div className="flex items-center justify-between bg-red-50 px-4 py-2">
            <span className="text-xs text-red-600">{error}</span>
            <button
              onClick={clearError}
              className="text-xs text-red-400 hover:text-red-600"
            >
              &times;
            </button>
          </div>
        )}

        {/* Input area */}
        <div className="border-t bg-white px-4 py-3">
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              maxLength={2000}
              placeholder="输入你的问题..."
              disabled={streaming}
              className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
            />
            {streaming ? (
              <button
                onClick={stopStreaming}
                className="shrink-0 rounded-lg bg-red-500 px-4 py-2 text-sm text-white hover:bg-red-600"
              >
                停止
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                发送
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
