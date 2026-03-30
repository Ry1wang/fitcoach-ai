import { useRef, useState } from "react";
import useDocuments from "../hooks/useDocuments";

const STATUS_MAP = {
  pending: { label: "等待中", color: "bg-yellow-400", pulse: false },
  processing: { label: "处理中", color: "bg-blue-400", pulse: true },
  ready: { label: "就绪", color: "bg-green-500", pulse: false },
  failed: { label: "失���", color: "bg-red-500", pulse: false },
};

const DOMAIN_OPTIONS = [
  { value: "", label: "自动识别" },
  { value: "training", label: "训练" },
  { value: "rehab", label: "康复" },
  { value: "nutrition", label: "营养" },
];

function formatSize(bytes) {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusBadge({ status }) {
  const info = STATUS_MAP[status] || STATUS_MAP.pending;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-gray-500">
      <span
        className={`inline-block h-2 w-2 rounded-full ${info.color} ${info.pulse ? "animate-pulse" : ""}`}
      />
      {info.label}
    </span>
  );
}

export default function DocumentPanel() {
  const {
    documents,
    loading,
    uploading,
    error,
    uploadDocument,
    deleteDocument,
    clearError,
  } = useDocuments();

  const [domain, setDomain] = useState("");
  const [confirmId, setConfirmId] = useState(null);
  const fileRef = useRef(null);

  const handleUpload = () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    uploadDocument(file, domain || null);
    fileRef.current.value = "";
  };

  const handleDelete = (docId) => {
    if (confirmId === docId) {
      deleteDocument(docId);
      setConfirmId(null);
    } else {
      setConfirmId(docId);
    }
  };

  return (
    <div className="flex w-72 shrink-0 flex-col border-r bg-white">
      {/* Header */}
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-700">文档管理</h2>
      </div>

      {/* Upload area */}
      <div className="space-y-2 border-b px-4 py-3">
        <div className="flex gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            className="min-w-0 flex-1 text-xs file:mr-2 file:rounded file:border-0 file:bg-blue-50 file:px-2 file:py-1 file:text-xs file:text-blue-600 hover:file:bg-blue-100"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className="flex-1 rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
          >
            {DOMAIN_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {uploading ? "上传中..." : "上传"}
          </button>
        </div>
      </div>

      {/* Error */}
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

      {/* Document list */}
      <div className="flex-1 overflow-y-auto">
        {loading && documents.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-gray-400">
            加载中...
          </p>
        ) : documents.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-gray-400">
            暂无文档，请上传 PDF
          </p>
        ) : (
          <ul>
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="group border-b px-4 py-3 hover:bg-gray-50"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p
                      className="truncate text-sm text-gray-800"
                      title={doc.filename}
                    >
                      {doc.filename}
                    </p>
                    <div className="mt-1 flex items-center gap-3">
                      <StatusBadge status={doc.status} />
                      <span className="text-xs text-gray-400">
                        {formatSize(doc.file_size)}
                      </span>
                      {doc.status === "ready" && doc.chunk_count > 0 && (
                        <span className="text-xs text-gray-400">
                          {doc.chunk_count} 块
                        </span>
                      )}
                    </div>
                    {doc.status === "failed" && doc.error_message && (
                      <p className="mt-1 text-xs text-red-500">
                        {doc.error_message}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="shrink-0 rounded px-1.5 py-0.5 text-xs text-gray-400 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                  >
                    {confirmId === doc.id ? "确认?" : "删除"}
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
