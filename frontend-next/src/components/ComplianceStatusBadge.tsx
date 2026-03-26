"use client";

import { COMPLIANCE_STATUSES } from "@/lib/constants";

interface ComplianceStatusBadgeProps {
  status: string;
  className?: string;
}

export default function ComplianceStatusBadge({ status, className = "" }: ComplianceStatusBadgeProps) {
  const meta = COMPLIANCE_STATUSES.find((s) => s.value === status) || {
    label: status || "Unknown",
    color: "#757575",
    bg: "#F5F5F5",
  };

  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${className}`}
      style={{ color: meta.color, backgroundColor: meta.bg }}
    >
      {meta.label}
    </span>
  );
}
