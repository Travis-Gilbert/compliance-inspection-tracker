export const FINDINGS = [
  { value: "visibly_renovated", label: "Visibly Renovated", color: "#2E7D32", bg: "#E8F5E9" },
  { value: "occupied_maintained", label: "Occupied & Maintained", color: "#1565C0", bg: "#E3F2FD" },
  { value: "partial_progress", label: "Partial Progress", color: "#F57F17", bg: "#FFF8E1" },
  { value: "appears_vacant", label: "Appears Vacant", color: "#E65100", bg: "#FFF3E0" },
  { value: "structure_gone", label: "Structure Gone", color: "#B71C1C", bg: "#FFEBEE" },
  { value: "inconclusive", label: "Needs Inspection", color: "#4A148C", bg: "#F3E5F5" },
] as const;

export const DETECTION_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  likely_occupied: { label: "Likely Occupied", color: "#2E7D32", bg: "#E8F5E9" },
  likely_vacant: { label: "Likely Vacant", color: "#E65100", bg: "#FFF3E0" },
  likely_demolished: { label: "Likely Demolished", color: "#B71C1C", bg: "#FFEBEE" },
  no_streetview: { label: "No Street View", color: "#757575", bg: "#F5F5F5" },
  unprocessed: { label: "Not Processed", color: "#9E9E9E", bg: "#FAFAFA" },
};

export const PROGRAMS = [
  "Featured Homes",
  "Ready for Rehab",
  "VIP Spotlight",
  "Demolition",
];

export const RESOLVED_FINDINGS = [
  "visibly_renovated",
  "occupied_maintained",
  "partial_progress",
  "appears_vacant",
  "structure_gone",
];

export const NAV_ITEMS = [
  { path: "/", label: "Dashboard", shortLabel: "DB" },
  { path: "/review", label: "Review Queue", shortLabel: "RQ" },
  { path: "/map", label: "Compliance Map", shortLabel: "MP" },
  { path: "/before-after", label: "Before and After", shortLabel: "BA" },
  { path: "/import", label: "Import", shortLabel: "IM" },
  { path: "/export", label: "Export", shortLabel: "EX" },
  { path: "/processing", label: "Processing", shortLabel: "PR" },
];

export const REVIEW_FAST_LANES = [
  {
    id: "unreviewed",
    label: "Open Queue",
    description: "Work the full open review queue by compliance priority.",
    params: { filter: "unreviewed", sort: "priority" },
  },
  {
    id: "likely_demolished",
    label: "Likely Demolished",
    description: "Start with the most urgent structure-loss signals.",
    params: { filter: "unreviewed", detection: "likely_demolished", sort: "detection_score" },
  },
  {
    id: "likely_vacant",
    label: "Likely Vacant",
    description: "Move through vacancy cases while detections are still fresh.",
    params: { filter: "unreviewed", detection: "likely_vacant", sort: "detection_score" },
  },
  {
    id: "needs_inspection",
    label: "Needs Inspection",
    description: "Review anything already marked for a field visit.",
    params: { filter: "inconclusive", sort: "priority" },
  },
  {
    id: "unprocessed",
    label: "Not Processed",
    description: "Find properties still waiting on imagery or detection.",
    params: { filter: "unreviewed", detection: "unprocessed", sort: "created_at" },
  },
];

export const COMPLIANCE_STATUSES = [
  { value: "compliant", label: "Compliant", color: "#2E7D32", bg: "#E8F5E9" },
  { value: "in_progress", label: "In Progress", color: "#1565C0", bg: "#E3F2FD" },
  { value: "needs_outreach", label: "Needs Outreach", color: "#F57F17", bg: "#FFF8E1" },
  { value: "non_compliant", label: "Non-Compliant", color: "#E65100", bg: "#FFF3E0" },
  { value: "unknown", label: "Unknown", color: "#757575", bg: "#F5F5F5" },
] as const;

export const TAX_STATUSES = [
  { value: "current", label: "Current", color: "#2E7D32" },
  { value: "delinquent", label: "Delinquent", color: "#B71C1C" },
  { value: "payment_plan", label: "Payment Plan", color: "#F57F17" },
  { value: "unknown", label: "Unknown", color: "#757575" },
] as const;
