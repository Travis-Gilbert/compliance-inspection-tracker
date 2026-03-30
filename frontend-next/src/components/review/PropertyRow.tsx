"use client";

import { DETECTION_LABELS, FINDINGS, TAX_STATUSES } from "@/lib/constants";
import type { Property } from "@/lib/types";
import ComplianceStatusBadge from "@/components/ComplianceStatusBadge";

interface PropertyRowProps {
  property: Property;
  isSelected: boolean;
  isFocused: boolean;
  isChecked: boolean;
  onSelect: () => void;
  onCheck: () => void;
}

export default function PropertyRow({
  property,
  isSelected,
  isFocused,
  isChecked,
  onSelect,
  onCheck,
}: PropertyRowProps) {
  const finding = FINDINGS.find((item) => item.value === property.finding);
  const detection = DETECTION_LABELS[property.detection_label || ""];

  return (
    <div
      role="option"
      aria-selected={isSelected}
      tabIndex={isFocused ? 0 : -1}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={`cursor-pointer border-b border-gray-100 px-3 py-2.5 transition-colors ${
        isSelected
          ? "bg-civic-green-pale border-l-2 border-l-civic-green"
          : isFocused
            ? "bg-gray-50 border-l-2 border-l-gray-300"
            : "hover:bg-gray-50"
      }`}
    >
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          aria-label={`Select ${property.address}`}
          checked={isChecked}
          onChange={(e) => {
            e.stopPropagation();
            onCheck();
          }}
          onClick={(e) => e.stopPropagation()}
          className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-gray-300 text-civic-green focus:ring-civic-green"
        />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-gray-900 truncate">
            {property.address}
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-gray-500">
            {property.buyer_name && <span className="truncate">{property.buyer_name}</span>}
            {property.parcel_id && <span>{property.parcel_id}</span>}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {property.program && (
              <span className="rounded bg-civic-blue-pale px-1.5 py-0.5 text-[11px] font-medium text-civic-blue">
                {property.program}
              </span>
            )}
            {property.compliance_status && property.compliance_status !== "unknown" && (
              <ComplianceStatusBadge status={property.compliance_status} className="text-[11px] px-1.5 py-0.5" />
            )}
            {property.tax_status && property.tax_status === "delinquent" && (
              <span className="rounded bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-700">
                Tax: {TAX_STATUSES.find((s) => s.value === property.tax_status)?.label || property.tax_status}
              </span>
            )}
            {detection && property.detection_label !== "unprocessed" && (
              <span
                className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                style={{ color: detection.color, background: detection.bg }}
              >
                {detection.label}
              </span>
            )}
            {finding ? (
              <span
                className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                style={{ color: finding.color, background: finding.bg }}
              >
                {finding.label}
              </span>
            ) : (
              <span className="rounded bg-gray-50 px-1.5 py-0.5 text-[11px] italic text-gray-400">
                Unreviewed
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
