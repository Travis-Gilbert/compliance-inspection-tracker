import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  getImageryStatus,
  getMapProperties,
  getStats,
  runPipelineAll,
  runPipelineStream,
} from "../utils/api";
import {
  DETECTION_LABELS,
  FINDINGS,
  REVIEW_FAST_LANES,
} from "../utils/constants";
import InlineNotice from "../components/InlineNotice";
import ManagementCoverageMap from "../components/ManagementCoverageMap";
import { DashboardSkeleton } from "../components/LoadingSkeleton";

const STEP_LABELS = {
  geocode: "Geocoding addresses",
  imagery: "Fetching imagery",
  detection: "Running detection",
};

function PipelineProgress({ events }) {
  if (!events.length) {
    return null;
  }

  const steps = ["geocode", "imagery", "detection"];
  const stepState = {};
  let grandTotals = null;
  let grandProcessed = 0;

  for (const event of events) {
    if (event.step === "init" && event.grand_totals) {
      grandTotals = event.grand_totals;
    }
    if (event.step && !["complete", "error", "init", "cycle"].includes(event.step)) {
      stepState[event.step] = event;
    }
    if (event.grand_processed != null) {
      grandProcessed = event.grand_processed;
    }
  }

  const completeEvent = [...events].reverse().find((event) => event.step === "complete");
  const errorEvent = [...events].reverse().find((event) => event.step === "error");
  const grandTotal = grandTotals?.total || 0;
  const grandPct = grandTotal > 0 ? Math.round((grandProcessed / grandTotal) * 100) : 0;

  return (
    <div className="mt-4 space-y-3">
      {errorEvent?.message && (
        <InlineNotice
          tone="error"
          title="Pipeline failed"
          message={errorEvent.message}
        />
      )}

      {grandTotals && (
        <div className="mb-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-800">Overall progress</span>
            <span className="text-xs font-medium text-civic-green">{grandPct}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-gray-100">
            <div
              className="h-2 rounded-full bg-civic-green transition-all duration-300"
              style={{ width: `${grandPct}%` }}
            />
          </div>
          <div className="mt-1 text-xs text-gray-500">
            {grandProcessed} / {grandTotal} properties processed
          </div>
        </div>
      )}

      {steps.map((step) => {
        const state = stepState[step];
        if (!state) {
          return null;
        }

        const isDone = state.status === "done";
        const isProgress = ["started", "progress", "batch_complete"].includes(state.status);
        const total = state.total ?? state.attempted ?? 0;
        const current = state.current ?? 0;
        const pct = total > 0
          ? Math.round(((isDone ? state.processed || total : current) / total) * 100)
          : 0;

        return (
          <div key={step} className="flex items-center gap-3">
            <div className="flex h-4 w-4 shrink-0 items-center justify-center">
              {isDone ? (
                <svg className="h-4 w-4 text-civic-green" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              ) : (
                <div className="mt-0.5 h-3 w-3 rounded-full border-2 border-civic-green border-t-transparent animate-spin" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-700">{STEP_LABELS[step]}</span>
                <span className="text-xs text-gray-500">
                  {isDone ? `${state.processed || 0}/${total} done` : `${current}/${total}`}
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-gray-100">
                <div
                  className="h-1.5 rounded-full bg-civic-green transition-all duration-300"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>
        );
      })}

      {completeEvent && !errorEvent && (
        <div className="pt-1 text-xs font-medium text-civic-green">
          {completeEvent.message || "Pipeline complete"}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [apiStatus, setApiStatus] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [mapProperties, setMapProperties] = useState([]);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapError, setMapError] = useState("");
  const [processing, setProcessing] = useState(false);
  const [processingMode, setProcessingMode] = useState("batch");
  const [pipelineEvents, setPipelineEvents] = useState([]);
  const [pipelineNotice, setPipelineNotice] = useState(null);
  const cancelRef = useRef(null);

  const loadData = async () => {
    setLoadError("");
    setMapError("");
    setMapLoading(true);
    const [statsResult, statusResult, mapResult] = await Promise.allSettled([
      getStats(),
      getImageryStatus(),
      getMapProperties(),
    ]);

    if (statsResult.status === "fulfilled") {
      setStats(statsResult.value);
    } else {
      setLoadError(statsResult.reason?.message || "Could not load dashboard data.");
    }

    if (statusResult.status === "fulfilled") {
      setApiStatus(statusResult.value);
    } else {
      setApiStatus(null);
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

  const handleProcess = async ({ processAll = false } = {}) => {
    setProcessing(true);
    setProcessingMode(processAll ? "all" : "batch");
    setPipelineEvents([]);
    setPipelineNotice(null);

    const runner = processAll
      ? runPipelineAll(100, (event) => setPipelineEvents((prev) => [...prev, event]))
      : runPipelineStream(
          25,
          (event) => setPipelineEvents((prev) => [...prev, event]),
          { processAll: false }
        );

    cancelRef.current = runner.cancel;

    try {
      await runner.promise;
      await loadData();
      setPipelineNotice({
        tone: "success",
        title: processAll ? "All remaining properties processed" : "Batch complete",
        message: processAll
          ? "The pipeline ran through every remaining eligible property."
          : "The next batch finished processing.",
      });
    } catch (error) {
      if (error.name === "AbortError") {
        setPipelineNotice({
          tone: "warning",
          title: "Processing stopped",
          message: "The current pipeline run was stopped before completion.",
        });
      } else {
        setPipelineEvents((prev) => [...prev, { step: "error", message: error.message }]);
        setPipelineNotice({
          tone: "error",
          title: "Processing failed",
          message: error.message,
        });
      }
    } finally {
      setProcessing(false);
      cancelRef.current = null;
    }
  };

  const handleStop = () => {
    if (cancelRef.current) {
      cancelRef.current();
    }
  };

  if (!stats && !loadError) {
    return <DashboardSkeleton />;
  }

  if (!stats && loadError) {
    return (
      <InlineNotice
        tone="error"
        title="Dashboard unavailable"
        message={loadError}
        actionLabel="Retry"
        onAction={loadData}
      />
    );
  }

  const pct = stats?.percent_reviewed || 0;
  const laneCounts = {
    unreviewed: stats.unreviewed,
    likely_demolished: stats.unreviewed_by_detection?.likely_demolished || 0,
    likely_vacant: stats.unreviewed_by_detection?.likely_vacant || 0,
    needs_inspection: stats.needs_inspection,
    unprocessed: stats.unreviewed_by_detection?.unprocessed || 0,
  };

  return (
    <div className="space-y-6">
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

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-heading font-semibold text-gray-900">Review Progress</span>
          <span className="text-sm font-medium text-civic-green">{pct}%</span>
        </div>
        <div className="h-3 w-full rounded-full bg-gray-100">
          <div
            className="h-3 rounded-full bg-civic-green transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between text-xs text-gray-500">
          <span>{stats.reviewed} reviewed</span>
          <span>{stats.unreviewed} remaining</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: "Total Properties", value: stats.total, accent: "border-l-gray-400" },
          { label: "Resolved (Desk)", value: stats.resolved, accent: "border-l-civic-green" },
          { label: "Needs Inspection", value: stats.needs_inspection, accent: "border-l-orange-500" },
          { label: "Unreviewed", value: stats.unreviewed, accent: "border-l-gray-300" },
        ].map((card) => (
          <div
            key={card.label}
            className={`rounded-lg border border-gray-200 border-l-4 ${card.accent} bg-white p-4`}
          >
            <div className="text-xs uppercase tracking-wide text-gray-500">{card.label}</div>
            <div className="mt-1 font-heading text-2xl font-bold text-gray-900">{card.value}</div>
          </div>
        ))}
      </div>

      <ManagementCoverageMap
        properties={mapProperties}
        totalProperties={stats.total}
        loading={mapLoading}
        error={mapError}
      />

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 className="font-heading font-semibold text-gray-900">Fast Review Lanes</h3>
            <p className="mt-1 text-sm text-gray-600">
              Jump straight into the queue slice most likely to move the work forward.
            </p>
          </div>
          <Link
            to="/review"
            className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            Open Full Queue
          </Link>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {REVIEW_FAST_LANES.map((lane) => (
            <Link
              key={lane.id}
              to={`/review?${new URLSearchParams(lane.params).toString()}`}
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

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-2 font-heading font-semibold text-gray-900">Processing Pipeline</h3>
        <p className="mb-4 text-sm text-gray-600">
          Import properties, then run the pipeline to geocode addresses, fetch Street View and satellite imagery, and run smart detection. Properties flagged as likely vacant or demolished will sort to the top of your review queue.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => handleProcess({ processAll: false })}
            disabled={processing || stats.total === 0}
            className={`rounded-md px-5 py-2 text-sm font-medium transition-colors ${
              processing || stats.total === 0
                ? "cursor-not-allowed bg-gray-200 text-gray-500"
                : "bg-civic-green text-white hover:bg-civic-green-light"
            }`}
          >
            {processing && processingMode === "batch" ? "Processing..." : "Run Next Batch"}
          </button>

          <button
            onClick={() => handleProcess({ processAll: true })}
            disabled={processing || stats.total === 0}
            className={`rounded-md px-5 py-2 text-sm font-medium transition-colors ${
              processing || stats.total === 0
                ? "cursor-not-allowed bg-gray-200 text-gray-500"
                : "bg-civic-blue text-white hover:bg-civic-blue-light"
            }`}
          >
            {processing && processingMode === "all" ? "Processing..." : "Process All Remaining"}
          </button>

          {processing && (
            <button
              onClick={handleStop}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
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

        {pipelineNotice && (
          <InlineNotice
            tone={pipelineNotice.tone}
            title={pipelineNotice.title}
            message={pipelineNotice.message}
            className="mt-4"
          />
        )}

        <PipelineProgress events={pipelineEvents} />
      </div>

      {Object.keys(stats.by_detection || {}).length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="mb-3 font-heading font-semibold text-gray-900">Smart Detection Results</h3>
          <div className="space-y-2">
            {Object.entries(stats.by_detection).map(([label, count]) => {
              const meta = DETECTION_LABELS[label] || { label, color: "#999", bg: "#f5f5f5" };
              return (
                <div key={label} className="flex items-center gap-3">
                  <span
                    className="rounded px-2 py-1 text-xs font-medium"
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

      {Object.keys(stats.by_finding || {}).length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="mb-3 font-heading font-semibold text-gray-900">Review Findings</h3>
          <div className="space-y-2">
            {Object.entries(stats.by_finding).map(([finding, count]) => {
              const meta = FINDINGS.find((item) => item.value === finding) || {
                label: finding,
                color: "#999",
                bg: "#f5f5f5",
              };
              return (
                <div key={finding} className="flex items-center gap-3">
                  <span
                    className="rounded px-2 py-1 text-xs font-medium"
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
