"use client";

import { useEffect, useMemo, useState } from "react";
import SectionCard from "@/components/ui/SectionCard";
import StatCard from "@/components/ui/StatCard";

type CategoryKey =
  | "oversight_enforcement"
  | "data_governance"
  | "tech_infrastructure"
  | "stakeholder_coordination"
  | "operational_support";

interface CategoryDefinition {
  key: CategoryKey;
  label: string;
  targetPct: number;
  purpose: string;
}

interface ActivityEntry {
  id: string;
  date: string;
  category: CategoryKey;
  createdAt?: string;
  propertyRecord: string;
  action: string;
  sourceReference: string;
  status: string;
  hours: string;
}

interface StoredReportState {
  entries?: ActivityEntry[];
  followupItems?: string;
  overallStatus?: string;
  primaryWork?: string;
  questions?: string;
  weekEnd?: string;
  weekStart?: string;
}

const STORAGE_KEY = "gclba-weekly-compliance-report-v1";

const CATEGORIES: CategoryDefinition[] = [
  {
    key: "oversight_enforcement",
    label: "Compliance Oversight & Enforcement",
    targetPct: 40,
    purpose: "Monitor post-sale compliance across Featured Homes, VIP, Demolition, and Ready-for-Rehab properties.",
  },
  {
    key: "data_governance",
    label: "Project Tracking & Data Governance",
    targetPct: 35,
    purpose: "Maintain accurate property data and documentation across FileMaker, Regrid, GIS, and compliance files.",
  },
  {
    key: "tech_infrastructure",
    label: "Technology & Sales Infrastructure Support",
    targetPct: 10,
    purpose: "Support systems that improve sales operations, property tracking, and public-facing transparency.",
  },
  {
    key: "stakeholder_coordination",
    label: "Stakeholder & Interdepartmental Coordination",
    targetPct: 10,
    purpose: "Support coordination with Sales, Development, City of Flint departments, and other stakeholders.",
  },
  {
    key: "operational_support",
    label: "Operational Support & Continuity",
    targetPct: 5,
    purpose: "Provide cross-functional support during high-volume periods and documentation review.",
  },
];

const STATUS_OPTIONS = [
  "Complete",
  "In progress",
  "Pending direction",
  "Needs follow-up",
  "Escalated",
];

const ATTENTION_STATUSES = new Set(["Pending direction", "Needs follow-up", "Escalated"]);

function padDatePart(value: number): string {
  return String(value).padStart(2, "0");
}

function formatLocalDate(date: Date): string {
  return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`;
}

function getDefaultWeekRange(): { weekStart: string; weekEnd: string } {
  const now = new Date();
  const day = now.getDay();
  const daysFromMonday = day === 0 ? 6 : day - 1;
  const monday = new Date(now);
  monday.setDate(now.getDate() - daysFromMonday);

  const friday = new Date(monday);
  friday.setDate(monday.getDate() + 4);

  return {
    weekStart: formatLocalDate(monday),
    weekEnd: formatLocalDate(friday),
  };
}

function createEmptyEntry(date: string): ActivityEntry {
  return {
    id: "",
    date,
    category: "oversight_enforcement",
    propertyRecord: "",
    action: "",
    sourceReference: "",
    status: "Complete",
    hours: "0.5",
  };
}

function parseStoredState(value: string | null): StoredReportState | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as StoredReportState;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function getCategoryLabel(category: CategoryKey): string {
  return CATEGORIES.find((item) => item.key === category)?.label ?? category;
}

function toNumber(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function escapeCsv(value: string | number): string {
  const text = String(value);
  if (!/[",\n]/.test(text)) {
    return text;
  }
  return `"${text.replaceAll("\"", "\"\"")}"`;
}

function downloadText(filename: string, content: string, type: string): void {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function formatPct(value: number): string {
  return `${Math.round(value)}%`;
}

async function sha256Hex(content: string): Promise<string> {
  const encoded = new TextEncoder().encode(content);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export default function WeeklyReportPage() {
  const defaultWeek = useMemo(() => getDefaultWeekRange(), []);
  const [weekStart, setWeekStart] = useState(defaultWeek.weekStart);
  const [weekEnd, setWeekEnd] = useState(defaultWeek.weekEnd);
  const [overallStatus, setOverallStatus] = useState("On track");
  const [primaryWork, setPrimaryWork] = useState("");
  const [followupItems, setFollowupItems] = useState("");
  const [questions, setQuestions] = useState("");
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [draft, setDraft] = useState<ActivityEntry>(() => createEmptyEntry(defaultWeek.weekStart));
  const [copyStatus, setCopyStatus] = useState("");
  const [hasLoaded, setHasLoaded] = useState(false);

  useEffect(() => {
    const stored = parseStoredState(window.localStorage.getItem(STORAGE_KEY));
    if (stored) {
      setWeekStart(stored.weekStart || defaultWeek.weekStart);
      setWeekEnd(stored.weekEnd || defaultWeek.weekEnd);
      setOverallStatus(stored.overallStatus || "On track");
      setPrimaryWork(stored.primaryWork || "");
      setFollowupItems(stored.followupItems || "");
      setQuestions(stored.questions || "");
      setEntries(Array.isArray(stored.entries) ? stored.entries : []);
      setDraft(createEmptyEntry(stored.weekStart || defaultWeek.weekStart));
    }
    setHasLoaded(true);
  }, [defaultWeek.weekEnd, defaultWeek.weekStart]);

  useEffect(() => {
    if (!hasLoaded) {
      return;
    }

    const payload: StoredReportState = {
      entries,
      followupItems,
      overallStatus,
      primaryWork,
      questions,
      weekEnd,
      weekStart,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }, [entries, followupItems, hasLoaded, overallStatus, primaryWork, questions, weekEnd, weekStart]);

  useEffect(() => {
    setDraft((current) => ({ ...current, date: weekStart }));
  }, [weekStart]);

  const weekEntries = useMemo(() => {
    return entries
      .filter((entry) => entry.date >= weekStart && entry.date <= weekEnd)
      .sort((a, b) => `${a.date}-${a.category}`.localeCompare(`${b.date}-${b.category}`));
  }, [entries, weekEnd, weekStart]);

  const totalHours = useMemo(() => {
    return weekEntries.reduce((sum, entry) => sum + toNumber(entry.hours), 0);
  }, [weekEntries]);

  const categorySummaries = useMemo(() => {
    return CATEGORIES.map((category) => {
      const categoryEntries = weekEntries.filter((entry) => entry.category === category.key);
      const hours = categoryEntries.reduce((sum, entry) => sum + toNumber(entry.hours), 0);
      const actualPct = totalHours > 0 ? (hours / totalHours) * 100 : 0;
      return {
        ...category,
        actualPct,
        count: categoryEntries.length,
        entries: categoryEntries,
        hours,
      };
    });
  }, [totalHours, weekEntries]);

  const sourcedEntryCount = useMemo(() => {
    return weekEntries.filter((entry) => entry.sourceReference.trim().length > 0).length;
  }, [weekEntries]);

  const sourceCoveragePct = weekEntries.length > 0 ? (sourcedEntryCount / weekEntries.length) * 100 : 0;

  const attentionEntryCount = useMemo(() => {
    return weekEntries.filter((entry) => ATTENTION_STATUSES.has(entry.status)).length;
  }, [weekEntries]);

  const missingSourceEntries = useMemo(() => {
    return weekEntries.filter((entry) => entry.sourceReference.trim().length === 0);
  }, [weekEntries]);

  const reportMarkdown = useMemo(() => {
    const summaryRows = categorySummaries.map((category) => {
      return `| ${category.label} | ${category.targetPct}% | ${formatPct(category.actualPct)} | ${category.hours.toFixed(1)} hrs, ${category.count} activities |`;
    });

    const categorySections = categorySummaries.map((category) => {
      const activityRows = category.entries.length > 0
        ? category.entries.map((entry) => {
          const record = entry.propertyRecord || "General program work";
          const source = entry.sourceReference || "Internal work record";
          return `- ${entry.date} - ${record}: ${entry.action} (${source}; ${entry.status}; ${toNumber(entry.hours).toFixed(1)} hrs)`;
        }).join("\n")
        : "- None logged for this week.";

      return [
        `## ${category.label} (${category.targetPct}% target, ${formatPct(category.actualPct)} actual)`,
        "",
        category.purpose,
        "",
        activityRows,
      ].join("\n");
    });

    const activityRows = weekEntries.length > 0
      ? weekEntries.map((entry) => {
        return `| ${entry.date} | ${entry.createdAt || ""} | ${getCategoryLabel(entry.category)} | ${entry.propertyRecord || "General program work"} | ${entry.action} | ${entry.sourceReference || "Internal work record"} | ${entry.status} |`;
      }).join("\n")
      : "| [Date] | [Logged at] | [Category] | [Property / record] | [Action] | [Source / reference] | [Status] |";

    const missingSourceRows = missingSourceEntries.length > 0
      ? missingSourceEntries.map((entry) => {
        return `- ${entry.date} - ${entry.propertyRecord || "General program work"}: ${entry.action}`;
      }).join("\n")
      : "- None.";

    return [
      "# Weekly Compliance Program Report",
      "",
      `**Week of:** ${weekStart} to ${weekEnd}`,
      "**Prepared by:** Travis Gilbert",
      "**Submitted to:** Michael Freeman and Alexandria Riley",
      `**Submitted on:** ${formatLocalDate(new Date())}`,
      "",
      "## Executive Summary",
      "",
      `- **Overall status:** ${overallStatus || "On track"}`,
      `- **Primary work completed this week:** ${primaryWork || "[Add 1-3 sentence summary]"}`,
      `- **Items needing direction or follow-up:** ${followupItems || "None identified this week."}`,
      "",
      "## Time Allocation Summary",
      "",
      "| Area | Target | Actual | Notes |",
      "| --- | ---: | ---: | --- |",
      ...summaryRows,
      "",
      "## Record Controls",
      "",
      "- Report generated locally from logged activity rows.",
      `- Source/reference coverage: ${sourcedEntryCount} of ${weekEntries.length} activities (${formatPct(sourceCoveragePct)}).`,
      `- Activities needing direction, follow-up, or escalation: ${attentionEntryCount}.`,
      "- Rows missing source/reference:",
      missingSourceRows,
      "",
      ...categorySections.flatMap((section) => [section, ""]),
      "## Questions / Direction Needed",
      "",
      questions || "None at this time.",
      "",
      "## Activity Log",
      "",
      "| Date | Logged at | Category | Property / record | Action | Source / reference | Status |",
      "| --- | --- | --- | --- | --- | --- | --- |",
      activityRows,
      "",
    ].join("\n");
  }, [
    attentionEntryCount,
    categorySummaries,
    followupItems,
    missingSourceEntries,
    overallStatus,
    primaryWork,
    questions,
    sourcedEntryCount,
    sourceCoveragePct,
    weekEnd,
    weekEntries,
    weekStart,
  ]);

  const reportCsv = useMemo(() => {
    const rows = [
      ["date", "logged_at", "category", "target_pct", "hours", "property_record", "action", "source_reference", "status"],
      ...weekEntries.map((entry) => [
        entry.date,
        entry.createdAt || "",
        getCategoryLabel(entry.category),
        String(CATEGORIES.find((category) => category.key === entry.category)?.targetPct ?? ""),
        toNumber(entry.hours).toFixed(2),
        entry.propertyRecord,
        entry.action,
        entry.sourceReference,
        entry.status,
      ]),
    ];

    return rows.map((row) => row.map(escapeCsv).join(",")).join("\n");
  }, [weekEntries]);

  const handleAddEntry = () => {
    if (!draft.action.trim()) {
      setCopyStatus("Add an action before logging the activity.");
      return;
    }

    const entry: ActivityEntry = {
      ...draft,
      id: crypto.randomUUID(),
      action: draft.action.trim(),
      createdAt: new Date().toISOString(),
      hours: toNumber(draft.hours).toString(),
      propertyRecord: draft.propertyRecord.trim(),
      sourceReference: draft.sourceReference.trim(),
    };

    setEntries((current) => [entry, ...current]);
    setDraft(createEmptyEntry(draft.date));
    setCopyStatus("Activity logged.");
  };

  const handleDeleteEntry = (entryId: string) => {
    setEntries((current) => current.filter((entry) => entry.id !== entryId));
  };

  const handleClearWeek = () => {
    const confirmed = window.confirm("Clear only the activities in the visible report week?");
    if (!confirmed) {
      return;
    }

    setEntries((current) => current.filter((entry) => entry.date < weekStart || entry.date > weekEnd));
    setCopyStatus("Visible week cleared.");
  };

  const handleCopyReport = async () => {
    await navigator.clipboard.writeText(reportMarkdown);
    setCopyStatus("Report copied.");
  };

  const handleExportBundle = async () => {
    const generatedAt = new Date().toISOString();
    const bundlePayload = {
      schemaVersion: 1,
      generatedAt,
      reportType: "weekly_compliance_program_report",
      weekStart,
      weekEnd,
      preparedBy: "Travis Gilbert",
      submittedTo: ["Michael Freeman", "Alexandria Riley"],
      recordControls: {
        activityCount: weekEntries.length,
        attentionEntryCount,
        sourceCoveragePct: Math.round(sourceCoveragePct),
        sourcedEntryCount,
        totalHours: Number(totalHours.toFixed(2)),
      },
      categories: categorySummaries.map((category) => ({
        key: category.key,
        label: category.label,
        targetPct: category.targetPct,
        actualPct: Math.round(category.actualPct),
        count: category.count,
        hours: Number(category.hours.toFixed(2)),
      })),
      entries: weekEntries,
      reportMarkdown,
      reportCsv,
    };
    const canonicalPayload = JSON.stringify(bundlePayload, null, 2);
    const digest = await sha256Hex(canonicalPayload);
    const bundle = {
      ...bundlePayload,
      digest: {
        algorithm: "SHA-256",
        covers: "bundle fields excluding digest",
        value: digest,
      },
    };

    downloadText(
      `weekly-compliance-record-bundle-${weekEnd}.json`,
      JSON.stringify(bundle, null, 2),
      "application/json;charset=utf-8",
    );
    setCopyStatus(`Record bundle exported. Digest ${digest.slice(0, 12)}.`);
  };

  const totalActivitiesLabel = weekEntries.length === 1 ? "activity" : "activities";

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-heading text-2xl font-bold text-gray-900">Weekly Report Builder</h2>
          <p className="mt-1 max-w-3xl text-sm text-gray-500">
            Log factual compliance activity, keep the 40/35/10/10/5 split visible, and export the Friday report without connecting to any external system.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleCopyReport}
            className="rounded border border-civic-green bg-civic-green px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-civic-green-light"
          >
            Copy Report
          </button>
          <button
            type="button"
            onClick={() => downloadText(`weekly-compliance-report-${weekEnd}.md`, reportMarkdown, "text/markdown;charset=utf-8")}
            className="rounded border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-50"
          >
            Export Markdown
          </button>
          <button
            type="button"
            onClick={() => downloadText(`weekly-compliance-activity-${weekEnd}.csv`, reportCsv, "text/csv;charset=utf-8")}
            className="rounded border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-50"
          >
            Export CSV
          </button>
          <button
            type="button"
            onClick={handleExportBundle}
            className="rounded border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-50"
          >
            Export Bundle
          </button>
        </div>
      </div>

      {copyStatus && (
        <div className="rounded border border-civic-green/20 bg-civic-green-pale px-4 py-3 text-sm text-civic-green">
          {copyStatus}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <StatCard
          label="Logged This Week"
          value={weekEntries.length}
          accentColor="#1565C0"
          subtitle={totalActivitiesLabel}
        />
        <StatCard
          label="Tracked Time"
          value={`${totalHours.toFixed(1)} hrs`}
          accentColor="#2E7D32"
          subtitle="Used for actual percentages"
        />
        <StatCard
          label="Source Coverage"
          value={formatPct(sourceCoveragePct)}
          accentColor="#1565C0"
          subtitle={`${sourcedEntryCount} of ${weekEntries.length} referenced`}
        />
        <StatCard
          label="Report Range"
          value={`${weekStart.slice(5)} to ${weekEnd.slice(5)}`}
          accentColor="#9CA3AF"
          subtitle="Editable below"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_390px]">
        <div className="space-y-5">
          <SectionCard title="Report Settings" subtitle="Keep this factual and operational.">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-sm font-medium text-gray-700">
                Week start
                <input
                  type="date"
                  value={weekStart}
                  onChange={(event) => setWeekStart(event.target.value)}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Week end
                <input
                  type="date"
                  value={weekEnd}
                  onChange={(event) => setWeekEnd(event.target.value)}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                />
              </label>
            </div>

            <div className="mt-4 grid gap-4">
              <label className="text-sm font-medium text-gray-700">
                Overall status
                <input
                  value={overallStatus}
                  onChange={(event) => setOverallStatus(event.target.value)}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Primary work completed
                <textarea
                  value={primaryWork}
                  onChange={(event) => setPrimaryWork(event.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                  placeholder="Summarize the main compliance work completed this week."
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Items needing direction or follow-up
                <textarea
                  value={followupItems}
                  onChange={(event) => setFollowupItems(event.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                  placeholder="Use 'None identified this week' if nothing needs direction."
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Questions or direction needed
                <textarea
                  value={questions}
                  onChange={(event) => setQuestions(event.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                  placeholder="List decisions needed, or leave blank."
                />
              </label>
            </div>
          </SectionCard>

          <SectionCard title="Log Activity" subtitle="Each row becomes part of the report and export.">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-sm font-medium text-gray-700">
                Date
                <input
                  type="date"
                  value={draft.date}
                  onChange={(event) => setDraft((current) => ({ ...current, date: event.target.value }))}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Category
                <select
                  value={draft.category}
                  onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value as CategoryKey }))}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                >
                  {CATEGORIES.map((category) => (
                    <option key={category.key} value={category.key}>
                      {category.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-medium text-gray-700">
                Property or record
                <input
                  value={draft.propertyRecord}
                  onChange={(event) => setDraft((current) => ({ ...current, propertyRecord: event.target.value }))}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                  placeholder="Address, parcel ID, batch, or general program work"
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Time spent (hours)
                <input
                  type="number"
                  min="0"
                  step="0.25"
                  value={draft.hours}
                  onChange={(event) => setDraft((current) => ({ ...current, hours: event.target.value }))}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                />
              </label>
              <label className="text-sm font-medium text-gray-700 md:col-span-2">
                Action
                <textarea
                  value={draft.action}
                  onChange={(event) => setDraft((current) => ({ ...current, action: event.target.value }))}
                  rows={3}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                  placeholder="Example: Reconciled rehab status against GIS and Regrid records, then flagged missing proof of investment."
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Source or reference
                <input
                  value={draft.sourceReference}
                  onChange={(event) => setDraft((current) => ({ ...current, sourceReference: event.target.value }))}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                  placeholder="Photo set, permit record, GIS, Regrid, FileMaker export, email"
                />
              </label>
              <label className="text-sm font-medium text-gray-700">
                Status
                <select
                  value={draft.status}
                  onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}
                  className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-civic-green focus:outline-none focus:ring-2 focus:ring-civic-green/20"
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <button
              type="button"
              onClick={handleAddEntry}
              className="mt-4 rounded border border-civic-green bg-civic-green px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-civic-green-light"
            >
              Add Activity
            </button>
          </SectionCard>

          <SectionCard
            title="Activity Log"
            subtitle="Only activities inside the selected week are shown."
            action={weekEntries.length > 0 && (
              <button
                type="button"
                onClick={handleClearWeek}
                className="rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
              >
                Clear Week
              </button>
            )}
          >
            {weekEntries.length === 0 ? (
              <div className="rounded border border-dashed border-gray-200 bg-gray-50 px-4 py-6 text-sm text-gray-500">
                No activities logged for this week yet.
              </div>
            ) : (
              <div className="-mx-5 overflow-x-auto">
                <table className="min-w-full border-y border-gray-200 text-left text-sm">
                  <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                    <tr>
                      <th className="px-5 py-3 font-medium">Date</th>
                      <th className="px-5 py-3 font-medium">Category</th>
                      <th className="px-5 py-3 font-medium">Property / record</th>
                      <th className="px-5 py-3 font-medium">Action</th>
                      <th className="px-5 py-3 font-medium">Hours</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                      <th className="px-5 py-3 font-medium">Remove</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {weekEntries.map((entry) => (
                      <tr key={entry.id} className="align-top">
                        <td className="whitespace-nowrap px-5 py-3 text-gray-600">{entry.date}</td>
                        <td className="min-w-48 px-5 py-3 font-medium text-gray-800">{getCategoryLabel(entry.category)}</td>
                        <td className="min-w-44 px-5 py-3 text-gray-600">{entry.propertyRecord || "General program work"}</td>
                        <td className="min-w-72 px-5 py-3 text-gray-700">
                          <div>{entry.action}</div>
                          {entry.sourceReference && (
                            <div className="mt-1 text-xs text-gray-500">Source: {entry.sourceReference}</div>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-5 py-3 text-gray-600">{toNumber(entry.hours).toFixed(1)}</td>
                        <td className="whitespace-nowrap px-5 py-3 text-gray-600">{entry.status}</td>
                        <td className="px-5 py-3">
                          <button
                            type="button"
                            onClick={() => handleDeleteEntry(entry.id)}
                            className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-800"
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </div>

        <aside className="space-y-5">
          <SectionCard title="Allocation" subtitle="Actual percentages are based on logged hours.">
            <div className="space-y-4">
              {categorySummaries.map((category) => (
                <div key={category.key}>
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="font-medium text-gray-700">{category.label}</span>
                    <span className="font-medium text-gray-500">
                      {formatPct(category.actualPct)} / {category.targetPct}%
                    </span>
                  </div>
                  <div className="mt-2 h-2 rounded-full bg-gray-100">
                    <div
                      className="h-2 rounded-full bg-civic-green transition-all"
                      style={{ width: `${Math.min(100, category.actualPct)}%` }}
                    />
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    {category.hours.toFixed(1)} hrs, {category.count} logged
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Record Controls" subtitle="Checks included in report and bundle.">
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3 border-b border-gray-100 pb-2">
                <span className="text-gray-500">Activities with source/reference</span>
                <span className="font-medium text-gray-800">{sourcedEntryCount} of {weekEntries.length}</span>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-gray-100 pb-2">
                <span className="text-gray-500">Missing source/reference</span>
                <span className="font-medium text-gray-800">{missingSourceEntries.length}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-gray-500">Needs direction or follow-up</span>
                <span className="font-medium text-gray-800">{attentionEntryCount}</span>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Report Preview" subtitle="Copy or export this text for the Friday report.">
            <pre className="max-h-[720px] overflow-auto whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] leading-relaxed text-gray-700">
              {reportMarkdown}
            </pre>
          </SectionCard>
        </aside>
      </div>
    </div>
  );
}
