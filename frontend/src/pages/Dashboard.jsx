import { useState, useEffect, useRef } from "react";
import { getStats, getImageryStatus, runPipelineStream } from "../utils/api";
import { FINDINGS, DETECTION_LABELS } from "../utils/constants";
import { DashboardSkeleton } from "../components/LoadingSkeleton";

const STEP_LABELS = {
  geocode: "Geocoding addresses",
  imagery: "Fetching imagery",
  detection: "Running detection",
};

function PipelineProgress({ events }) {
  if (!events.length) return null;

  const steps = ["geocode", "imagery", "detection"];
  const stepState = {};
  let grandTotals = null;
  let grandProcessed = 0;

  for (const e of events) {
    if (e.step === "init" && e.grand_totals) {
      grandTotals = e.grand_totals;
    }
    if (e.step && e.step !== "complete" && e.step !== "init") {
      stepState[e.step] = e;
    }
    if (e.grand_processed != null) {
      grandProcessed = e.grand_processed;
    }
  }
  const complete = events.some(e => e.step === "complete");

  const grandTotal = grandTotals?.total || 0;
  const grandPct = grandTotal > 0 ? Math.round((grandProcessed / grandTotal) * 100) : 0;

  return (
    <div className="mt-4 space-y-2">
      {/* Grand total progress bar (shown for process-all) */}
      {grandTotals && (
        <div className="mb-3 pb-3 border-b border-gray-100">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-gray-800">Overall progress</span>
            <span className="text-xs font-medium text-civic-green">{grandPct}%</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div
              className="bg-civic-green rounded-full h-2 transition-all duration-300"
              style={{ width: `${grandPct}%` }}
            />
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {grandProcessed} / {grandTotal} properties processed
          </div>
        </div>
      )}

      {steps.map(step => {
        const state = stepState[step];
        if (!state) return null;

        const isDone = state.status === "done";
        const isProgress = state.status === "progress" || state.status === "batch_complete";
        const total = state.total ?? state.attempted ?? 0;
        const pct = isProgress && state.total > 0
          ? Math.round((state.current / state.total) * 100)
          : isDone && total > 0 ? 100 : 0;

        return (
          <div key={step} className="flex items-center gap-3">
            <div className="w-4 h-4 flex-shrink-0">
              {isDone ? (
                <svg className="w-4 h-4 text-civic-green" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              ) : (
                <div className="w-3 h-3 border-2 border-civic-green border-t-transparent rounded-full animate-spin mt-0.5" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-700">
                  {STEP_LABELS[step]}
                </span>
                <span className="text-xs text-gray-500">
                  {isDone
                    ? `${state.processed || 0}/${total} done`
                    : isProgress
                      ? `${state.current}/${state.total}`
                      : `0/${total}`
                  }
                </span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-1.5 mt-1">
                <div
                  className="bg-civic-green rounded-full h-1.5 transition-all duration-300"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>
        );
      })}
      {complete && (
        <div className="text-xs text-civic-green font-medium pt-1">
          Pipeline complete {grandProcessed > 0 ? `(${grandProcessed} properties processed)` : ""}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [apiStatus, setApiStatus] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processingMode, setProcessingMode] = useState("batch");
  const [pipelineEvents, setPipelineEvents] = useState([]);
  const cancelRef = useRef(null);

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

  const handleProcess = async ({ processAll = false } = {}) => {
    setProcessing(true);
    setProcessingMode(processAll ? "all" : "batch");
    setPipelineEvents([]);

    const { promise, cancel } = runPipelineStream(
      25,
      (event) => {
        setPipelineEvents((prev) => [...prev, event]);
      },
      { processAll }
    );
    cancelRef.current = cancel;

    try {
      await promise;
      await loadData();
    } catch (e) {
      if (e.name !== "AbortError") {
        setPipelineEvents(prev => [...prev, { step: "error", message: e.message }]);
      }
    }
    setProcessing(false);
    cancelRef.current = null;
  };

  const handleStop = () => {
    if (cancelRef.current) {
      cancelRef.current();
      setPipelineEvents(prev => [...prev, { step: "complete", status: "done", message: "Stopped by user" }]);
    }
  };

  if (!stats) return <DashboardSkeleton />;

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
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={() => handleProcess({ processAll: false })}
            disabled={processing || stats.total === 0}
            className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
              processing || stats.total === 0
                ? "bg-gray-200 text-gray-500 cursor-not-allowed"
                : "bg-civic-green text-white hover:bg-civic-green-light"
            }`}
          >
            {processing && processingMode === "batch" ? "Processing..." : "Run Next Batch"}
          </button>

          <button
            onClick={() => handleProcess({ processAll: true })}
            disabled={processing || stats.total === 0}
            className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
              processing || stats.total === 0
                ? "bg-gray-200 text-gray-500 cursor-not-allowed"
                : "bg-civic-blue text-white hover:bg-civic-blue-light"
            }`}
          >
            {processing && processingMode === "all" ? "Processing..." : "Process All Remaining"}
          </button>

          {processing && (
            <button
              onClick={handleStop}
              className="px-4 py-2 rounded-md text-sm font-medium border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Stop
            </button>
          )}

          {apiStatus && (
            <span className={`text-xs ${apiStatus.configured ? "text-civic-green" : "text-orange-500"}`}>
              {apiStatus.configured ? "Google Maps API configured" : "Google Maps API key not set"}
            </span>
          )}
        </div>

        <PipelineProgress events={pipelineEvents} />
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
