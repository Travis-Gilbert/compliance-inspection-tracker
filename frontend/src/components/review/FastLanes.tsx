"use client";

import { REVIEW_FAST_LANES } from "@/lib/constants";
import type { ReviewFilters } from "@/hooks/useReviewQueue";
import type { Stats } from "@/lib/types";

interface FastLanesProps {
  stats: Stats | null;
  onApplyLane: (filters: Partial<ReviewFilters>) => void;
}

export default function FastLanes({ stats, onApplyLane }: FastLanesProps) {
  const laneCounts: Record<string, number> = {
    unreviewed: stats?.unreviewed || 0,
    likely_demolished: stats?.unreviewed_by_detection?.likely_demolished || 0,
    likely_vacant: stats?.unreviewed_by_detection?.likely_vacant || 0,
    needs_inspection: stats?.needs_inspection || 0,
    unprocessed: stats?.unreviewed_by_detection?.unprocessed || 0,
  };

  return (
    <div className="border-b border-gray-100 p-3">
      <div className="grid gap-1.5 grid-cols-5">
        {REVIEW_FAST_LANES.map((lane) => (
          <button
            key={lane.id}
            onClick={() =>
              onApplyLane({
                filter: lane.params.filter || "unreviewed",
                sort: lane.params.sort || "priority",
                program: (lane.params as Record<string, string>).program || "all",
                detection: (lane.params as Record<string, string>).detection || "all",
                compliance: "all",
                tax: "all",
                search: "",
              })
            }
            className="rounded border border-gray-200 bg-gray-50 px-2 py-1.5 text-left transition-colors hover:border-civic-green/40 hover:bg-civic-green-pale/20"
          >
            <div className="text-[10px] uppercase tracking-wide text-gray-500">
              {laneCounts[lane.id] || 0}
            </div>
            <div className="text-xs font-semibold text-gray-900 truncate">
              {lane.label}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
