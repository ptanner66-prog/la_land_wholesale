import client from './client';
import type {
  Buyer,
  BuyerSummary,
  BuyerCreate,
  BuyerDeal,
  MatchBuyersResponse,
  BlastResult,
  BlastPreview,
  BuyerPipelineResponse,
  BuyerStatistics,
  MarketCode,
  BuyerDealStage,
} from '@/lib/types';

// =============================================================================
// Buyer CRUD
// =============================================================================

export async function createBuyer(data: BuyerCreate): Promise<Buyer> {
  const response = await client.post<Buyer>('/buyers', data);
  return response.data;
}

export async function getBuyers(params?: {
  market?: MarketCode;
  vip_only?: boolean;
  pof_verified_only?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<BuyerSummary[]> {
  const response = await client.get<BuyerSummary[]>('/buyers', { params });
  return response.data;
}

export async function getBuyer(buyerId: number): Promise<Buyer> {
  const response = await client.get<Buyer>(`/buyers/${buyerId}`);
  return response.data;
}

export async function updateBuyer(
  buyerId: number,
  data: Partial<BuyerCreate>
): Promise<Buyer> {
  const response = await client.put<Buyer>(`/buyers/${buyerId}`, data);
  return response.data;
}

export async function deleteBuyer(buyerId: number): Promise<{ success: boolean }> {
  const response = await client.delete(`/buyers/${buyerId}`);
  return response.data;
}

export async function updateBuyerPOF(
  buyerId: number,
  pofUrl: string,
  verified: boolean = false
): Promise<Buyer> {
  const response = await client.post<Buyer>(`/buyers/${buyerId}/pof`, {
    pof_url: pofUrl,
    verified,
  });
  return response.data;
}

export async function getBuyerDeals(
  buyerId: number,
  limit: number = 50
): Promise<BuyerDeal[]> {
  const response = await client.get<BuyerDeal[]>(`/buyers/${buyerId}/deals`, {
    params: { limit },
  });
  return response.data;
}

export async function getBuyerStatistics(): Promise<BuyerStatistics> {
  const response = await client.get<BuyerStatistics>('/buyers/statistics');
  return response.data;
}

// =============================================================================
// Buyer Matching
// =============================================================================

export async function matchBuyersToLead(
  leadId: number,
  params?: {
    offer_price?: number;
    min_score?: number;
    limit?: number;
  }
): Promise<MatchBuyersResponse> {
  const response = await client.post<MatchBuyersResponse>(
    `/buyers/match/${leadId}`,
    null,
    { params }
  );
  return response.data;
}

// =============================================================================
// Buyer Blast
// =============================================================================

export async function sendBuyerBlast(
  leadId: number,
  options?: {
    buyer_ids?: number[];
    min_match_score?: number;
    max_buyers?: number;
    dry_run?: boolean;
  }
): Promise<BlastResult> {
  const response = await client.post<BlastResult>(`/buyers/blast/${leadId}`, options || {});
  return response.data;
}

export async function previewBuyerBlast(
  leadId: number,
  params?: {
    min_match_score?: number;
    max_buyers?: number;
  }
): Promise<BlastPreview> {
  const response = await client.get<BlastPreview>(`/buyers/blast/${leadId}/preview`, {
    params,
  });
  return response.data;
}

// =============================================================================
// Buyer Deals
// =============================================================================

export async function getDealsForLead(leadId: number): Promise<BuyerDeal[]> {
  const response = await client.get<BuyerDeal[]>(`/buyers/deals/by-lead/${leadId}`);
  return response.data;
}

export async function updateDealStage(
  dealId: number,
  stage: BuyerDealStage,
  options?: {
    offer_amount?: number;
    assignment_fee?: number;
    notes?: string;
  }
): Promise<{ id: number; old_stage: string; new_stage: string; success: boolean }> {
  const response = await client.post(`/buyers/deals/${dealId}/stage`, {
    stage,
    ...options,
  });
  return response.data;
}

export async function getBuyerPipeline(
  stage?: BuyerDealStage,
  limit: number = 100
): Promise<BuyerPipelineResponse> {
  const response = await client.get<BuyerPipelineResponse>('/buyers/pipeline', {
    params: { stage, limit },
  });
  return response.data;
}

export default {
  createBuyer,
  getBuyers,
  getBuyer,
  updateBuyer,
  deleteBuyer,
  updateBuyerPOF,
  getBuyerDeals,
  getBuyerStatistics,
  matchBuyersToLead,
  sendBuyerBlast,
  previewBuyerBlast,
  getDealsForLead,
  updateDealStage,
  getBuyerPipeline,
};

