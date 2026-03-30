export default function StreamingText({ routingInfo }) {
  if (!routingInfo) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 text-sm text-blue-600">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
      {routingInfo.label}Agent 回答中...
      {routingInfo.cached && (
        <span className="text-xs text-gray-400">(缓存)</span>
      )}
    </div>
  );
}
