"use client";

export default function MapError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-warm-50 flex items-center justify-center">
      <div className="bg-white border border-red-200 rounded-lg p-6 max-w-md text-center">
        <div className="text-red-600 text-lg font-heading font-semibold mb-2">
          Map could not load
        </div>
        <p className="text-sm text-gray-600 mb-4">
          {error.message || "An unexpected error occurred loading the map."}
        </p>
        <button
          onClick={reset}
          className="text-sm font-medium px-4 py-2 rounded bg-civic-green text-white hover:bg-civic-green-light transition-colors"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
