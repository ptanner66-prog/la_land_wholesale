// Type definitions for LA Land Wholesale API

// =============================================================================
// Enums
// =============================================================================

export type MarketCode = 'LA' | 'TX' | 'MS' | 'AR' | 'AL';

export type PipelineStage =
  | 'INGESTED'
  | 'ENRICHING'
  | 'PRE_SCORE'
  | 'NEW'
  | 'CONTACTED'
  | 'REVIEW'
  | 'OFFER'
  | 'CONTRACT'
  | 'HOT';

export type ReplyClassification =
  | 'INTERESTED'
  | 'NOT_INTERESTED'
  | 'SEND_OFFER'
  | 'CONFUSED'
  | 'DEAD';

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export type BuyerDealStage =
  | 'NEW'
  | 'DEAL_SENT'
  | 'VIEWED'
  | 'INTERESTED'
  | 'NEGOTIATING'
  | 'OFFERED'
  | 'CLOSED'
  | 'PASSED';

export type PropertyType =
  | 'infill'
  | 'rural'
  | 'wooded'
  | 'lot'
  | 'agricultural'
  | 'recreational'
  | 'waterfront';

// =============================================================================
// Core Models
// =============================================================================

export interface Owner {
  id: number;
  party_id: number;
  market_code: MarketCode;
  phone?: string;
  phone_primary?: string;
  phone_secondary?: string;
  email?: string;
  tcpa_compliant: boolean;
  is_tcpa_safe?: boolean;
  dnc_registered: boolean;
  is_dnr?: boolean;
  opt_out?: boolean;
  created_at: string;
  updated_at: string;
}

export interface Parcel {
  id: number;
  canonical_parcel_id: string;
  market_code: MarketCode;
  raw_parcel_id?: string;
  address?: string;
  situs_address?: string;
  city?: string;
  state?: string;
  zip?: string;
  postal_code?: string;
  parish?: string;
  latitude?: number;
  longitude?: number;
  acres?: number;
  lot_size_acres?: number;
  property_type?: PropertyType;
  assessed_value?: number;
  land_assessed_value?: number;
  market_value?: number;
  is_adjudicated?: boolean;
  years_tax_delinquent?: number;
  inside_city_limits?: boolean;
  created_at: string;
  updated_at: string;
}

export interface LeadSummary {
  id: number;
  owner_id: number;
  parcel_id: number;
  market_code: MarketCode;
  motivation_score?: number;
  pipeline_stage: PipelineStage;
  status?: string;
  created_at: string;
  updated_at: string;
  owner?: Owner;
  parcel?: Parcel;
}

export interface LeadDetail extends LeadSummary {
  score_details?: ScoreDetails;
  last_reply_classification?: ReplyClassification;
  last_reply_at?: string;
  followup_count: number;
  last_followup_at?: string;
  next_followup_at?: string;
  tags?: string[];
}

export interface ScoreDetails {
  total_score: number;
  factors: Record<string, any>;
  breakdown: Record<string, number>;
}

export interface ScoringResult {
  lead_id: number;
  motivation_score: number;
  score_details: ScoreDetails;
}

// =============================================================================
// Lead Operations
// =============================================================================

export interface ManualLeadCreate {
  market_code: MarketCode;
  owner_name: string;
  owner_phone?: string;
  owner_email?: string;
  address: string;
  city?: string;
  state?: string;
  zip?: string;
  acres?: number;
  assessed_value?: number;
}

export interface ManualLeadResponse {
  lead_id: number;
  message: string;
}

export interface LeadStatistics {
  total: number;
  by_stage: Record<PipelineStage, number>;
  by_market: Record<MarketCode, number>;
  avg_score: number;
}

export interface TimelineEvent {
  id: number;
  lead_id: number;
  event_type: string;
  description: string;
  metadata?: Record<string, any>;
  created_at: string;
}

// =============================================================================
// Offers & Comps
// =============================================================================

export interface OfferResult {
  lead_id: number;
  mao: number;
  offer_range: {
    min: number;
    max: number;
  };
  risk_adjustment: number;
  calculated_at: string;
}

export interface CompsResult {
  lead_id: number;
  comps: CompSale[];
  avg_price_per_acre: number;
  calculated_at: string;
}

export interface CompSale {
  address: string;
  sale_price: number;
  sale_date: string;
  acres: number;
  price_per_acre: number;
  distance_miles: number;
  distance?: number;
}

// =============================================================================
// Buyers & Deals
// =============================================================================

export interface Buyer {
  id: number;
  name: string;
  phone?: string;
  email?: string;
  markets: MarketCode[];
  market_codes?: MarketCode[];
  counties?: string[];
  min_acres?: number;
  max_acres?: number;
  max_budget?: number;
  price_min?: number;
  price_max?: number;
  target_spread?: number;
  closing_speed_days?: number;
  property_types: PropertyType[];
  vip?: boolean;
  notes?: string;
  pof_url?: string;
  pof_verified?: boolean;
  created_at: string;
  updated_at: string;
}

export interface BuyerSummary {
  id: number;
  name: string;
  markets: MarketCode[];
  deal_count: number;
  closed_deals: number;
  vip: boolean;
}

export interface BuyerCreate {
  name: string;
  phone?: string;
  email?: string;
  markets: MarketCode[];
  min_acres?: number;
  max_acres?: number;
  max_budget?: number;
  property_types: PropertyType[];
}

export interface BuyerStatistics {
  total_buyers: number;
  active_buyers: number;
  by_market: Record<MarketCode, number>;
  avg_deals_per_buyer: number;
}

export interface BuyerMatch {
  buyer: Buyer;
  match_score: number;
  match_factors: Record<string, any>;
}

export interface MatchBuyersResponse {
  lead_id: number;
  matches: BuyerMatch[];
  total_matches: number;
}

export interface BlastResult {
  success: boolean;
  buyers_notified: number;
  messages_sent: number;
  errors: string[];
}

export interface BlastPreview {
  buyer_count: number;
  message_preview: string;
  estimated_cost: number;
}

export interface BuyerPipelineResponse {
  deals: BuyerDeal[];
  statistics: {
    by_stage: Record<BuyerDealStage, number>;
    total_value: number;
  };
}

export interface BuyerDeal {
  id: number;
  buyer_id: number;
  lead_id: number;
  stage: BuyerDealStage;
  created_at: string;
  updated_at: string;
  buyer?: Buyer;
  lead?: LeadDetail;
}

export interface DealSheet {
  lead_id: number;
  property_description: string;
  highlights: string[];
  offer_details: {
    asking_price: number;
    assignment_fee: number;
    buyer_price: number;
  };
  generated_at: string;
}

export interface DispositionSummary {
  lead: LeadDetail;
  deal_sheet: DealSheet;
  matched_buyers: BuyerMatch[];
  assignment_fee: number;
}

export interface CallScript {
  lead_id: number;
  script: string;
  key_points: string[];
  objection_handlers: Record<string, string>;
}

// =============================================================================
// Outreach
// =============================================================================

export interface OutreachAttempt {
  id: number;
  lead_id: number;
  message: string;
  message_body?: string;
  message_context?: any;
  status: string;
  sid?: string;
  result?: string;
  reply_classification?: ReplyClassification;
  sent_at?: string;
  created_at: string;
}

export interface OutreachResult {
  success: boolean;
  message_sid?: string;
  error?: string;
}

export interface OutreachStats {
  total_attempts: number;
  sent_today: number;
  responses_today: number;
  pending_followups: number;
  response_rate: number;
  successful?: number;
  failed?: number;
}

export interface GenerateMessageResponse {
  message: string;
  template_used?: string;
}

export interface ClassifyReplyResponse {
  classification: ReplyClassification;
  confidence: number;
  suggested_response?: string;
}

export interface FollowupDueResponse {
  leads: LeadSummary[];
  total: number;
  total_due?: number;
}

export interface SendMessageRequest {
  lead_id: number;
  message: string;
  dry_run?: boolean;
}

export interface SendMessageResponse {
  success: boolean;
  message_sid?: string;
  lead_id: number;
  sent_at?: string;
  error?: string;
}

export interface ConversationThread {
  lead_id: number;
  messages: Message[];
  last_message_at: string;
  unread_count: number;
}

export interface Message {
  id: number;
  from: string;
  to: string;
  body: string;
  direction: 'inbound' | 'outbound';
  created_at: string;
}

// =============================================================================
// Markets & Configuration
// =============================================================================

export interface MarketConfig {
  market_code: MarketCode;
  code?: MarketCode;
  name: string;
  state: string;
  enabled: boolean;
  min_motivation_score: number;
  max_sms_per_day: number;
}

export interface MarketStats {
  market_code: MarketCode;
  total_leads: number;
  active_leads: number;
  avg_motivation_score: number;
  total_parcels: number;
}

// =============================================================================
// System & Health
// =============================================================================

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  dry_run?: boolean;
  environment?: string;
  checks?: Record<string, any>;
}

export interface ExternalServiceStatus {
  service_name?: string;
  status: 'available' | 'unavailable' | 'degraded';
  last_checked?: string;
  services?: Record<string, any>;
}

export interface BackgroundTask {
  id: number;
  task_name: string;
  status: TaskStatus;
  progress?: number;
  result?: any;
  error?: string;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Ingestion
// =============================================================================

export interface IngestionResult {
  success: boolean;
  leads_created: number;
  leads_updated: number;
  errors: string[];
  warnings: string[];
}

export interface IngestionJob {
  id: number;
  filename: string;
  status: TaskStatus;
  total_rows: number;
  processed_rows: number;
  created_leads: number;
  errors: number;
  started_at?: string;
  completed_at?: string;
}

// =============================================================================
// Map & Visualization
// =============================================================================

export interface MapData {
  center: {
    lat: number;
    lng: number;
  };
  zoom: number;
  markers: MapMarker[];
}

export interface MapMarker {
  id: number;
  position: {
    lat: number;
    lng: number;
  };
  label: string;
  color: string;
}

// =============================================================================
// Dashboard & Analytics
// =============================================================================

export interface PipelineStats {
  total_leads: number;
  by_stage: Record<PipelineStage, number>;
  hot_leads: number;
  avg_motivation_score: number;
  conversion_rate: number;
}

export interface DashboardMetrics {
  pipeline: PipelineStats;
  outreach: {
    sent_today: number;
    responses_today: number;
    response_rate: number;
  };
  deals: {
    active_deals: number;
    closed_this_month: number;
    revenue_this_month: number;
  };
}

// =============================================================================
// Alert Configuration
// =============================================================================

export interface AlertConfig {
  id: number;
  market_code: MarketCode;
  min_score_threshold: number;
  hot_score_threshold?: number;
  enabled: boolean;
  notification_channels: string[];
  alert_phone?: string;
  slack_webhook_url?: string;
}

// =============================================================================
// Evaluation & Scoring
// =============================================================================

export interface EvaluationResult {
  lead_id: number;
  recommendation: 'pursue' | 'pass' | 'review';
  confidence: number;
  factors: Record<string, any>;
  notes: string;
}

// =============================================================================
// API Response Wrappers
// =============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ApiError {
  error: string;
  message: string;
  detail?: string;
}

// =============================================================================
// Call Prep
// =============================================================================

export interface CallPrepPack {
  lead: LeadDetail;
  owner: Owner;
  parcel: Parcel;
  deal_sheet?: DealSheet;
  call_script?: CallScript;
  comps?: CompsResult;
  timeline: TimelineEvent[];
}

// =============================================================================
// Active Market
// =============================================================================

export interface ActiveMarketLock {
  market_code: MarketCode;
  locked_by: string;
  locked_at: string;
  expires_at: string;
}

// =============================================================================
// Automation
// =============================================================================

export interface RunFollowupsResult {
  total_processed: number;
  messages_sent: number;
  sent?: number;
  skipped?: number;
  errors: number;
  dry_run: boolean;
}

export interface NightlyPipelineResult {
  enriched: number;
  scored: number;
  archived: number;
  errors: number;
  markets_processed?: MarketCode[];
  duration_seconds: number;
}
