"use client";

import { FINDINGS } from "@/lib/constants";

interface BatchActionBarProps {
  selectedCount: number;
  onBatchUpdate: (finding: string) => void;
  onClear: () => void;
}

export default function BatchActionBar({ selectedCount, onBatchUpdate, onClear }: BatchActionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="sticky bottom-0 bg-white border-t border-gray-200 px-4 py-3 shadow-sm">
      <div className="flex items-center gap-3 overflow-x-auto">
        <span className="shrink-0 text-xs font-medium text-gray-700">
          {selectedCount} selected
        </span>
        <div className="flex shrink-0 gap-1.5">
          {FINDINGS.map((finding) => (
            <button
              key={finding.value}
              onClick={() => onBatchUpdate(finding.value)}
              className="shrink-0 rounded px-2.5 py-1.5 text-xs font-medium"
              style={{ color: finding.color, background: finding.bg }}
            >
              {finding.label}
            </button>
          ))}
        </div>
        <button
          onClick={onClear}
          className="shrink-0 text-xs text-gray-500 hover:text-gray-700"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
