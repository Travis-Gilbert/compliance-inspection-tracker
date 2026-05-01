"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  getImageryStatus,
  getStats,
  runPipelineAll,
  runPipelineStream,
} from "@/lib/api";
import { DETECTION_LABELS, FINDINGS } from "@/lib/constants";
import type { PipelineEvent, Stats } from "@/lib/types";
import InlineNotice from "@/components/InlineNotice";

const STEP_LABELS: Record<string, string> = {
  geocode: "Geocoding addresses",
  imagery: "Fetching imagery",
  detection: "Running detection",
};

function PipelineProgress({ events }: { events: PipelineEvent[] }) {
  if (!events.length) return null;

  const steps = ["geocode", "imagery", "detection"];
  const stepState: Record<string, PipelineEvent> = {};
  let grandTotals: { total: number } | null = null;
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

  const completeEvent = [...events].reverse().find((e) => e.step === "complete");
  const errorEvent = [...events].reverse().find((e) => e.step === "error");
  const grandTotal = grandTotals?.total || 0;
  const grandPct = grandTotal > 0 ? Math.round((grandProcessed / grandTotal) * 100) : 0;

  return (
    <div className="mt-4 space-y-3">
      {errorEvent?.message && (
        <InlineNotice tone="error" title="Pipeline failed" message={errorEvent.message} />
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
        if (!state) return null;

        const isDone = state.status === "done";
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

export default function ProcessingPage() {
  const searchParams = useSearchParams();
  const autostart = searchParams.get("autostart") === "true";

  const [stats, setStats] = useState<Stats | null>(null);
  const [apiStatus, setApiStatus] = useState<{ configured: boolean } | null>(null);
  const [loadError, setLoadError] = useState("");
  const [processing, setProcessing] = useState(false);
  const [processingMode, setProcessingMode] = useState("batch");
  const [pipelineEvents, setPipelineEvents] = useState<PipelineEvent[]>([]);
  const [pipelineNotice, setPipelineNotice] = useState<{
    tone: "info" | "success" | "warning" | "error";
    title: string;
    message: string;
  } | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const autostartedRef = useRef(false);

  const loadData = async () => {
    setLoadError("");
    const [statsResult, statusResult] = await Promise.allSettled([
      getStats(),
      getImageryStatus(),
    ]);

    if (statsResult.status === "fulfilled") {
      setStats(statsResult.value);
    } else {
      setLoadError(statsResult.reason?.message || "Could not load data.");
    }

    if (statusResult.status === "fulfilled") {
      setApiStatus(statusResult.value);
    }
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
      ? runPipelineAll(100, (event) => setPipelineEvents((prev) => [...prev, event as unknown as PipelineEvent]))
      : runPipelineStream(
          25,
          (event) => setPipelineEvents((prev) => [...prev, event as unknown as PipelineEvent]),
          { processAll: false },
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
    } catch (error: unknown) {
      const err = error as Error;
      if (err.name === "AbortError") {
        setPipelineNotice({
          tone: "warning",
          title: "Processing stopped",
          message: "The current pipeline run was stopped before completion.",
        });
      } else {
        setPipelineEvents((prev) => [...prev, { step: "error", message: err.message }]);
        setPipelineNotice({
          tone: "error",
          title: "Processing failed",
          message: err.message,
        });
      }
    } finally {
      setProcessing(false);
      cancelRef.current = null;
    }
  };

  // Auto-start if coming from import page
  useEffect(() => {
    if (autostart && stats && !autostartedRef.current && stats.total > 0) {
      autostartedRef.current = true;
      handleProcess({ processAll: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autostart, stats]);

  const handleStop = () => {
    cancelRef.current?.();
  };

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-6">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Processing Pipeline</h2>
        <p className="mt-1 text-sm text-gray-500">
          Geocode addresses, fetch Street View and satellite imagery, and run vacancy detection.
        </p>
      </div>

      {loadError && (
        <InlineNotice
          tone="error"
          title="Data unavailable"
          message={loadError}
          actionLabel="Retry"
          onAction={loadData}
        />
      )}

      {/* Pipeline controls */}
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-2 font-heading font-semibold text-gray-900">Run Pipeline</h3>
        <p className="mb-4 text-sm text-gray-600">
          Import properties first, then run the pipeline to geocode, fetch imagery, and detect vacancy signals.
          Properties flagged as likely vacant or demolished will sort to the top of the review queue.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => handleProcess({ processAll: false })}
            disabled={processing || !stats || stats.total === 0}
            className={`rounded-md px-5 py-2 text-sm font-medium transition-colors ${
              processing || !stats || stats.total === 0
                ? "cursor-not-allowed bg-gray-200 text-gray-500"
                : "bg-civic-green text-white hover:bg-civic-green-light"
            }`}
          >
            {processing && processingMode === "batch" ? "Processing…" : "Run Next Batch"}
          </button>

          <button
            onClick={() => handleProcess({ processAll: true })}
            disabled={processing || !stats || stats.total === 0}
            className={`rounded-md px-5 py-2 text-sm font-medium transition-colors ${
              processing || !stats || stats.total === 0
                ? "cursor-not-allowed bg-gray-200 text-gray-500"
                : "bg-civic-blue text-white hover:bg-civic-blue-light"
            }`}
          >
            {processing && processingMode === "all" ? "Processing…" : "Process All Remaining"}
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

      {/* Detection results */}
      {stats && Object.keys(stats.by_detection || {}).length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="mb-3 font-heading font-semibold text-gray-900">Detection Results</h3>
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

      {/* Review Findings */}
      {stats && Object.keys(stats.by_finding || {}).length > 0 && (
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

      {/* Current stats summary */}
      {stats && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Current Status</div>
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-6">
            <div>Total: <span className="font-medium">{stats.total}</span></div>
            <div>Photo Ready: <span className="font-medium text-civic-blue">{stats.imagery_fetched}</span></div>
            <div>System Triaged: <span className="font-medium text-civic-green">{stats.detection_ran}</span></div>
            <div>Manual Findings: <span className="font-medium">{stats.reviewed}</span></div>
            <div>Resolved: <span className="font-medium text-civic-green">{stats.resolved}</span></div>
            <div>Needs Visit: <span className="font-medium text-orange-600">{stats.needs_inspection}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}
