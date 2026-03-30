"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { getMapProperties, getStats } from "@/lib/api";
import { COMPLIANCE_STATUSES, REVIEW_FAST_LANES } from "@/lib/constants";
import type { Property, Stats } from "@/lib/types";
import InlineNotice from "@/components/InlineNotice";
import StatCard from "@/components/ui/StatCard";
import { DashboardSkeleton } from "@/components/LoadingSkeleton";

const ManagementCoverageMap = dynamic(
  () => import("@/components/ManagementCoverageMap"),
  { ssr: false },
);

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loadError, setLoadError] = useState("");
  const [mapProperties, setMapProperties] = useState<Property[]>([]);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapError, setMapError] = useState("");
  const [complianceExpanded, setComplianceExpanded] = useState(true);

  const loadData = async () => {
    setLoadError("");
    setMapError("");
    setMapLoading(true);
    const [statsResult, mapResult] = await Promise.allSettled([
      getStats(),
      getMapProperties(),
    ]);

    if (statsResult.status === "fulfilled") {
      setStats(statsResult.value);
    } else {
      setLoadError(statsResult.reason?.message || "Could not load dashboard data.");
    }

    if (mapResult.status === "fulfilled") {
      setMapProperties(mapResult.value.properties || []);
    } else {
      setMapProperties([]);
      setMapError(mapResult.reason?.message || "Could not load county coverage data.");
    }

    setMapLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  if (!stats && !loadError) {
    return (
      <div className="max-w-5xl mx-auto p-4 md:p-6">
        <DashboardSkeleton />
      </div>
    );
  }

  if (!stats && loadError) {
    return (
      <div className="max-w-5xl mx-auto p-4 md:p-6">
        <InlineNotice
          tone="error"
          title="Dashboard unavailable"
          message={loadError}
          actionLabel="Retry"
          onAction={loadData}
        />
      </div>
    );
  }

  const pct = stats?.percent_reviewed || 0;
  const highestUrgent = Math.max(stats!.needs_inspection, stats!.unreviewed);
  const highlightInspection = stats!.needs_inspection >= stats!.unreviewed;

  const laneCounts: Record<string, number> = {
    unreviewed: stats!.unreviewed,
    likely_demolished: stats!.unreviewed_by_detection?.likely_demolished || 0,
    likely_vacant: stats!.unreviewed_by_detection?.likely_vacant || 0,
    needs_inspection: stats!.needs_inspection,
    unprocessed: stats!.unreviewed_by_detection?.unprocessed || 0,
  };

  const nonCompliantCount = stats!.by_compliance_status?.non_compliant || 0;
  const taxDelinquentCount = stats!.by_compliance_status?.needs_outreach || 0;
  const allReviewed = stats!.unreviewed === 0 && stats!.total > 0;

  return (
    <div className="max-w-5xl mx-auto p-4 md:p-6 space-y-5">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Management Dashboard</h2>
        <p className="mt-1 text-sm text-gray-500">
          Countywide coverage and compliance progress overview
        </p>
      </div>

      {loadError && (
        <InlineNotice
          tone="warning"
          title="Some dashboard data could not be refreshed"
          message={loadError}
          actionLabel="Retry"
          onAction={loadData}
        />
      )}

      {/* Attention bar */}
      {allReviewed ? (
        <div className="rounded-lg border border-civic-green/20 bg-civic-green-pale px-4 py-3 flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-civic-green">
            All {stats!.total} properties reviewed.
          </span>
          <Link
            href="/review"
            className="text-xs font-medium text-civic-green hover:underline shrink-0"
          >
            Open Review Queue
          </Link>
        </div>
      ) : (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <span className="text-sm text-amber-800">
            <span className="font-semibold">{stats!.unreviewed}</span> properties need review
            {nonCompliantCount > 0 && (
              <> | <span className="font-semibold">{nonCompliantCount}</span> non-compliant</>
            )}
            {taxDelinquentCount > 0 && (
              <> | <span className="font-semibold">{taxDelinquentCount}</span> need outreach</>
            )}
          </span>
          <Link
            href="/review?filter=unreviewed"
            className="text-xs font-semibold text-amber-700 hover:underline shrink-0"
          >
            Open Review Queue &rarr;
          </Link>
        </div>
      )}

      {/* Review progress (compact) */}
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-gray-500 shrink-0">Review Progress</span>
        <div className="h-2 flex-1 rounded-full bg-gray-100">
          <div
            className="h-2 rounded-full bg-civic-green transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs font-medium text-civic-green shrink-0">{pct}%</span>
        <span className="text-xs text-gray-400 shrink-0 hidden sm:inline">
          ({stats!.reviewed} reviewed, {stats!.unreviewed} remaining)
        </span>
      </div>

      {/* Summary stats row */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Total Properties"
          value={stats!.total}
          accentColor="#9CA3AF"
          href="/review?filter=all"
        />
        <StatCard
          label="Resolved (Desk)"
          value={stats!.resolved}
          accentColor="#2E7D32"
          href="/review?filter=resolved"
        />
        <StatCard
          label="Needs Inspection"
          value={stats!.needs_inspection}
          accentColor="#EA580C"
          href="/review?filter=inconclusive"
          highlight={highlightInspection && stats!.needs_inspection > 0}
        />
        <StatCard
          label="Unreviewed"
          value={stats!.unreviewed}
          accentColor="#D1D5DB"
          href="/review?filter=unreviewed"
          highlight={!highlightInspection && stats!.unreviewed > 0}
        />
      </div>

      {/* Compliance Map (promoted) */}
      <ManagementCoverageMap
        properties={mapProperties}
        totalProperties={stats!.total}
        loading={mapLoading}
        error={mapError}
      />

      {/* Compliance status breakdown (collapsible) */}
      {stats!.by_compliance_status && Object.keys(stats!.by_compliance_status).length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white">
          <button
            onClick={() => setComplianceExpanded(!complianceExpanded)}
            className="w-full flex items-center justify-between p-5 text-left"
          >
            <h3 className="font-heading font-semibold text-gray-900">Compliance Status</h3>
            <svg
              className={`h-4 w-4 text-gray-400 transition-transform ${complianceExpanded ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {complianceExpanded && (
            <div className="px-5 pb-5">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                {COMPLIANCE_STATUSES.map((status) => {
                  const count = stats!.by_compliance_status[status.value] || 0;
                  return (
                    <div
                      key={status.value}
                      className="rounded-lg border border-gray-200 px-3 py-3 text-center"
                      style={{ borderLeftWidth: 4, borderLeftColor: status.color }}
                    >
                      <div className="font-heading text-xl font-bold" style={{ color: status.color }}>{count}</div>
                      <div className="mt-1 text-xs text-gray-600">{status.label}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Fast Review Lanes */}
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="font-heading font-semibold text-gray-900">Fast Review Lanes</h3>
            <p className="mt-1 text-sm text-gray-600">
              Jump straight into the queue slice most likely to move the work forward.
            </p>
          </div>
          <Link
            href="/review"
            className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            Open Full Queue
          </Link>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {REVIEW_FAST_LANES.map((lane) => (
            <Link
              key={lane.id}
              href={`/review?${new URLSearchParams(lane.params as Record<string, string>).toString()}`}
              className="rounded-lg border border-gray-200 bg-gray-50 p-4 transition-colors hover:border-civic-green/40 hover:bg-civic-green-pale/20"
            >
              <div className="text-xs uppercase tracking-wide text-gray-500">Open lane</div>
              <div className="mt-1 font-heading text-lg font-semibold text-gray-900">
                {lane.label}
              </div>
              <div className="mt-2 text-sm text-gray-600">{lane.description}</div>
              <div className="mt-3 text-xs font-medium text-civic-green">
                {laneCounts[lane.id] || 0} open properties
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
