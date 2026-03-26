"use client";

const TONE_STYLES: Record<string, string> = {
  info: "border-civic-blue/20 bg-civic-blue-pale text-civic-blue",
  success: "border-civic-green/20 bg-civic-green-pale text-civic-green",
  warning: "border-orange-200 bg-orange-50 text-orange-700",
  error: "border-red-200 bg-red-50 text-red-700",
};

interface InlineNoticeProps {
  tone?: "info" | "success" | "warning" | "error";
  title?: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export default function InlineNotice({
  tone = "info",
  title,
  message,
  actionLabel,
  onAction,
  className = "",
}: InlineNoticeProps) {
  if (!title && !message) return null;

  return (
    <div className={`rounded-lg border px-4 py-3 ${TONE_STYLES[tone] || TONE_STYLES.info} ${className}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          {title && <div className="text-sm font-semibold">{title}</div>}
          {message && <div className="text-sm opacity-90">{message}</div>}
        </div>
        {actionLabel && onAction && (
          <button
            type="button"
            onClick={onAction}
            className="shrink-0 rounded border border-current/20 bg-white/80 px-3 py-1.5 text-xs font-semibold hover:bg-white"
          >
            {actionLabel}
          </button>
        )}
      </div>
    </div>
  );
}
