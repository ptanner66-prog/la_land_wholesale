import client from './client';
import type { DealSheet, CallScript, DispositionSummary } from '@/lib/types';

// =============================================================================
// Deal Sheet
// =============================================================================

export async function getDealSheet(
  leadId: number,
  forceRegenerate: boolean = false
): Promise<DealSheet> {
  const response = await client.get<DealSheet>(`/dispo/dealsheet/${leadId}`, {
    params: { force_regenerate: forceRegenerate },
  });
  return response.data;
}

// =============================================================================
// Call Script
// =============================================================================

export async function getCallScript(leadId: number): Promise<CallScript> {
  const response = await client.get<CallScript>(`/dispo/callscript/${leadId}`);
  return response.data;
}

// =============================================================================
// AI Tools
// =============================================================================

export async function getPropertyDescription(leadId: number): Promise<{
  lead_id: number;
  description: string | null;
  property_summary: {
    address: string;
    acreage: number;
    county: string;
    state: string;
    price: number;
  };
}> {
  const response = await client.get(`/dispo/ai/property-description/${leadId}`);
  return response.data;
}

export async function getNegotiationTips(leadId: number): Promise<{
  lead_id: number;
  negotiation_angle: string;
  price_justification: string;
  anchor_price: number;
  walk_away_price: number;
  objections: { objection: string; response: string }[];
}> {
  const response = await client.get(`/dispo/ai/negotiation-tips/${leadId}`);
  return response.data;
}

// =============================================================================
// Disposition Summary
// =============================================================================

export async function getDispositionSummary(leadId: number): Promise<DispositionSummary> {
  const response = await client.get<DispositionSummary>(`/dispo/lead/${leadId}/disposition-summary`);
  return response.data;
}

export default {
  getDealSheet,
  getCallScript,
  getPropertyDescription,
  getNegotiationTips,
  getDispositionSummary,
};

