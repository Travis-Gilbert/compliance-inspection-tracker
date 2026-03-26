"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { getImageUrl, getProperty, updateProperty } from "@/lib/api";
import { DETECTION_LABELS, FINDINGS } from "@/lib/constants";
import InlineNotice from "@/components/InlineNotice";
import { PropertyDetailSkeleton } from "@/components/LoadingSkeleton";
import TaxInfoCard from "@/components/TaxInfoCard";
import OutreachLog from "@/components/OutreachLog";
import ComplianceStatusBadge from "@/components/ComplianceStatusBadge";

const AUTO_ADVANCE_KEY = "compliance-review-auto-advance";

export default function PropertyDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [property, setProperty] = useState<any>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState<{
    tone: "info" | "success" | "warning" | "error";
    title: string;
    message: string;
  } | null>(null);
  const [autoAdvance, setAutoAdvance] = useState(() => {
    if (typeof window === "undefined") {
      return true;
    }
    return window.localStorage.getItem(AUTO_ADVANCE_KEY) !== "false";
  });

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
    (targetId: number) => {
      router.push(`/property/${targetId}`);
    },
    [router],
  );

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        AUTO_ADVANCE_KEY,
        autoAdvance ? "true" : "false",
      );
    }
  }, [autoAdvance]);

  useEffect(() => {
    let cancelled = false;

    getProperty(id)
      .then((result: any) => {
        if (cancelled) {
          return;
        }
        setProperty(result);
        setNotes(result.notes || "");
        setLoadError("");
      })
      .catch((error: any) => {
        if (cancelled) {
          return;
        }
        setLoadError(error.message || "The property could not be loaded.");
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleFinding = useCallback(
    async (finding: string) => {
      if (!property) return;
      const nextFinding = property.finding === finding ? "" : finding;
      const shouldAdvance = Boolean(autoAdvance && nextId && nextFinding);
      setSaving(true);
      setNotice(null);
      try {
        const updated = await updateProperty(id, {
          finding: nextFinding,
          notes,
        });
        setProperty(updated);
        setNotes(updated.notes || "");
        if (shouldAdvance) {
          navigateTo(nextId!);
          return;
        }
        setNotice({
          tone: "success",
          title: "Finding saved",
          message: "The property status was updated.",
        });
      } catch (error: any) {
        setNotice({
          tone: "error",
          title: "Save failed",
          message:
            error.message || "The property status could not be updated.",
        });
      } finally {
        setSaving(false);
      }
    },
    [property, autoAdvance, nextId, id, notes, navigateTo],
  );

  const handleSaveNotes = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const updated = await updateProperty(id, { notes });
      setProperty(updated);
      setNotes(updated.notes || "");
      setNotice({
        tone: "success",
        title: "Notes saved",
        message: "Your notes were saved to this property.",
      });
    } catch (error: any) {
      setNotice({
        tone: "error",
        title: "Save failed",
        message: error.message || "The notes could not be saved.",
      });
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement).tagName;
      if (
        ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(tag) ||
        saving
      ) {
        return;
      }

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
        if (idx < FINDINGS.length) {
          handleFinding(FINDINGS[idx].value);
        }
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [nextId, prevId, property, saving, router, navigateTo, handleFinding]);

  if (!property && !loadError) {
    return <PropertyDetailSkeleton />;
  }

  if (!property && loadError) {
    return (
      <InlineNotice
        tone="error"
        title="Property unavailable"
        message={loadError}
        actionLabel="Back to Queue"
        onAction={() => router.push("/review")}
      />
    );
  }

  const detection = DETECTION_LABELS[property.detection_label];
  const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${encodeURIComponent(property.formatted_address || `${property.address}, Flint, MI`)}`;
  const propertyPortalUrl = `https://www.flintpropertyportal.com/search?q=${encodeURIComponent(property.address)}`;
  const googleMapsUrl = `https://www.google.com/maps/search/${encodeURIComponent(property.formatted_address || `${property.address}, Flint, MI`)}`;

  return (
    <div className="space-y-5">
      {/* Navigation bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          onClick={() => router.push("/review")}
          className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 hover:text-gray-700"
        >
          Back to Queue
        </button>
        {queueIds.length > 0 && (
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <button
              onClick={() => prevId && navigateTo(prevId)}
              disabled={!prevId}
              className={`rounded border px-3 py-1.5 text-xs font-medium transition-colors ${
                prevId
                  ? "border-gray-200 text-gray-700 hover:bg-gray-50"
                  : "cursor-not-allowed border-gray-100 text-gray-300"
              }`}
            >
              Prev
            </button>
            <span className="text-xs text-gray-400">
              {currentIndex + 1} / {queueIds.length}
            </span>
            <button
              onClick={() => nextId && navigateTo(nextId)}
              disabled={!nextId}
              className={`rounded border px-3 py-1.5 text-xs font-medium transition-colors ${
                nextId
                  ? "border-civic-green bg-civic-green text-white hover:bg-civic-green-light"
                  : "cursor-not-allowed border-gray-100 text-gray-300"
              }`}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Inline notice */}
      {notice && (
        <InlineNotice
          tone={notice.tone}
          title={notice.title}
          message={notice.message}
        />
      )}

      {/* Property header */}
      <div>
        <div className="flex items-center gap-3">
          <h2 className="font-heading text-xl font-bold text-gray-900">
            {property.address}
          </h2>
          {property.compliance_status &&
            property.compliance_status !== "unknown" && (
              <ComplianceStatusBadge status={property.compliance_status} />
            )}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-3 text-xs text-gray-500">
          {property.parcel_id && <span>Parcel: {property.parcel_id}</span>}
          {property.buyer_name && <span>Buyer: {property.buyer_name}</span>}
          {property.program && (
            <span className="rounded bg-civic-blue-pale px-1.5 py-0.5 font-medium text-civic-blue">
              {property.program}
            </span>
          )}
          {property.closing_date && (
            <span>Closed: {property.closing_date}</span>
          )}
          {property.commitment && (
            <span>Committed: {property.commitment}</span>
          )}
        </div>
      </div>

      {/* Detection alert bar */}
      {detection && property.detection_label !== "unprocessed" && (
        <div
          className="flex flex-col gap-1 rounded-lg border px-4 py-3 sm:flex-row sm:items-center sm:gap-3"
          style={{
            borderColor: `${detection.color}40`,
            background: detection.bg,
          }}
        >
          <span
            className="text-sm font-medium"
            style={{ color: detection.color }}
          >
            Smart Detection: {detection.label}
          </span>
          {property.detection_score != null && (
            <span className="text-xs text-gray-500">
              Score: {property.detection_score}
            </span>
          )}
        </div>
      )}

      {/* Street View and Satellite imagery grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
            <span className="text-xs font-medium text-gray-700">
              Street View
            </span>
            {property.streetview_date && (
              <span className="text-xs text-gray-400">
                Captured: {property.streetview_date}
              </span>
            )}
          </div>
          {property.streetview_available ? (
            <img
              src={getImageUrl(property.id, "streetview")}
              alt={`Street View for ${property.address}`}
              className="aspect-video w-full object-cover"
            />
          ) : (
            <div className="flex aspect-video w-full items-center justify-center bg-gray-50 text-sm text-gray-400">
              No Street View available
            </div>
          )}
        </div>

        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-100 px-3 py-2">
            <span className="text-xs font-medium text-gray-700">
              Satellite
            </span>
          </div>
          {property.satellite_path ? (
            <img
              src={getImageUrl(property.id, "satellite")}
              alt={`Satellite image for ${property.address}`}
              className="aspect-video w-full object-cover"
            />
          ) : (
            <div className="flex aspect-video w-full items-center justify-center bg-gray-50 text-sm text-gray-400">
              No satellite image
            </div>
          )}
        </div>
      </div>

      {/* External links */}
      <div className="flex flex-wrap gap-2">
        <a
          href={streetViewUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md bg-civic-green px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-civic-green-light"
        >
          Open Street View (Interactive)
        </a>
        <a
          href={propertyPortalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md bg-civic-blue px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-civic-blue-light"
        >
          Flint Property Portal
        </a>
        <a
          href={googleMapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md bg-gray-100 px-3 py-2 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-200"
        >
          Google Maps
        </a>
      </div>

      {/* Tax Information */}
      <TaxInfoCard
        taxStatus={property.tax_status || "unknown"}
        lastTaxPayment={property.last_tax_payment}
        taxAmountOwed={property.tax_amount_owed}
        homeownerExemption={property.homeowner_exemption}
      />

      {/* Outreach Log */}
      <OutreachLog propertyId={property.id} />

      {/* Finding buttons */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Record Your Finding
          </span>
          <span className="hidden text-xs text-gray-400 md:inline">
            Keys: 1-6 findings, arrows prev/next, Esc back
          </span>
        </div>
        <label className="mb-3 flex items-center gap-2 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={autoAdvance}
            onChange={(event) => setAutoAdvance(event.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-civic-green focus:ring-civic-green"
          />
          Move to the next property after saving a finding
        </label>
        <div className="flex flex-wrap gap-2">
          {FINDINGS.map((finding, index) => (
            <button
              key={finding.value}
              onClick={() => handleFinding(finding.value)}
              disabled={saving}
              className="rounded border px-3 py-2 text-xs font-medium transition-all"
              style={{
                color:
                  property.finding === finding.value ? "#fff" : finding.color,
                background:
                  property.finding === finding.value
                    ? finding.color
                    : finding.bg,
                borderColor: `${finding.color}40`,
              }}
            >
              <span className="mr-1 hidden text-[10px] opacity-60 md:inline">
                {index + 1}
              </span>
              {finding.label}
            </button>
          ))}
        </div>
        {autoAdvance && queueIds.length > 0 && (
          <p className="mt-3 text-xs text-gray-500">
            Notes save with the finding, then the next property in this queue
            opens automatically.
          </p>
        )}
      </div>

      {/* Notes */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
          Notes
        </div>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Street View shows recent renovation work. New siding visible. Image dated June 2025."
          rows={4}
          className="w-full resize-y rounded-md border border-gray-200 p-2.5 text-sm font-body"
        />
        <button
          onClick={handleSaveNotes}
          disabled={saving || notes === (property.notes || "")}
          className={`mt-2 rounded px-4 py-1.5 text-xs font-medium transition-colors ${
            saving || notes === (property.notes || "")
              ? "cursor-not-allowed bg-gray-100 text-gray-400"
              : "bg-civic-green text-white hover:bg-civic-green-light"
          }`}
        >
          {saving ? "Saving..." : "Save Notes"}
        </button>
      </div>

      {/* Metadata footer */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-400">
        {property.reviewed_at && (
          <span>
            Reviewed: {new Date(property.reviewed_at).toLocaleString()}
          </span>
        )}
        {property.geocoded_at && (
          <span>
            Geocoded: {new Date(property.geocoded_at).toLocaleString()}
          </span>
        )}
        {property.formatted_address && (
          <span>Resolved: {property.formatted_address}</span>
        )}
        {property.latitude && (
          <span>
            {property.latitude.toFixed(5)}, {property.longitude.toFixed(5)}
          </span>
        )}
      </div>
    </div>
  );
}
