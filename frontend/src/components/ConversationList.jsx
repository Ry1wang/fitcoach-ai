import { useCallback, useEffect, useState } from "react";
import client from "../api/client";

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  return new Date(dateStr).toLocaleDateString("zh-CN");
}

export default function ConversationList({ activeId, onSelect, onNew }) {
  const [conversations, setConversations] = useState([]);
  const [confirmId, setConfirmId] = useState(null);

  const fetchConversations = useCallback(async () => {
    try {
      const { data } = await client.get("/conversations");
      setConversations(data.conversations);
    } catch {
      // silent — sidebar is non-critical
    }
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations, activeId]);

  const handleDelete = async (e, convId) => {
    e.stopPropagation();
    if (confirmId === convId) {
      try {
        await client.delete(`/conversations/${convId}`);
        setConversations((prev) => prev.filter((c) => c.id !== convId));
        if (activeId === convId) onNew();
      } catch {
        // silent
      }
      setConfirmId(null);
    } else {
      setConfirmId(convId);
    }
  };

  return (
    <div className="hidden md:flex w-52 shrink-0 flex-col border-r bg-gray-50">
      <div className="flex items-center justify-between border-b px-3 py-3">
        <h3 className="text-xs font-semibold text-gray-600">对话记录</h3>
        <button
          onClick={onNew}
          className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700"
        >
          新对话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-gray-400">暂无对话</p>
        ) : (
          <ul>
            {conversations.map((conv) => (
              <li
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={`group cursor-pointer border-b px-3 py-2.5 transition ${
                  activeId === conv.id
                    ? "bg-blue-50 border-l-2 border-l-blue-500"
                    : "hover:bg-gray-100"
                }`}
              >
                <p className="truncate text-xs text-gray-800">
                  {conv.title || "新对话"}
                </p>
                <div className="mt-0.5 flex items-center justify-between">
                  <span className="text-xs text-gray-400">
                    {timeAgo(conv.updated_at)}
                  </span>
                  <button
                    onClick={(e) => handleDelete(e, conv.id)}
                    className="text-xs text-gray-400 opacity-0 hover:text-red-500 group-hover:opacity-100"
                  >
                    {confirmId === conv.id ? "确认?" : "删除"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
