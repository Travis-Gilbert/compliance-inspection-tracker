"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import InlineNotice from "@/components/InlineNotice";
import {
  createWorkflowLetterPacket,
  getMediaUrl,
  getWorkflowActionQueue,
} from "@/lib/api";
import type { WorkflowLetterPacketResponse, WorkflowQueueGroup, WorkflowQueueResponse } from "@/lib/types";

const HIGHLIGHT_ACTIONS = ["ATTEMPT_1", "ATTEMPT_2", "WARNING", "DEFAULT_NOTICE", "MISSING_EMAIL"];

export default function WorkflowPage() {
  const [queue, setQueue] = useState<WorkflowQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedMissingEmail, setSelectedMissingEmail] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<{
    tone: "info" | "success" | "warning" | "error";
    title: string;
    message: string;
  } | null>(null);
  const [packetResponse, setPacketResponse] = useState<WorkflowLetterPacketResponse | null>(null);
  const [generating, setGenerating] = useState(false);

  const loadQueue = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getWorkflowActionQueue();
      setQueue(result);
    } catch (err: unknown) {
      setError((err as Error).message || "The action queue could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, []);

  const visibleGroups = useMemo(() => {
    return (queue?.groups || []).filter((group) => group.count > 0);
  }, [queue]);

  const missingEmailGroup = useMemo(() => {
    return visibleGroups.find((group) => group.action === "MISSING_EMAIL") || null;
  }, [visibleGroups]);

  useEffect(() => {
    if (!missingEmailGroup) {
      setSelectedMissingEmail(new Set());
      return;
    }
    const allowedIds = new Set(missingEmailGroup.items.map((item) => item.propertyId));
    setSelectedMissingEmail((prev) => {
      const next = new Set<number>();
      prev.forEach((id) => {
        if (allowedIds.has(id)) {
          next.add(id);
        }
      });
      return next;
    });
  }, [missingEmailGroup]);

  const toggleMissingEmailSelection = (propertyId: number) => {
    setSelectedMissingEmail((prev) => {
      const next = new Set(prev);
      if (next.has(propertyId)) {
        next.delete(propertyId);
      } else {
        next.add(propertyId);
      }
      return next;
    });
  };

  const handleSelectAllMissingEmail = () => {
    if (!missingEmailGroup) {
      return;
    }
    const groupIds = missingEmailGroup.items.map((item) => item.propertyId);
    setSelectedMissingEmail((prev) => {
      if (prev.size === groupIds.length) {
        return new Set();
      }
      return new Set(groupIds);
    });
  };

  const handleGeneratePacket = async () => {
    if (selectedMissingEmail.size === 0) {
      return;
    }
    setGenerating(true);
    setNotice(null);
    try {
      const response = await createWorkflowLetterPacket({
        property_ids: [...selectedMissingEmail],
      });
      setPacketResponse(response);
      setNotice({
        tone: "success",
        title: "Mail packet generated",
        message: `${response.letters.length} printable letters and audit files were stored.`,
      });
      await loadQueue();
    } catch (err: unknown) {
      setNotice({
        tone: "error",
        title: "Packet generation failed",
        message: (err as Error).message || "The selected mail packet could not be generated.",
      });
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#fafaf5] px-4 py-6 md:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-civic-green">Workflow</div>
            <h1 className="mt-2 font-heading text-3xl font-bold text-gray-900">Action Queue</h1>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Grouped compliance actions, missing-email routing, and packet generation for staff follow-through.
            </p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600">
            <div>As of: <span className="font-medium text-gray-900">{queue?.asOf || "Loading…"}</span></div>
            <div className="mt-1">Open workflow items: <span className="font-medium text-gray-900">{queue?.totalItems || 0}</span></div>
          </div>
        </div>

        {notice && <InlineNotice tone={notice.tone} title={notice.title} message={notice.message} />}

        {packetResponse && (
          <InlineNotice
            tone="info"
            title="Latest packet artifacts"
            message="Open the batch packet or manifest, then print from the browser when the packet is ready."
            actionLabel="Open Batch Packet"
            onAction={() => window.open(getMediaUrl(packetResponse.batch_document.storage_url), "_blank", "noopener,noreferrer")}
          />
        )}

        {loading ? (
          <div className="rounded-xl border border-gray-200 bg-white px-6 py-10 text-sm text-gray-500">
            Loading workflow queue…
          </div>
        ) : error ? (
          <InlineNotice tone="error" title="Queue unavailable" message={error} />
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {HIGHLIGHT_ACTIONS.map((action) => {
                const group = queue?.groups.find((item) => item.action === action);
                return (
                  <div key={action} className="rounded-xl border border-gray-200 bg-white p-4">
                    <div className="text-[11px] uppercase tracking-wide text-gray-400">{group?.label || action}</div>
                    <div className="mt-3 text-3xl font-heading font-bold text-gray-900">{group?.count || 0}</div>
                  </div>
                );
              })}
            </div>

            {missingEmailGroup && (
              <section className="rounded-xl border border-orange-200 bg-orange-50/70 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-orange-600">Mail Packet Lane</div>
                    <div className="mt-1 text-sm text-orange-900">
                      {missingEmailGroup.count} due properties do not have a buyer email on file.
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={handleSelectAllMissingEmail}
                      className="rounded border border-orange-300 bg-white px-3 py-1.5 text-xs font-medium text-orange-800 hover:bg-orange-100"
                    >
                      {selectedMissingEmail.size === missingEmailGroup.items.length ? "Clear Selection" : "Select All"}
                    </button>
                    <button
                      type="button"
                      onClick={handleGeneratePacket}
                      disabled={selectedMissingEmail.size === 0 || generating}
                      className="rounded bg-civic-blue px-3 py-1.5 text-xs font-medium text-white hover:bg-civic-blue-light disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {generating ? "Generating…" : `Generate Packet (${selectedMissingEmail.size})`}
                    </button>
                    {packetResponse && (
                      <a
                        href={getMediaUrl(packetResponse.manifest_document.storage_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="rounded border border-civic-blue px-3 py-1.5 text-xs font-medium text-civic-blue hover:bg-civic-blue-pale"
                      >
                        Open Manifest
                      </a>
                    )}
                  </div>
                </div>
              </section>
            )}

            <div className="space-y-5">
              {visibleGroups.map((group: WorkflowQueueGroup) => (
                <section key={group.action} className="rounded-xl border border-gray-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3 border-b border-gray-100 pb-3">
                    <div>
                      <h2 className="font-heading text-xl font-bold text-gray-900">{group.label}</h2>
                      <div className="mt-1 text-sm text-gray-500">{group.count} open item{group.count === 1 ? "" : "s"}</div>
                    </div>
                  </div>

                  <div className="mt-4 space-y-3">
                    {group.items.map((item) => (
                      <article
                        key={`${group.action}-${item.propertyId}`}
                        className="rounded-lg border border-gray-200 px-4 py-3"
                      >
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-start gap-3">
                              {group.action === "MISSING_EMAIL" && (
                                <input
                                  type="checkbox"
                                  checked={selectedMissingEmail.has(item.propertyId)}
                                  onChange={() => toggleMissingEmailSelection(item.propertyId)}
                                  className="mt-1 h-4 w-4 rounded border-gray-300 text-civic-blue focus:ring-civic-blue"
                                  aria-label={`Select ${item.address} for packet generation`}
                                />
                              )}
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <h3 className="text-base font-semibold text-gray-900">{item.address}</h3>
                                  <span className="rounded bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">
                                    {item.program || "Program missing"}
                                  </span>
                                  {item.daysOverdue > 0 && (
                                    <span className="rounded bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700">
                                      {item.daysOverdue} day{item.daysOverdue === 1 ? "" : "s"} overdue
                                    </span>
                                  )}
                                </div>
                                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
                                  {item.buyerName && <span>Buyer: {item.buyerName}</span>}
                                  {item.parcelId && <span>Parcel: {item.parcelId}</span>}
                                  {item.dueDate && <span>Due: {item.dueDate}</span>}
                                  <span>Priority: {item.priority}</span>
                                </div>
                                {item.reasons.length > 0 && (
                                  <ul className="mt-2 space-y-1 text-sm text-gray-600">
                                    {item.reasons.map((reason) => (
                                      <li key={reason}>• {reason}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            <Link
                              href={`/property/${item.propertyId}`}
                              className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                            >
                              Open Property
                            </Link>
                            {group.action === "MISSING_EMAIL" && (
                              <button
                                type="button"
                                disabled={generating}
                                onClick={async () => {
                                  if (generating) {
                                    return;
                                  }
                                  setGenerating(true);
                                  setNotice(null);
                                  setSelectedMissingEmail(new Set([item.propertyId]));
                                  try {
                                    const response = await createWorkflowLetterPacket({ property_ids: [item.propertyId] });
                                    setPacketResponse(response);
                                    setNotice({
                                      tone: "success",
                                      title: "Single-property packet ready",
                                      message: `Stored a printable packet for ${item.address}.`,
                                    });
                                    await loadQueue();
                                  } catch (err: unknown) {
                                    setNotice({
                                      tone: "error",
                                      title: "Packet generation failed",
                                      message: (err as Error).message || "The packet could not be created.",
                                    });
                                  } finally {
                                    setGenerating(false);
                                  }
                                }}
                                className="rounded border border-civic-blue px-3 py-1.5 text-xs font-medium text-civic-blue hover:bg-civic-blue-pale disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                Packet
                              </button>
                            )}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
