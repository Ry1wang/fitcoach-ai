import { useCallback, useEffect, useRef, useState } from "react";
import client from "../api/client";

const POLL_INTERVAL = 3000;

export default function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const pollTimerRef = useRef(null);

  // ── Fetch document list ─────────────���───────────────────────────────────
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/documents");
      setDocuments(data.documents);
      return data.documents;
    } catch {
      setError("获取文档列表失败");
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Upload ───────���──────────────────────────────────────────────────────
  const uploadDocument = useCallback(
    async (file, domain) => {
      setUploading(true);
      setError("");
      try {
        const form = new FormData();
        form.append("file", file);
        if (domain) form.append("domain", domain);
        await client.post("/documents/upload", form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        // Refresh list and start polling for the new doc
        await fetchDocuments();
        startPolling();
      } catch (err) {
        const detail = err.response?.data?.detail;
        setError(detail?.message || "上传失败，请重试");
      } finally {
        setUploading(false);
      }
    },
    [fetchDocuments], // eslint-disable-line react-hooks/exhaustive-deps -- startPolling is stable (declared after this hook, so can't be in deps array without reordering)
  );

  // ── Delete ──────────��───────────────────────────────────��───────────────
  const deleteDocument = useCallback(
    async (docId) => {
      setError("");
      try {
        await client.delete(`/documents/${docId}`);
        setDocuments((prev) => prev.filter((d) => d.id !== docId));
      } catch {
        setError("删除失败，请重��");
      }
    },
    [],
  );

  // ── Polling for status transitions ──────────────────────────────────────
  const startPolling = useCallback(() => {
    // Avoid duplicate timers
    if (pollTimerRef.current) return;
    pollTimerRef.current = setInterval(async () => {
      const docs = await fetchDocuments();
      const hasPending = docs.some(
        (d) => d.status === "pending" || d.status === "processing",
      );
      if (!hasPending) {
        stopPolling();
      }
    }, POLL_INTERVAL);
  }, [fetchDocuments]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  // ── Initial load ───────────────────────────────────────────────────────
  useEffect(() => {
    fetchDocuments().then((docs) => {
      const hasPending = docs.some(
        (d) => d.status === "pending" || d.status === "processing",
      );
      if (hasPending) startPolling();
    });
    return () => stopPolling();
  }, [fetchDocuments, startPolling, stopPolling]);

  return {
    documents,
    loading,
    uploading,
    error,
    uploadDocument,
    deleteDocument,
    clearError: () => setError(""),
  };
}
