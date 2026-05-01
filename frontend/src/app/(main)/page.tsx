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

  const imageryFetched = stats?.imagery_fetched || 0;
  const detectionRan = stats?.detection_ran || 0;
  const photoReady = stats?.photo_ready || 0;
  const compliantReviewed = stats?.compliant_reviewed || 0;
  const nonCompliantReviewed = stats?.non_compliant_reviewed || 0;
  const inProgressReviewed = stats?.in_progress_reviewed || 0;
  const photoCoveragePct = stats!.total > 0
    ? Math.round((photoReady / stats!.total) * 100)
    : 0;
  const manualReviewPct = stats!.percent_reviewed || 0;
  const compliantReviewedPct = stats!.compliant_percent_reviewed || 0;
  const highlightInspection = stats!.needs_inspection >= stats!.unreviewed;

  const laneCounts: Record<string, number> = {
    unreviewed: stats!.unreviewed,
    likely_demolished: stats!.unreviewed_by_detection?.likely_demolished || 0,
    likely_vacant: stats!.unreviewed_by_detection?.likely_vacant || 0,
    needs_inspection: stats!.needs_inspection,
    unprocessed: stats!.unreviewed_by_detection?.unprocessed || 0,
  };

  const allReviewed = stats!.unreviewed === 0 && stats!.total > 0;
  const allPhotoReady = photoReady === stats!.total && stats!.total > 0;
  const overviewHeadline = allReviewed
    ? `${stats!.reviewed} reviewed, 0 pending.`
    : allPhotoReady
      ? `${stats!.reviewed} reviewed, ${stats!.unreviewed} pending. Photo evidence is ready.`
      : `${stats!.reviewed} reviewed, ${stats!.unreviewed} pending.`;
  const overviewCopy = allReviewed
    ? `${compliantReviewed} reviewed properties are program-aware compliant. Use export for the desk-review handoff.`
    : allPhotoReady
      ? "The evidence set is ready. The remaining work is manual judgment, notes, and field follow-up decisions."
      : "Use the queue and gallery to complete photo evidence before treating compliance percentages as meaningful.";

  return (
    <div className="max-w-5xl mx-auto p-4 md:p-6 space-y-5">
      <div>
          <h2 className="font-heading text-2xl font-bold text-gray-900">Operations Dashboard</h2>
        <p className="mt-1 text-sm text-gray-500">
          Manual review progress, photo readiness, and map coverage
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

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_320px]">
        <section className="rounded border border-gray-200 bg-white p-5 shadow-[0_1px_4px_rgba(15,23,42,0.04)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-gray-500">County overview</div>
              <h3 className="mt-2 font-heading text-2xl font-semibold leading-tight text-gray-900">
                {overviewHeadline}
              </h3>
              <p className="mt-2 max-w-2xl text-sm text-gray-600">
                {overviewCopy}
              </p>
            </div>
            <Link
              href="/processing"
              className="rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              Open Processing
            </Link>
          </div>

          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-civic-blue/20 bg-white px-3 py-1 font-medium text-civic-blue">
              {photoReady} photo-ready
            </span>
            <span className="rounded-full border border-civic-green/20 bg-white px-3 py-1 font-medium text-civic-green">
              {compliantReviewed} compliant among reviewed
            </span>
            <span className="rounded-full border border-gray-200 bg-white px-3 py-1 font-medium text-gray-700">
              {stats!.reviewed} manual findings
            </span>
            {nonCompliantReviewed > 0 && (
              <span className="rounded-full border border-orange-200 bg-white px-3 py-1 font-medium text-orange-700">
                {nonCompliantReviewed} non-compliant
              </span>
            )}
            {inProgressReviewed > 0 && (
              <span className="rounded-full border border-civic-blue/20 bg-white px-3 py-1 font-medium text-civic-blue">
                {inProgressReviewed} in progress
              </span>
            )}
          </div>

          <div className="mt-5 space-y-3">
            <div className="rounded-lg border border-white/80 bg-white/80 px-3 py-3">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium text-gray-600">Photo-ready records</span>
                <span className="font-medium text-civic-blue">
                  {photoCoveragePct}% ({photoReady} of {stats!.total})
                </span>
              </div>
              <div className="mt-2 h-2 rounded-full bg-gray-100">
                <div
                  className="h-2 rounded-full bg-civic-blue transition-all duration-500"
                  style={{ width: `${photoCoveragePct}%` }}
                />
              </div>
            </div>

            <div className="rounded-lg border border-white/80 bg-white/80 px-3 py-3">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium text-gray-600">Compliant among reviewed</span>
                <span className="font-medium text-civic-green">
                  {compliantReviewedPct}% ({compliantReviewed} of {stats!.reviewed})
                </span>
              </div>
              <div className="mt-2 h-2 rounded-full bg-gray-100">
                <div
                  className="h-2 rounded-full bg-civic-green transition-all duration-500"
                  style={{ width: `${compliantReviewedPct}%` }}
                />
              </div>
            </div>

            <div className="rounded-lg border border-white/80 bg-white/80 px-3 py-3">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="font-medium text-gray-600">Manual review</span>
                <span className="font-medium text-gray-700">
                  {manualReviewPct}% ({stats!.reviewed} of {stats!.total})
                </span>
              </div>
              <div className="mt-2 h-2 rounded-full bg-gray-100">
                <div
                  className="h-2 rounded-full bg-gray-500 transition-all duration-500"
                  style={{ width: `${manualReviewPct}%` }}
                />
              </div>
            </div>
          </div>
        </section>

        <aside className="rounded border border-civic-green/20 bg-civic-green-pale/60 p-5 shadow-[0_1px_4px_rgba(46,125,50,0.08)]">
          <div className="text-[11px] uppercase tracking-wide text-civic-green">Pending manual review</div>
          <div className="mt-3 font-heading text-4xl font-bold text-gray-900">{stats!.unreviewed}</div>
          <p className="mt-2 text-sm text-gray-700">
            Properties still need a human finding before the desk-review pass is complete.
          </p>
          <Link
            href="/review?filter=unreviewed"
            className="mt-4 inline-flex rounded border border-civic-green bg-civic-green px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-civic-green-light"
          >
            Open Manual Review
          </Link>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-3">
              <div className="text-gray-500">Needs inspection</div>
              <div className="mt-1 font-heading text-xl text-gray-900">{stats!.needs_inspection}</div>
            </div>
            <div className="rounded-lg border border-white/70 bg-white/80 px-3 py-3">
              <div className="text-gray-500">Desk resolved</div>
              <div className="mt-1 font-heading text-xl text-gray-900">{stats!.resolved}</div>
            </div>
          </div>
        </aside>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <StatCard
          label="Total Properties"
          value={stats!.total}
          accentColor="#9CA3AF"
          subtitle="Current county list"
          href="/review?filter=all"
        />
        <StatCard
          label="Resolved (Desk)"
          value={stats!.resolved}
          accentColor="#2E7D32"
          subtitle="Manual finding logged"
          href="/review?filter=resolved"
        />
        <StatCard
          label="Needs Inspection"
          value={stats!.needs_inspection}
          accentColor="#EA580C"
          subtitle="Still needs a field visit"
          href="/review?filter=inconclusive"
          highlight={highlightInspection && stats!.needs_inspection > 0}
        />
      </div>

      {/* Compliance Map (promoted) */}
      <ManagementCoverageMap
        properties={mapProperties}
        totalProperties={stats!.total}
        humanReviewed={stats!.reviewed}
        imageryFetched={imageryFetched}
        systemTriaged={detectionRan}
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
            <h3 className="font-heading font-semibold text-gray-900">Imported Compliance Status</h3>
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
                      className="rounded-lg border px-3 py-3 text-center"
                      style={{ borderColor: `${status.color}33`, backgroundColor: status.bg }}
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
