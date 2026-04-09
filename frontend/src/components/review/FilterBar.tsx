"use client";

import { forwardRef, useState } from "react";
import {
  COMPLIANCE_STATUSES,
  PROGRAMS,
  TAX_STATUSES,
} from "@/lib/constants";
import type { ReviewFilters } from "@/hooks/useReviewQueue";
import FilterPill from "@/components/ui/FilterPill";

const FILTER_OPTIONS = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Open Review" },
  { value: "resolved", label: "Resolved" },
  { value: "inconclusive", label: "Needs Inspection" },
];

const SORT_OPTIONS = [
  { value: "priority", label: "Compliance Priority" },
  { value: "detection_score", label: "Detection Score" },
  { value: "created_at", label: "Newest First" },
  { value: "address", label: "Address A-Z" },
];

const DETECTION_FILTER_OPTIONS = [
  { value: "all", label: "All detections" },
  { value: "likely_demolished", label: "Likely Demolished" },
  { value: "likely_vacant", label: "Likely Vacant" },
  { value: "likely_occupied", label: "Likely Occupied" },
  { value: "no_streetview", label: "No Street View" },
  { value: "unprocessed", label: "Not Processed" },
];

interface FilterBarProps {
  filters: ReviewFilters;
  onChange: (partial: Partial<ReviewFilters>) => void;
}

const FilterBar = forwardRef<HTMLInputElement, FilterBarProps>(function FilterBar(
  { filters, onChange },
  searchRef,
) {
  const [expanded, setExpanded] = useState(false);

  const advancedFilterCount = [
    filters.sort !== "priority",
    filters.program !== "all",
    filters.detection !== "all",
    filters.compliance !== "all",
    filters.tax !== "all",
  ].filter(Boolean).length;

  return (
    <form role="search" className="border-b border-gray-100 p-3 space-y-2">
      {/* Primary controls: filter pills + search */}
      <div className="flex flex-wrap items-center gap-1.5">
        {FILTER_OPTIONS.map((option) => (
          <FilterPill
            key={option.value}
            label={option.label}
            active={filters.filter === option.value}
            onClick={() => onChange({ filter: option.value })}
          />
        ))}
        <div className="flex-1 min-w-[140px] ml-1">
          <input
            ref={searchRef}
            value={filters.search}
            onChange={(e) => onChange({ search: e.target.value })}
            placeholder="Search address, parcel, buyer..."
            className="w-full rounded border border-gray-200 px-2.5 py-1.5 text-xs"
          />
        </div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className={`rounded px-2.5 py-1.5 text-xs font-medium transition-colors ${
            advancedFilterCount > 0
              ? "border border-civic-green/20 bg-civic-green-pale text-civic-green"
              : "border border-gray-200 text-gray-600 hover:bg-gray-50"
          }`}
        >
          More filters{advancedFilterCount > 0 ? ` (${advancedFilterCount})` : ""}
        </button>
      </div>

      {/* Expanded advanced filters */}
      {expanded && (
        <div className="flex flex-wrap gap-2 pt-1">
          <select
            value={filters.sort}
            onChange={(e) => onChange({ sort: e.target.value })}
            className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>

          <select
            value={filters.program}
            onChange={(e) => onChange({ program: e.target.value })}
            className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          >
            <option value="all">All programs</option>
            {PROGRAMS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>

          <select
            value={filters.detection}
            onChange={(e) => onChange({ detection: e.target.value })}
            className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          >
            {DETECTION_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>

          <select
            value={filters.compliance}
            onChange={(e) => onChange({ compliance: e.target.value })}
            className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          >
            <option value="all">All compliance</option>
            {COMPLIANCE_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>

          <select
            value={filters.tax}
            onChange={(e) => onChange({ tax: e.target.value })}
            className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          >
            <option value="all">All tax status</option>
            {TAX_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      )}
    </form>
  );
});

export default FilterBar;
