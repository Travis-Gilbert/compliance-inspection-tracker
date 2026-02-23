import { useState, useEffect } from "react";
import { getStats, getImageryStatus, runPipeline } from "../utils/api";
import { FINDINGS, DETECTION_LABELS } from "../utils/constants";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [apiStatus, setApiStatus] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [pipelineResult, setPipelineResult] = useState(null);

  const loadData = async () => {
    try {
      const [s, a] = await Promise.all([getStats(), getImageryStatus()]);
      setStats(s);
      setApiStatus(a);
    } catch (e) {
      console.error("Failed to load dashboard:", e);
    }
  };

  useEffect(() => { loadData(); }, []);

  const handleProcess = async () => {
    setProcessing(true);
    setPipelineResult(null);
    try {
      const result = await runPipeline(25);
      setPipelineResult(result);
      await loadData();
    } catch (e) {
      setPipelineResult({ error: e.message });
    }
    setProcessing(false);
  };

  if (!stats) return <div className="text-gray-500 py-8">Loading...</div>;

  const pct = stats.percent_reviewed || 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Dashboard</h2>
        <p className="text-sm text-gray-500 mt-1">
          Compliance inspection progress overview
        </p>
      </div>

      {/* Progress bar */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <span className="font-heading font-semibold text-gray-900">Review Progress</span>
          <span className="text-sm font-medium text-civic-green">{pct}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-3">
          <div
            className="bg-civic-green rounded-full h-3 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-500">
          <span>{stats.reviewed} reviewed</span>
          <span>{stats.unreviewed} remaining</span>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Total Properties", value: stats.total, accent: "border-l-gray-400" },
          { label: "Resolved (Desk)", value: stats.resolved, accent: "border-l-civic-green" },
          { label: "Needs Inspection", value: stats.needs_inspection, accent: "border-l-orange-500" },
          { label: "Unreviewed", value: stats.unreviewed, accent: "border-l-gray-300" },
        ].map(card => (
          <div key={card.label} className={`bg-white rounded-lg border border-gray-200 border-l-4 ${card.accent} p-4`}>
            <div className="text-xs text-gray-500 uppercase tracking-wide">{card.label}</div>
            <div className="font-heading text-2xl font-bold text-gray-900 mt-1">{card.value}</div>
          </div>
        ))}
      </div>

      {/* Processing pipeline */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h3 className="font-heading font-semibold text-gray-900 mb-2">Processing Pipeline</h3>
        <p className="text-sm text-gray-600 mb-4">
          Import properties, then run the pipeline to geocode addresses, fetch Street View and satellite imagery, and run smart detection. Properties flagged as likely vacant or demolished will sort to the top of your review queue.
        </p>
        <div className="flex items-center gap-4 flex-wrap">
          <button
            onClick={handleProcess}
            disabled={processing || stats.total === 0}
            className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
              processing || stats.total === 0
                ? "bg-gray-200 text-gray-500 cursor-not-allowed"
                : "bg-civic-green text-white hover:bg-civic-green-light"
            }`}
          >
            {processing ? "Processing..." : "Run Pipeline (next 25)"}
          </button>

          {apiStatus && (
            <span className={`text-xs ${apiStatus.configured ? "text-civic-green" : "text-orange-500"}`}>
              {apiStatus.configured ? "Google Maps API configured" : "Google Maps API key not set"}
            </span>
          )}
        </div>

        {pipelineResult && (
          <pre className="mt-3 text-xs bg-gray-50 rounded p-3 overflow-auto font-mono text-gray-700">
            {JSON.stringify(pipelineResult, null, 2)}
          </pre>
        )}
      </div>

      {/* Detection breakdown */}
      {Object.keys(stats.by_detection || {}).length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h3 className="font-heading font-semibold text-gray-900 mb-3">Smart Detection Results</h3>
          <div className="space-y-2">
            {Object.entries(stats.by_detection).map(([label, count]) => {
              const meta = DETECTION_LABELS[label] || { label, color: "#999", bg: "#f5f5f5" };
              return (
                <div key={label} className="flex items-center gap-3">
                  <span
                    className="text-xs font-medium px-2 py-1 rounded"
                    style={{ color: meta.color, background: meta.bg }}
                  >
                    {meta.label}
                  </span>
                  <span className="text-sm text-gray-700">{count} properties</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Findings breakdown */}
      {Object.keys(stats.by_finding || {}).length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h3 className="font-heading font-semibold text-gray-900 mb-3">Review Findings</h3>
          <div className="space-y-2">
            {Object.entries(stats.by_finding).map(([finding, count]) => {
              const meta = FINDINGS.find(f => f.value === finding) || { label: finding, color: "#999", bg: "#f5f5f5" };
              return (
                <div key={finding} className="flex items-center gap-3">
                  <span
                    className="text-xs font-medium px-2 py-1 rounded"
                    style={{ color: meta.color, background: meta.bg }}
                  >
                    {meta.label}
                  </span>
                  <span className="text-sm text-gray-700">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
