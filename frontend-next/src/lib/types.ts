export interface Property {
  id: number;
  address: string;
  parcel_id: string | null;
  buyer_name: string | null;
  program: string | null;
  closing_date: string | null;
  commitment: string | null;
  finding: string | null;
  notes: string | null;
  detection_label: string | null;
  detection_score: number | null;
  compliance_status: string | null;
  tax_status: string | null;
  last_tax_payment: string | null;
  tax_amount_owed: number | null;
  homeowner_exemption: boolean | null;
  priority_score: number;
  latitude: number | null;
  longitude: number | null;
  formatted_address: string | null;
  streetview_available: boolean;
  streetview_date: string | null;
  streetview_historical_path: string | null;
  streetview_historical_date: string | null;
  satellite_path: string | null;
  reviewed_at: string | null;
  geocoded_at: string | null;
  created_at: string | null;
}

export interface Stats {
  total: number;
  reviewed: number;
  unreviewed: number;
  resolved: number;
  needs_inspection: number;
  inspection_candidates: number;
  percent_reviewed: number;
  by_finding: Record<string, number>;
  by_detection: Record<string, number>;
  by_compliance_status: Record<string, number>;
  unreviewed_by_detection: Record<string, number>;
}

export interface QueueResponse {
  properties: Property[];
  total: number;
}

export interface PipelineEvent {
  step: string;
  status?: string;
  total?: number;
  current?: number;
  processed?: number;
  attempted?: number;
  message?: string;
  grand_totals?: { total: number };
  grand_processed?: number;
}
