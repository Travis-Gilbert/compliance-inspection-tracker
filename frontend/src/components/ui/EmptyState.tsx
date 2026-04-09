import Link from "next/link";

interface EmptyStateProps {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  actionHref?: string;
}

export default function EmptyState({ title, message, actionLabel, onAction, actionHref }: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-8 text-center">
      <p className="text-gray-600">{title}</p>
      <p className="text-xs text-gray-400 mt-2">{message}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="mt-3 text-xs font-medium text-civic-green hover:underline"
        >
          {actionLabel}
        </button>
      )}
      {actionLabel && actionHref && !onAction && (
        <Link
          href={actionHref}
          className="mt-3 inline-block text-xs font-medium text-civic-green hover:underline"
        >
          {actionLabel}
        </Link>
      )}
    </div>
  );
}
