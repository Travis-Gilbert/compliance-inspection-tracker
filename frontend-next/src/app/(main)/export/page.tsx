"use client";

import { useEffect, useState } from "react";
import {
  exportCSVUrl,
  exportInspectionListUrl,
  exportResolvedCsvUrl,
  exportSummaryUrl,
  getStats,
} from "@/lib/api";
import InlineNotice from "@/components/InlineNotice";

export default function ExportPage() {
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState("");

  const loadStats = async () => {
    setError("");
    try {
      setStats(await getStats());
    } catch (loadError: any) {
      setError(loadError.message || "Could not load export counts.");
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  const exportOptions = [
    {
      title: "Full Export (CSV)",
      description: "All properties with findings, detection results, and notes. Suitable for FileMaker re-import or Excel analysis.",
      url: exportCSVUrl(),
      filename: "compliance-full-export.csv",
      count: stats?.total || 0,
      available: (stats?.total || 0) > 0,
    },
    {
      title: "FileMaker Import CSV",
      description: "Only the fields Lucille needs for FileMaker compliance import: address, parcel ID, buyer, program, finding, and compliance status.",
      url: exportCSVUrl({ finding: "", detection: "" }),
      filename: "filemaker-import.csv",
      count: stats?.total || 0,
      available: (stats?.total || 0) > 0,
    },
    {
      title: "Inspection List (CSV)",
      description: "Properties flagged for physical inspection or elevated follow-up. Formatted for field use with space for on-site findings.",
      url: exportInspectionListUrl(),
      filename: "inspection-list.csv",
      count: stats?.inspection_candidates || 0,
      available: (stats?.inspection_candidates || 0) > 0,
    },
    {
      title: "Summary Report (Text)",
      description: "A plain-text summary of progress, findings breakdown, and program statistics. Suitable for email updates to leadership.",
      url: exportSummaryUrl(),
      filename: "compliance-summary.txt",
      count: null,
      available: (stats?.total || 0) > 0,
    },
    {
      title: "Resolved Properties (CSV)",
      description: "All properties resolved through desk research, not just one finding type. Useful for updating FileMaker compliance status.",
      url: exportResolvedCsvUrl(),
      filename: "resolved-properties.csv",
      count: stats?.resolved || 0,
      available: (stats?.resolved || 0) > 0,
    },
  ];

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Export</h2>
        <p className="mt-1 text-sm text-gray-500">
          Download your review findings as CSV or text files for FileMaker import, field work, or reporting.
        </p>
      </div>

      {error && (
        <InlineNotice
          tone="error"
          title="Export counts unavailable"
          message={error}
          actionLabel="Retry"
          onAction={loadStats}
        />
      )}

      <div className="space-y-3">
        {exportOptions.map((option) => (
          <div
            key={option.title}
            className={`rounded-lg border border-gray-200 bg-white p-4 ${option.available ? "" : "opacity-50"}`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-semibold text-gray-900 font-heading">{option.title}</div>
                <div className="mt-1 text-xs text-gray-500">{option.description}</div>
                {option.count !== null && (
                  <div className="mt-1 text-xs text-gray-400">{option.count} properties</div>
                )}
              </div>
              <a
                href={option.available ? option.url : "#"}
                download={option.filename}
                className={`shrink-0 rounded-md px-4 py-2 text-xs font-medium transition-colors ${
                  option.available
                    ? "bg-civic-green text-white hover:bg-civic-green-light"
                    : "pointer-events-none bg-gray-200 text-gray-400"
                }`}
              >
                Download
              </a>
            </div>
          </div>
        ))}
      </div>

      {stats && stats.total > 0 && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Current Status</div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>Total: <span className="font-medium">{stats.total}</span></div>
            <div>Reviewed: <span className="font-medium">{stats.reviewed}</span></div>
            <div>Resolved: <span className="font-medium text-civic-green">{stats.resolved}</span></div>
            <div>Needs Visit: <span className="font-medium text-orange-600">{stats.needs_inspection}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}
