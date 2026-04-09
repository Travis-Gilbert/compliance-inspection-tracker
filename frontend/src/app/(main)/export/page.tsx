"use client";

import { useEffect, useState } from "react";
import {
  exportCSVUrl,
  exportInspectionListUrl,
  exportResolvedCsvUrl,
  exportSummaryUrl,
  getStats,
} from "@/lib/api";
import type { Stats } from "@/lib/types";
import InlineNotice from "@/components/InlineNotice";

export default function ExportPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  const loadStats = async () => {
    setError("");
    try {
      setStats(await getStats());
    } catch (loadError: unknown) {
      setError((loadError as Error).message || "Could not load export counts.");
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  const exportCards = [
    {
      title: "Full CSV Export",
      description: "All properties with every column: findings, detection results, compliance status, and notes.",
      url: exportCSVUrl(),
      filename: "compliance-full-export.csv",
      count: stats?.total || 0,
    },
    {
      title: "Inspection List",
      description: "Properties marked for physical inspection or elevated follow-up, formatted for field use.",
      url: exportInspectionListUrl(),
      filename: "inspection-list.csv",
      count: stats?.inspection_candidates || stats?.needs_inspection || 0,
    },
    {
      title: "Resolved Properties",
      description: "All properties resolved through desk research. Useful for updating FileMaker compliance status.",
      url: exportResolvedCsvUrl(),
      filename: "resolved-properties.csv",
      count: stats?.resolved || 0,
    },
    {
      title: "Summary Report",
      description: "Plain-text summary of progress, findings breakdown, and program statistics for email updates.",
      url: exportSummaryUrl(),
      filename: "compliance-summary.txt",
      count: null,
    },
  ];

  return (
    <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-6">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Export</h2>
        <p className="mt-1 text-sm text-gray-500">
          Download review findings as CSV or text for FileMaker import, field work, or reporting.
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

      <div className="grid gap-3 sm:grid-cols-2">
        {exportCards.map((card) => {
          const available = card.count === null ? (stats?.total || 0) > 0 : card.count > 0;
          return (
            <div
              key={card.title}
              className={`rounded-lg border border-gray-200 bg-white p-5 flex flex-col ${available ? "" : "opacity-50"}`}
            >
              <div className="flex-1">
                <div className="text-sm font-semibold text-gray-900 font-heading">{card.title}</div>
                <div className="mt-1.5 text-xs text-gray-500">{card.description}</div>
                {card.count !== null && (
                  <div className="mt-1 text-xs text-gray-400">{card.count} properties</div>
                )}
              </div>
              <a
                href={available ? card.url : "#"}
                download={card.filename}
                className={`mt-4 block rounded-md px-4 py-2 text-center text-xs font-medium transition-colors ${
                  available
                    ? "bg-civic-green text-white hover:bg-civic-green-light"
                    : "pointer-events-none bg-gray-200 text-gray-400"
                }`}
              >
                Download
              </a>
            </div>
          );
        })}
      </div>
    </div>
  );
}
