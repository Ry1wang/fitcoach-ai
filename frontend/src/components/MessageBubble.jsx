import { useState } from "react";

const AGENT_LABELS = {
  training: "训练",
  rehab: "康复",
  nutrition: "营养",
};

function SourceCard({ source }) {
  return (
    <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs">
      <div className="flex items-center gap-2">
        {source.source_book && (
          <span className="font-medium text-gray-700">{source.source_book}</span>
        )}
        {source.chapter && (
          <span className="text-gray-500">{source.chapter}</span>
        )}
        {source.relevance_score != null && (
          <span className="ml-auto text-gray-400">
            相关度 {(source.relevance_score * 100).toFixed(0)}%
          </span>
        )}
      </div>
      {source.content_preview && (
        <p className="mt-1 text-gray-500">{source.content_preview}</p>
      )}
    </div>
  );
}

export default function MessageBubble({ message }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === "user";
  const sources = message.sources;
  const hasSources = sources && sources.length > 0;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-lg px-4 py-2.5 ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white text-gray-800 shadow-sm border border-gray-100"
        }`}
      >
        {/* Agent badge */}
        {!isUser && message.agent_used && (
          <span className="mb-1 inline-block rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">
            {AGENT_LABELS[message.agent_used] || message.agent_used}
          </span>
        )}

        {/* Message content */}
        <div className="whitespace-pre-wrap text-sm leading-relaxed">
          {message.content}
          {!isUser && !message.content && (
            <span className="inline-block h-4 w-1 animate-pulse bg-gray-400" />
          )}
        </div>

        {/* Latency */}
        {!isUser && message.latency_ms > 0 && (
          <p className="mt-1 text-right text-xs text-gray-400">
            {(message.latency_ms / 1000).toFixed(1)}s
          </p>
        )}

        {/* Source citations (collapsed by default) */}
        {hasSources && (
          <div className="mt-2 border-t border-gray-100 pt-2">
            <button
              onClick={() => setShowSources(!showSources)}
              className="text-xs text-blue-500 hover:text-blue-600"
            >
              {showSources
                ? "收起参考来源"
                : `查看参考来源 (${sources.length})`}
            </button>
            {showSources && (
              <div className="mt-2 space-y-2">
                {sources.map((s, i) => (
                  <SourceCard key={s.chunk_id || i} source={s} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
