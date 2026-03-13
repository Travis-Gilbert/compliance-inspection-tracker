export const FINDINGS = [
  { value: "visibly_renovated", label: "Visibly Renovated", color: "#2E7D32", bg: "#E8F5E9" },
  { value: "occupied_maintained", label: "Occupied & Maintained", color: "#1565C0", bg: "#E3F2FD" },
  { value: "partial_progress", label: "Partial Progress", color: "#F57F17", bg: "#FFF8E1" },
  { value: "appears_vacant", label: "Appears Vacant", color: "#E65100", bg: "#FFF3E0" },
  { value: "structure_gone", label: "Structure Gone", color: "#B71C1C", bg: "#FFEBEE" },
  { value: "inconclusive", label: "Needs Inspection", color: "#4A148C", bg: "#F3E5F5" },
];

export const DETECTION_LABELS = {
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
  { path: "/", label: "Dashboard", icon: "📊" },
  { path: "/review", label: "Review Queue", icon: "📋" },
  { path: "/map", label: "Compliance Map", icon: "M" },
  { path: "/import", label: "Import", icon: "📥" },
  { path: "/export", label: "Export", icon: "📤" },
];
