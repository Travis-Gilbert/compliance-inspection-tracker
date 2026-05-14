export interface Property {
  id: number;
  address: string;
  parcel_id: string | null;
  buyer_name: string | null;
  email: string | null;
  organization: string | null;
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
  streetview_path?: string | null;
  streetview_date: string | null;
  streetview_historical_path: string | null;
  streetview_historical_date: string | null;
  satellite_path: string | null;
  reviewed_at: string | null;
  geocoded_at: string | null;
  created_at: string | null;
  manual_compliance_outcome: ComplianceOutcome;
  photo_summary?: PhotoSummary;
  photos?: PropertyPhoto[];
  primary_before_photo?: PropertyPhoto | null;
  primary_after_photo?: PropertyPhoto | null;
}

export interface Stats {
  total: number;
  geocoded: number;
  imagery_fetched: number;
  detection_ran: number;
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
  compliant_reviewed: number;
  non_compliant_reviewed: number;
  in_progress_reviewed: number;
  compliant_percent_reviewed: number;
  photo_ready: number;
  uploaded_before_count: number;
  uploaded_after_count: number;
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

export type PhotoSide = "before" | "after";

export type ComplianceOutcome =
  | "pending"
  | "compliant"
  | "non_compliant"
  | "in_progress"
  | "needs_inspection"
  | "unknown";

export interface PropertyPhoto {
  id: number;
  property_id: number;
  side: PhotoSide;
  image_url: string;
  original_filename: string;
  caption: string;
  source: string;
  is_primary: boolean;
  photo_date: string | null;
  photo_latitude: number | null;
  photo_longitude: number | null;
  distance_from_property_meters: number | null;
  proximity_status: string;
  metadata: Record<string, unknown>;
  uploaded_at: string | null;
}

export interface PhotoSummary {
  before_count: number;
  after_count: number;
  total_count: number;
  has_before: boolean;
  has_after: boolean;
  is_complete: boolean;
}

export interface GalleryResponse {
  properties: Property[];
  total: number;
  limit: number;
  offset: number;
}

export interface SearchResponse {
  query: string;
  results: Property[];
}

export interface WorkflowTiming {
  propertyId: number | null;
  parcelId: string;
  address: string;
  buyerName: string;
  buyerEmail: string;
  programType: string;
  programLabel: string;
  daysSinceClose: number;
  currentAction: string;
  recommendedEnforcementLevel: number;
  dueDate: string;
  isDueNow: boolean;
  daysOverdue: number;
  actionAlreadySent: boolean;
  completedActions: string[];
  nextAction: string | null;
  nextDueDate: string | null;
  lastContactDate: string | null;
  reasons: string[];
  error?: string;
}

export interface WorkflowQueueItem {
  propertyId: number;
  parcelId: string;
  address: string;
  buyerName: string;
  buyerEmail: string;
  program: string;
  action: string;
  actionLabel: string;
  status: string;
  dueDate: string | null;
  daysOverdue: number;
  priority: number;
  enforcementLevel: number;
  reasons: string[];
  source: string;
  finding: string | null;
  manualOutcome: ComplianceOutcome | string;
  taxStatus: string | null;
  notes: string;
  timing?: WorkflowTiming;
}

export interface WorkflowQueueGroup {
  action: string;
  label: string;
  count: number;
  items: WorkflowQueueItem[];
}

export interface WorkflowQueueResponse {
  asOf: string;
  groupOrder: string[];
  groups: WorkflowQueueGroup[];
  summary: Record<string, number>;
  totalItems: number;
}

export interface WorkflowTemplateRef {
  slug: string;
  name: string;
  status: string;
  isActive: boolean;
}

export interface WorkflowTemplatePreview {
  propertyId: number;
  action: string;
  template: WorkflowTemplateRef;
  recipientEmail: string;
  subject: string;
  body: string;
  missingVariables: string[];
  variables: Record<string, string>;
  timing: WorkflowTiming;
}

export interface WorkflowCommunication {
  id: number;
  property_id: number;
  buyer_id: number | null;
  template_id: number | null;
  template_slug: string;
  template_name: string;
  method: string;
  direction: string;
  action: string;
  status: string;
  recipient_email: string;
  provider_message_id: string;
  date_sent: string | null;
  sent_at: string | null;
  approved_at: string | null;
  subject: string;
  body: string;
  body_hash: string;
  response_received: boolean;
  response_date: string | null;
  response_notes: string;
  created_at: string | null;
  preview?: WorkflowTemplatePreview;
  documents?: WorkflowDocument[];
}

export interface WorkflowDocument {
  id: number;
  property_id: number | null;
  communication_id: number | null;
  filename: string;
  storage_key: string;
  storage_url: string;
  mime_type: string;
  size_bytes: number;
  category: string;
  slot: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

export interface WorkflowLetterPacketResponse {
  batch_document: WorkflowDocument;
  manifest_document: WorkflowDocument;
  letters: WorkflowDocument[];
  audits: WorkflowDocument[];
}
