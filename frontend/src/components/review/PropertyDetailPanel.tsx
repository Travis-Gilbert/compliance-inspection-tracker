"use client";

import { useState } from "react";
import { getImageUrl } from "@/lib/api";
import { DETECTION_LABELS } from "@/lib/constants";
import type { Property } from "@/lib/types";
import ComplianceStatusBadge from "@/components/ComplianceStatusBadge";
import TaxInfoCard from "@/components/TaxInfoCard";
import OutreachLog from "@/components/OutreachLog";
import FindingButtons from "./FindingButtons";

interface PropertyDetailPanelProps {
  property: Property;
  notes: string;
  onNotesChange: (notes: string) => void;
  onSaveNotes: () => void;
  onFindingAssign: (finding: string) => void;
  saving: boolean;
  notice?: { tone: "info" | "success" | "warning" | "error"; title: string; message: string } | null;
}

export default function PropertyDetailPanel({
  property,
  notes,
  onNotesChange,
  onSaveNotes,
  onFindingAssign,
  saving,
}: PropertyDetailPanelProps) {
  const detection = DETECTION_LABELS[property.detection_label || ""];
  const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${encodeURIComponent(property.formatted_address || `${property.address}, Flint, MI`)}`;
  const propertyPortalUrl = `https://www.flintpropertyportal.com/search?q=${encodeURIComponent(property.address)}`;
  const googleMapsUrl = `https://www.google.com/maps/search/${encodeURIComponent(property.formatted_address || `${property.address}, Flint, MI`)}`;

  const [streetviewError, setStreetviewError] = useState(false);

  return (
    <section aria-label="Property detail" className="space-y-4 p-4">
      {/* Property header */}
      <div>
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-heading text-lg font-bold text-gray-900">
            {property.address}
          </h3>
          {property.compliance_status && property.compliance_status !== "unknown" && (
            <ComplianceStatusBadge status={property.compliance_status} />
          )}
        </div>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
          {property.parcel_id && <span>Parcel: {property.parcel_id}</span>}
          {property.buyer_name && <span>Buyer: {property.buyer_name}</span>}
          {property.program && (
            <span className="rounded bg-civic-blue-pale px-1.5 py-0.5 font-medium text-civic-blue">
              {property.program}
            </span>
          )}
          {property.closing_date && <span>Closed: {property.closing_date}</span>}
          {property.commitment && <span>Committed: {property.commitment}</span>}
        </div>
      </div>

      {/* Imagery side-by-side */}
      <div className="grid grid-cols-2 gap-2">
        <div className="overflow-hidden rounded border border-gray-200 bg-gray-100">
          <div className="flex items-center justify-between border-b border-gray-100 bg-white px-2 py-1">
            <span className="text-[11px] font-medium text-gray-700">Street View</span>
            {property.streetview_date && (
              <span className="text-[11px] text-gray-400">{property.streetview_date}</span>
            )}
          </div>
          {property.streetview_available && !streetviewError ? (
            <img
              src={getImageUrl(property.id, "streetview")}
              alt={`Street View for ${property.address}`}
              className="aspect-video w-full object-cover"
              onError={() => setStreetviewError(true)}
            />
          ) : (
            <div className="flex aspect-video w-full items-center justify-center text-xs text-gray-400 px-2 text-center">
              {streetviewError ? (
                <a
                  href={streetViewUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-civic-green hover:underline"
                >
                  View on Google Street View
                </a>
              ) : (
                "No Street View"
              )}
            </div>
          )}
        </div>
        <div className="overflow-hidden rounded border border-gray-200 bg-gray-100">
          <div className="border-b border-gray-100 bg-white px-2 py-1">
            <span className="text-[11px] font-medium text-gray-700">Satellite</span>
          </div>
          {property.satellite_path ? (
            <img
              src={getImageUrl(property.id, "satellite")}
              alt={`Satellite for ${property.address}`}
              className="aspect-video w-full object-cover"
            />
          ) : (
            <div className="flex aspect-video w-full items-center justify-center text-xs text-gray-400">
              No satellite image
            </div>
          )}
        </div>
      </div>

      {/* Detection alert */}
      {detection && property.detection_label !== "unprocessed" && (
        <div
          className="flex items-center gap-3 rounded border px-3 py-2"
          style={{ borderColor: `${detection.color}40`, background: detection.bg }}
        >
          <span className="text-xs font-medium" style={{ color: detection.color }}>
            Detection: {detection.label}
          </span>
          {property.detection_score != null && (
            <>
              <div className="h-1.5 flex-1 rounded-full bg-white/60">
                <div
                  className="h-1.5 rounded-full"
                  style={{ width: `${Math.round(property.detection_score * 100)}%`, backgroundColor: detection.color }}
                />
              </div>
              <span className="text-[11px] text-gray-500">
                {property.detection_score.toFixed(2)} ({property.detection_score < 0.3 ? "low confidence" : property.detection_score < 0.6 ? "moderate confidence" : "high confidence"})
              </span>
            </>
          )}
        </div>
      )}

      {/* External links */}
      <div className="flex flex-wrap gap-2">
        <a
          href={streetViewUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded bg-civic-green px-2.5 py-1.5 text-xs font-medium text-white hover:bg-civic-green-light"
        >
          Interactive Street View
        </a>
        <a
          href={propertyPortalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded bg-civic-blue px-2.5 py-1.5 text-xs font-medium text-white hover:bg-civic-blue-light"
        >
          Property Portal
        </a>
        <a
          href={googleMapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded bg-gray-100 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200"
        >
          Google Maps
        </a>
      </div>

      {/* Finding buttons */}
      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
          Record Your Finding
        </div>
        <FindingButtons
          currentFinding={property.finding}
          onAssign={onFindingAssign}
          disabled={saving}
        />
        <div className="mt-1.5 text-[11px] text-gray-400">
          Keys: 1-6 findings, j/k navigate, Esc back to list
        </div>
      </div>

      {/* Notes */}
      <div>
        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">Notes</div>
        <textarea
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          placeholder="Street View shows recent renovation work. New siding visible."
          rows={3}
          className="w-full resize-y rounded border border-gray-200 p-2 text-sm font-body"
        />
        <button
          onClick={onSaveNotes}
          disabled={saving || notes === (property.notes || "")}
          className={`mt-1.5 rounded px-3 py-1 text-xs font-medium transition-colors ${
            saving || notes === (property.notes || "")
              ? "cursor-not-allowed bg-gray-100 text-gray-400"
              : "bg-civic-green text-white hover:bg-civic-green-light"
          }`}
        >
          {saving ? "Saving..." : "Save Notes"}
        </button>
      </div>

      {/* Tax Info */}
      <TaxInfoCard
        taxStatus={property.tax_status || "unknown"}
        lastTaxPayment={property.last_tax_payment}
        taxAmountOwed={property.tax_amount_owed}
        homeownerExemption={property.homeowner_exemption ?? undefined}
      />

      {/* Outreach Log */}
      <OutreachLog propertyId={property.id} />

      {/* Metadata */}
      <div className="flex flex-wrap gap-3 text-[11px] text-gray-400">
        {property.reviewed_at && <span>Reviewed: {new Date(property.reviewed_at).toLocaleString()}</span>}
        {property.geocoded_at && <span>Geocoded: {new Date(property.geocoded_at).toLocaleString()}</span>}
        {property.formatted_address && <span>Resolved: {property.formatted_address}</span>}
        {property.latitude && <span>{property.latitude.toFixed(5)}, {property.longitude?.toFixed(5)}</span>}
      </div>
    </section>
  );
}
