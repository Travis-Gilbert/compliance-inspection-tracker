"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="bg-white border border-red-200 rounded-lg p-6 max-w-md text-center">
        <div className="text-red-600 text-lg font-heading font-semibold mb-2">
          Something went wrong
        </div>
        <p className="text-sm text-gray-600 mb-4">
          {error.message || "An unexpected error occurred."}
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
