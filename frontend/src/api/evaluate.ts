import client from './client';

// =============================================================================
// Deal Analysis Types
// =============================================================================

export interface DealAnalysisRequest {
  purchase_price: number;
}

export interface ManualDealAnalysisRequest {
  parcel_id?: number;
  acres: number;
  zoning?: string;
  estimated_value?: number;
  comps?: number[];
  purchase_price?: number;
  market_code?: string;
  motivation_score?: number;
  is_adjudicated?: boolean;
}

export interface ManualDealAnalysisResponse {
  arv: number;
  mao: number;
  assignment_fee: number;
  offer_range: [number, number];
  confidence: number;
  notes: string[];
  full_analysis?: Record<string, unknown>;
}

export interface AssignmentFeeResult {
  lead_id: number;
  purchase_price: number;
  retail_value: number;
  buyer_count: number;
  fee: {
    recommended_fee: number;
    min_fee: number;
    max_fee: number;
    confidence: string;
    reasoning: string;
  };
}

export interface DealAnalysisResult {
  lead_id: number;
  analysis: {
    purchase_price: number;
    retail_value: number;
    gross_margin: number;
    margin_percentage: number;
    roi_percentage: number;
    recommended_assignment_fee: number;
    min_assignment_fee: number;
    max_assignment_fee: number;
    deal_quality: string;
    risk_level: string;
    buyer_demand: string;
    summary: string;
  };
}

export interface BuyerMatch {
  buyer_id: number;
  buyer_name: string;
  match_percentage: number;
  match_reasons: string[];
  vip: boolean;
  pof_verified: boolean;
}

export interface BuyerMatchesResult {
  lead_id: number;
  total_matches: number;
  matches: BuyerMatch[];
}

// =============================================================================
// Deal Calculator / Analysis
// =============================================================================

/**
 * Calculate optimal assignment fee for a lead
 */
export async function getAssignmentFee(
  leadId: number,
  purchasePrice: number
): Promise<AssignmentFeeResult> {
  const response = await client.get<AssignmentFeeResult>(
    `/dispo/assignment-fee/${leadId}`,
    {
      params: { purchase_price: purchasePrice },
    }
  );
  return response.data;
}

/**
 * Get complete deal analysis including margins and ROI
 */
export async function getDealAnalysis(
  leadId: number,
  purchasePrice: number
): Promise<DealAnalysisResult> {
  const response = await client.get<DealAnalysisResult>(
    `/dispo/deal-analysis/${leadId}`,
    {
      params: { purchase_price: purchasePrice },
    }
  );
  return response.data;
}

/**
 * Get matched buyers for a lead
 */
export async function getBuyerMatches(
  leadId: number,
  offerPrice?: number,
  minScore: number = 30,
  limit: number = 20
): Promise<BuyerMatchesResult> {
  const response = await client.get<BuyerMatchesResult>(
    `/dispo/matches/${leadId}`,
    {
      params: {
        offer_price: offerPrice,
        min_score: minScore,
        limit,
      },
    }
  );
  return response.data;
}

/**
 * Manual deal analysis without requiring a lead/parcel in the system
 */
export async function analyzeManualDeal(
  request: ManualDealAnalysisRequest
): Promise<ManualDealAnalysisResponse> {
  const response = await client.post<ManualDealAnalysisResponse>(
    '/dispo/deal',
    request
  );
  return response.data;
}

export default {
  getAssignmentFee,
  getDealAnalysis,
  getBuyerMatches,
  analyzeManualDeal,
};

