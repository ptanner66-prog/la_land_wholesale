import client from './client';
import type {
  LeadSummary,
  LeadDetail,
  LeadStatistics,
  ManualLeadCreate,
  ManualLeadResponse,
  ScoringResult,
  ScoreDetails,
  TimelineEvent,
  CompsResult,
  OfferResult,
  MapData,
  MarketCode,
  PipelineStage,
} from '@/lib/types';

interface GetLeadsParams {
  market?: MarketCode;
  pipeline_stage?: PipelineStage;
  min_score?: number;
  status?: string;
  tcpa_safe_only?: boolean;
  order_by?: 'score_desc' | 'score_asc' | 'created_desc' | 'created_asc';
  limit?: number;
  offset?: number;
}

interface PaginatedLeads {
  items: LeadSummary[];
  total: number;
  limit: number;
  offset: number;
}

export async function getLeads(params: GetLeadsParams = {}): Promise<LeadSummary[]> {
  const response = await client.get<PaginatedLeads | LeadSummary[]>('/leads', { params });
  // Handle both paginated and array responses for backwards compatibility
  if (Array.isArray(response.data)) {
    return response.data;
  }
  return response.data.items || [];
}

export async function getLeadsPaginated(params: GetLeadsParams = {}): Promise<PaginatedLeads> {
  const response = await client.get<PaginatedLeads>('/leads', { params });
  // Ensure we always return a proper structure
  if (Array.isArray(response.data)) {
    return {
      items: response.data,
      total: response.data.length,
      limit: params.limit || 100,
      offset: params.offset || 0,
    };
  }
  return {
    items: response.data.items || [],
    total: response.data.total || 0,
    limit: response.data.limit || params.limit || 100,
    offset: response.data.offset || params.offset || 0,
  };
}

export async function getLeadById(leadId: number): Promise<LeadDetail> {
  const response = await client.get<LeadDetail>(`/leads/${leadId}`);
  return response.data;
}

export async function searchLeads(
  q: string,
  market?: MarketCode,
  limit: number = 50
): Promise<LeadSummary[]> {
  const response = await client.get<LeadSummary[]>('/leads/search', {
    params: { q, market, limit },
  });
  return response.data;
}

export async function getLeadStatistics(market?: MarketCode): Promise<LeadStatistics> {
  const response = await client.get<LeadStatistics>('/leads/statistics', {
    params: { market },
  });
  return response.data;
}

export async function createManualLead(data: ManualLeadCreate): Promise<ManualLeadResponse> {
  const response = await client.post<ManualLeadResponse>('/leads/manual', data);
  return response.data;
}

export async function updateLeadStatus(
  leadId: number,
  status: string
): Promise<LeadDetail> {
  const response = await client.patch<LeadDetail>(`/leads/${leadId}/status`, null, {
    params: { status },
  });
  return response.data;
}

export async function updatePipelineStage(
  leadId: number,
  stage: PipelineStage
): Promise<{ id: number; old_stage: string; new_stage: string; success: boolean }> {
  const response = await client.post(`/leads/${leadId}/stage`, { stage });
  return response.data;
}

export async function getScoreDetails(leadId: number): Promise<ScoreDetails> {
  const response = await client.get<ScoreDetails>(`/leads/${leadId}/score_details`);
  return response.data;
}

export async function rescoreLead(
  leadId: number
): Promise<{ id: number; old_score: number; new_score: number; score_details: ScoreDetails }> {
  const response = await client.post(`/leads/${leadId}/rescore`);
  return response.data;
}

export async function getLeadTimeline(
  leadId: number,
  limit: number = 50,
  event_type?: string
): Promise<TimelineEvent[]> {
  const response = await client.get<TimelineEvent[]>(`/leads/${leadId}/timeline`, {
    params: { limit, event_type },
  });
  return response.data;
}

export async function getLeadComps(
  leadId: number,
  max_comps: number = 5
): Promise<CompsResult> {
  const response = await client.get<CompsResult>(`/leads/${leadId}/comps`, {
    params: { max_comps },
  });
  return response.data;
}

export async function getLeadOffer(leadId: number): Promise<OfferResult> {
  const response = await client.get<OfferResult>(`/leads/${leadId}/offer`);
  return response.data;
}

export async function getLeadMapData(leadId: number): Promise<MapData> {
  const response = await client.get<MapData>(`/leads/${leadId}/map`);
  return response.data;
}

export async function scoreLeads(market?: MarketCode): Promise<{ message: string; market: string }> {
  const response = await client.post('/leads/score', null, {
    params: { market },
  });
  return response.data;
}

export async function scoreLeadsSync(
  market?: MarketCode,
  min_score?: number
): Promise<ScoringResult> {
  const response = await client.post<ScoringResult>('/leads/score-sync', null, {
    params: { market, min_score },
  });
  return response.data;
}

export interface DeleteLeadResult {
  success: boolean;
  lead_id: number;
  outreach_deleted: number;
  timeline_deleted: number;
  owner_orphaned: boolean;
  parcel_orphaned: boolean;
}

export async function deleteLead(leadId: number): Promise<DeleteLeadResult> {
  const response = await client.delete<DeleteLeadResult>(`/leads/${leadId}`);
  return response.data;
}

// Background scoring job
export interface ScoringJobResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface JobStatus {
  job_id: string;
  job_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  total: number;
  processed: number;
  remaining: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  result: Record<string, unknown>;
  progress_percent: number;
}

export async function startScoringJob(
  market?: MarketCode,
  batchSize: number = 1000
): Promise<ScoringJobResponse> {
  const response = await client.post<ScoringJobResponse>('/automation/scoring/start', {
    market,
    batch_size: batchSize,
  });
  return response.data;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const response = await client.get<JobStatus>(`/automation/status/${jobId}`);
  return response.data;
}

export default {
  getLeads,
  getLeadById,
  searchLeads,
  getLeadStatistics,
  createManualLead,
  updateLeadStatus,
  updatePipelineStage,
  getScoreDetails,
  rescoreLead,
  getLeadTimeline,
  getLeadComps,
  getLeadOffer,
  getLeadMapData,
  scoreLeads,
  scoreLeadsSync,
  deleteLead,
  startScoringJob,
  getJobStatus,
};
