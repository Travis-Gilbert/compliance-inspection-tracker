"use client";

import { useEffect, useMemo, useState } from "react";
import InlineNotice from "@/components/InlineNotice";
import {
  createWorkflowComm,
  createWorkflowLetterPacket,
  getMediaUrl,
  getWorkflowComms,
  getWorkflowDocuments,
  getWorkflowTemplatePreview,
  getWorkflowTiming,
} from "@/lib/api";
import type {
  WorkflowCommunication,
  WorkflowDocument,
  WorkflowTemplatePreview,
  WorkflowTiming,
} from "@/lib/types";

interface OutreachLogProps {
  propertyId: number;
  onWorkflowChanged?: () => void;
}

const ACTION_LABELS: Record<string, string> = {
  ATTEMPT_1: "First Attempt",
  ATTEMPT_2: "Second Attempt",
  WARNING: "Warning",
  DEFAULT_NOTICE: "Default Notice",
};

function defaultActionForTiming(timing: WorkflowTiming | null): string {
  if (!timing) {
    return "";
  }
  if (timing.error) {
    return "";
  }
  if (timing.actionAlreadySent) {
    return timing.nextAction || "";
  }
  if (timing.currentAction && timing.currentAction !== "NOT_DUE_YET") {
    return timing.currentAction;
  }
  return timing.nextAction || "";
}

export default function OutreachLog({ propertyId, onWorkflowChanged }: OutreachLogProps) {
  const [timing, setTiming] = useState<WorkflowTiming | null>(null);
  const [preview, setPreview] = useState<WorkflowTemplatePreview | null>(null);
  const [comms, setComms] = useState<WorkflowCommunication[]>([]);
  const [documents, setDocuments] = useState<WorkflowDocument[]>([]);
  const [selectedAction, setSelectedAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generatingPacket, setGeneratingPacket] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "info" | "success" | "warning" | "error";
    title: string;
    message: string;
  } | null>(null);
  const [latestPacketUrl, setLatestPacketUrl] = useState("");

  const loadWorkflow = async () => {
    setLoading(true);
    try {
      const [timingData, commData, documentData] = await Promise.all([
        getWorkflowTiming(propertyId).catch(() => null),
        getWorkflowComms(propertyId).catch(() => []),
        getWorkflowDocuments(propertyId).catch(() => []),
      ]);
      setTiming(timingData);
      setComms(commData);
      setDocuments(documentData);
      setLatestPacketUrl(
        documentData.find((item: WorkflowDocument) => item.category === "mail_packet")?.storage_url || "",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWorkflow();
  }, [propertyId]);

  useEffect(() => {
    const nextAction = defaultActionForTiming(timing);
    setSelectedAction(nextAction);
  }, [timing?.currentAction, timing?.nextAction, timing?.actionAlreadySent, timing?.error]);

  useEffect(() => {
    if (!selectedAction) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    getWorkflowTemplatePreview(propertyId, { action: selectedAction })
      .then((result: WorkflowTemplatePreview) => {
        if (!cancelled) {
          setPreview(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPreview(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [propertyId, selectedAction]);

  const hasEmail = Boolean(preview?.recipientEmail || timing?.buyerEmail);
  const previewLabel = ACTION_LABELS[selectedAction] || selectedAction || "Workflow Action";
  const activeReasons = timing?.reasons || [];

  const documentGroups = useMemo(() => {
    return documents.reduce<Record<string, WorkflowDocument[]>>((groups, document) => {
      if (!groups[document.category]) {
        groups[document.category] = [];
      }
      groups[document.category].push(document);
      return groups;
    }, {});
  }, [documents]);

  const handleLogCommunication = async (status: "draft" | "sent", method: "email" | "mail") => {
    if (!selectedAction) {
      return;
    }
    setSaving(true);
    setNotice(null);
    try {
      const result: WorkflowCommunication = await createWorkflowComm(propertyId, {
        method,
        direction: "outbound",
        action: selectedAction,
        status,
        template_slug: preview?.template.slug,
        subject: preview?.subject || "",
        body: preview?.body || "",
      });
      setNotice({
        tone: "success",
        title: status === "sent" ? "Workflow communication logged" : "Draft saved",
        message:
          status === "sent"
            ? `${ACTION_LABELS[selectedAction] || selectedAction} recorded for the property workflow.`
            : "Template draft saved to the communication log.",
      });
      await loadWorkflow();
      const packetDocument = result.documents?.find((document) => document.category === "mail_packet");
      if (packetDocument?.storage_url) {
        setLatestPacketUrl(packetDocument.storage_url);
      }
      await onWorkflowChanged?.();
    } catch (error: unknown) {
      setNotice({
        tone: "error",
        title: "Workflow update failed",
        message: (error as Error).message || "The communication could not be recorded.",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleGeneratePacket = async () => {
    setGeneratingPacket(true);
    setNotice(null);
    try {
      const response = await createWorkflowLetterPacket({
        property_ids: [propertyId],
        action: selectedAction || undefined,
      });
      setLatestPacketUrl(response.batch_document.storage_url);
      setNotice({
        tone: "success",
        title: "Mail packet generated",
        message: "A printable packet and audit manifest were stored for this property.",
      });
      await loadWorkflow();
      await onWorkflowChanged?.();
    } catch (error: unknown) {
      setNotice({
        tone: "error",
        title: "Packet generation failed",
        message: (error as Error).message || "The mail packet could not be created.",
      });
    } finally {
      setGeneratingPacket(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Compliance Workflow
          </div>
          <div className="mt-1 text-sm text-gray-600">
            Timing, outreach proof, and generated packet artifacts for this property.
          </div>
        </div>
        {selectedAction && (
          <span className="rounded bg-civic-blue-pale px-2 py-1 text-xs font-medium text-civic-blue">
            {previewLabel}
          </span>
        )}
      </div>

      {notice && <InlineNotice tone={notice.tone} title={notice.title} message={notice.message} className="mb-4" />}

      {loading ? (
        <div className="text-xs text-gray-400">Loading workflow…</div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="grid gap-3 md:grid-cols-4">
              <div>
                <div className="text-[11px] uppercase tracking-wide text-gray-400">Current action</div>
                <div className="mt-1 text-sm font-semibold text-gray-900">
                  {timing?.error
                    ? "Manual review"
                    : ACTION_LABELS[timing?.currentAction || ""] || timing?.currentAction || "Not due yet"}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-gray-400">Due date</div>
                <div className="mt-1 text-sm text-gray-700">{timing?.dueDate || "Not available"}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-gray-400">Days overdue</div>
                <div className="mt-1 text-sm text-gray-700">{timing?.daysOverdue || 0}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-gray-400">Contact path</div>
                <div className="mt-1 text-sm text-gray-700">{hasEmail ? "Email workflow" : "Manual mail packet"}</div>
              </div>
            </div>
            {activeReasons.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs text-gray-600">
                {activeReasons.map((reason) => (
                  <li key={reason}>• {reason}</li>
                ))}
              </ul>
            )}
          </div>

          {selectedAction ? (
            <div className="rounded-lg border border-gray-200 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-gray-500">Generated message</div>
                  <div className="mt-1 text-sm text-gray-600">
                    {hasEmail
                      ? "Review the generated outreach text before logging it."
                      : "No buyer email is on file. Generate a printable mail packet instead."}
                  </div>
                </div>
                {!hasEmail && latestPacketUrl && (
                  <a
                    href={getMediaUrl(latestPacketUrl)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded border border-civic-blue px-3 py-1.5 text-xs font-medium text-civic-blue hover:bg-civic-blue-pale"
                  >
                    Open latest packet
                  </a>
                )}
              </div>

              {preview ? (
                <div className="mt-3 space-y-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-gray-400">Subject</div>
                    <div className="mt-1 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-800">
                      {preview.subject}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-gray-400">Body</div>
                    <div className="mt-1 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-sm leading-6 text-gray-800 whitespace-pre-wrap">
                      {preview.body}
                    </div>
                  </div>
                  {preview.missingVariables.length > 0 && (
                    <InlineNotice
                      tone="warning"
                      title="Template variables need review"
                      message={`Missing variables: ${preview.missingVariables.join(", ")}`}
                    />
                  )}
                  <div className="flex flex-wrap gap-2">
                    {hasEmail ? (
                      <>
                        <button
                          type="button"
                          onClick={() => handleLogCommunication("draft", "email")}
                          disabled={saving}
                          className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {saving ? "Saving…" : "Save Draft"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleLogCommunication("sent", "email")}
                          disabled={saving}
                          className="rounded bg-civic-green px-3 py-1.5 text-xs font-medium text-white hover:bg-civic-green-light disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {saving ? "Saving…" : "Log Sent"}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={handleGeneratePacket}
                          disabled={generatingPacket}
                          className="rounded bg-civic-blue px-3 py-1.5 text-xs font-medium text-white hover:bg-civic-blue-light disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {generatingPacket ? "Generating…" : "Generate Mail Packet"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleLogCommunication("sent", "mail")}
                          disabled={saving}
                          className="rounded border border-civic-green px-3 py-1.5 text-xs font-medium text-civic-green hover:bg-civic-green-pale disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {saving ? "Saving…" : "Log Mail Sent"}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ) : (
                <div className="mt-3 text-xs text-gray-400">
                  No workflow template preview is available for the current action.
                </div>
              )}
            </div>
          ) : (
            <InlineNotice
              tone="info"
              title="No workflow action selected"
              message="This property does not currently expose a workflow action that can be drafted or mailed."
            />
          )}

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-gray-200 p-3">
              <div className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">
                Workflow Communications ({comms.length})
              </div>
              {comms.length === 0 ? (
                <div className="text-xs text-gray-400">No workflow communications recorded yet.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-100 text-left text-gray-500">
                        <th className="pb-2 pr-3 font-medium">Date</th>
                        <th className="pb-2 pr-3 font-medium">Method</th>
                        <th className="pb-2 pr-3 font-medium">Action</th>
                        <th className="pb-2 pr-3 font-medium">Status</th>
                        <th className="pb-2 font-medium">Subject</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comms.map((comm) => (
                        <tr key={comm.id} className="border-b border-gray-50 align-top">
                          <td className="py-2 pr-3 text-gray-700">{comm.date_sent || "Draft"}</td>
                          <td className="py-2 pr-3 capitalize text-gray-700">{comm.method}</td>
                          <td className="py-2 pr-3 text-gray-700">{ACTION_LABELS[comm.action] || comm.action || "Manual"}</td>
                          <td className="py-2 pr-3 text-gray-700">{comm.status}</td>
                          <td className="py-2 text-gray-700">{comm.subject || "No subject"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="rounded-lg border border-gray-200 p-3">
              <div className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">
                Generated Documents ({documents.length})
              </div>
              {documents.length === 0 ? (
                <div className="text-xs text-gray-400">No stored proof artifacts or packets yet.</div>
              ) : (
                <div className="space-y-3">
                  {Object.entries(documentGroups).map(([category, items]) => (
                    <div key={category}>
                      <div className="text-[11px] uppercase tracking-wide text-gray-400">{category.replaceAll("_", " ")}</div>
                      <div className="mt-1 space-y-1.5">
                        {items.map((document) => (
                          <a
                            key={document.id}
                            href={getMediaUrl(document.storage_url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-between rounded border border-gray-200 px-3 py-2 text-xs text-gray-700 hover:bg-gray-50"
                          >
                            <span className="min-w-0 truncate pr-3">{document.filename}</span>
                            <span className="shrink-0 text-gray-400">
                              {document.created_at ? new Date(document.created_at).toLocaleDateString() : ""}
                            </span>
                          </a>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
