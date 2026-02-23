import { useState, useEffect } from "react";
import { getStats, exportCSVUrl, exportInspectionListUrl, exportSummaryUrl } from "../utils/api";

export default function Export() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    getStats().then(setStats).catch(console.error);
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
      title: "Inspection List (CSV)",
      description: "Only properties flagged for physical inspection. Formatted for field use with space for on-site findings.",
      url: exportInspectionListUrl(),
      filename: "inspection-list.csv",
      count: stats?.needs_inspection || 0,
      available: (stats?.needs_inspection || 0) > 0,
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
      description: "Only properties resolved through desk research (no site visit needed). Useful for updating FileMaker compliance status.",
      url: exportCSVUrl({ finding: "visibly_renovated" }) + "&" + new URLSearchParams({ detection: "" }),
      filename: "resolved-properties.csv",
      count: stats?.resolved || 0,
      available: (stats?.resolved || 0) > 0,
    },
  ];

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Export</h2>
        <p className="text-sm text-gray-500 mt-1">
          Download your review findings as CSV files for FileMaker import or reporting.
        </p>
      </div>

      <div className="space-y-3">
        {exportOptions.map(opt => (
          <div
            key={opt.title}
            className={`bg-white border border-gray-200 rounded-lg p-4 ${
              opt.available ? "" : "opacity-50"
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="font-heading font-semibold text-gray-900 text-sm">{opt.title}</div>
                <div className="text-xs text-gray-500 mt-1">{opt.description}</div>
                {opt.count !== null && (
                  <div className="text-xs text-gray-400 mt-1">{opt.count} properties</div>
                )}
              </div>
              <a
                href={opt.available ? opt.url : "#"}
                download={opt.filename}
                className={`text-xs font-medium px-4 py-2 rounded-md flex-shrink-0 transition-colors ${
                  opt.available
                    ? "bg-civic-green text-white hover:bg-civic-green-light"
                    : "bg-gray-200 text-gray-400 cursor-not-allowed pointer-events-none"
                }`}
              >
                Download
              </a>
            </div>
          </div>
        ))}
      </div>

      {/* Stats summary inline */}
      {stats && stats.total > 0 && (
        <div className="bg-gray-50 rounded-lg border border-gray-200 p-4">
          <div className="text-xs text-gray-500 uppercase tracking-wide font-medium mb-2">Current Status</div>
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
