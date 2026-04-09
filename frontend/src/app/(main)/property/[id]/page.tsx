"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { getProperty, updateProperty } from "@/lib/api";
import { FINDINGS } from "@/lib/constants";
import type { Property } from "@/lib/types";
import InlineNotice from "@/components/InlineNotice";
import { PropertyDetailSkeleton } from "@/components/LoadingSkeleton";
import PropertyDetailPanel from "@/components/review/PropertyDetailPanel";

export default function PropertyDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [property, setProperty] = useState<Property | null>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState<{
    tone: "info" | "success" | "warning" | "error";
    title: string;
    message: string;
  } | null>(null);

  // Read queue IDs from sessionStorage (set by ReviewQueue before navigating)
  const [queueIds, setQueueIds] = useState<number[]>([]);
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("review-queue-ids");
      if (stored) setQueueIds(JSON.parse(stored));
    } catch {
      // sessionStorage unavailable or parse error
    }
  }, []);

  const currentIndex = queueIds.indexOf(Number(id));
  const prevId = currentIndex > 0 ? queueIds[currentIndex - 1] : null;
  const nextId =
    currentIndex >= 0 && currentIndex < queueIds.length - 1
      ? queueIds[currentIndex + 1]
      : null;

  const navigateTo = useCallback(
    (targetId: number) => router.push(`/property/${targetId}`),
    [router],
  );

  useEffect(() => {
    let cancelled = false;
    getProperty(id)
      .then((result: Property) => {
        if (cancelled) return;
        setProperty(result);
        setNotes(result.notes || "");
        setLoadError("");
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setLoadError(error.message || "The property could not be loaded.");
      });
    return () => { cancelled = true; };
  }, [id]);

  const handleFinding = useCallback(
    async (finding: string) => {
      if (!property) return;
      const nextFinding = property.finding === finding ? "" : finding;
      setSaving(true);
      setNotice(null);
      try {
        const updated = await updateProperty(id, { finding: nextFinding, notes });
        setProperty(updated);
        setNotes(updated.notes || "");
        if (nextFinding && nextId) {
          navigateTo(nextId);
          return;
        }
        const label = FINDINGS.find((f) => f.value === finding)?.label || finding;
        setNotice({
          tone: "success",
          title: nextFinding ? `Saved: ${label}` : "Finding cleared",
          message: "",
        });
        setTimeout(() => setNotice(null), 2000);
      } catch (error: unknown) {
        setNotice({
          tone: "error",
          title: "Save failed",
          message: (error as Error).message || "The property status could not be updated.",
        });
      } finally {
        setSaving(false);
      }
    },
    [property, nextId, id, notes, navigateTo],
  );

  const handleSaveNotes = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const updated = await updateProperty(id, { notes });
      setProperty(updated);
      setNotes(updated.notes || "");
      setNotice({ tone: "success", title: "Notes saved", message: "" });
      setTimeout(() => setNotice(null), 2000);
    } catch (error: unknown) {
      setNotice({ tone: "error", title: "Save failed", message: (error as Error).message });
    } finally {
      setSaving(false);
    }
  };

  // Keyboard shortcuts for standalone page
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement).tagName;
      if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(tag) || saving) return;

      if (event.key === "ArrowLeft" && prevId) {
        event.preventDefault();
        navigateTo(prevId);
      } else if (event.key === "ArrowRight" && nextId) {
        event.preventDefault();
        navigateTo(nextId);
      } else if (event.key === "Escape") {
        router.push("/review");
      } else if (event.key >= "1" && event.key <= "6" && property) {
        const idx = parseInt(event.key, 10) - 1;
        if (idx < FINDINGS.length) handleFinding(FINDINGS[idx].value);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [nextId, prevId, property, saving, router, navigateTo, handleFinding]);

  if (!property && !loadError) return (
    <div className="max-w-4xl mx-auto p-4 md:p-6">
      <PropertyDetailSkeleton />
    </div>
  );

  if (!property && loadError) return (
    <div className="max-w-4xl mx-auto p-4 md:p-6">
      <InlineNotice
        tone="error"
        title="Property unavailable"
        message={loadError}
        actionLabel="Back to Queue"
        onAction={() => router.push("/review")}
      />
    </div>
  );

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-4">
      {/* Navigation bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => router.push("/review")}
          className="rounded border border-gray-200 px-2.5 py-1 text-xs text-gray-500 hover:bg-gray-50"
        >
          Back to Queue
        </button>
        {queueIds.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => prevId && navigateTo(prevId)}
              disabled={!prevId}
              className={`rounded border px-3 py-1.5 text-xs font-medium ${
                prevId ? "border-gray-200 text-gray-700 hover:bg-gray-50" : "cursor-not-allowed border-gray-100 text-gray-300"
              }`}
            >
              Prev
            </button>
            <span className="text-xs text-gray-400">{currentIndex + 1} / {queueIds.length}</span>
            <button
              onClick={() => nextId && navigateTo(nextId)}
              disabled={!nextId}
              className={`rounded border px-3 py-1.5 text-xs font-medium ${
                nextId ? "border-civic-green bg-civic-green text-white hover:bg-civic-green-light" : "cursor-not-allowed border-gray-100 text-gray-300"
              }`}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {notice && <InlineNotice tone={notice.tone} title={notice.title} message={notice.message} />}

      <PropertyDetailPanel
        property={property!}
        notes={notes}
        onNotesChange={setNotes}
        onSaveNotes={handleSaveNotes}
        onFindingAssign={handleFinding}
        saving={saving}
        notice={notice}
      />
    </div>
  );
}
