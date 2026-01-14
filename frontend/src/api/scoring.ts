import client from './client'
import type { ScoringResult } from '@/lib/types'

const BASE_PATH = '/scoring'

/**
 * Get scoring configuration
 */
export async function getScoringConfig(): Promise<Record<string, unknown>> {
  const response = await client.get<Record<string, unknown>>(`/config/scoring`)
  return response.data
}

/**
 * Run scoring for all leads
 */
export async function runScoring(): Promise<ScoringResult> {
  const response = await client.post<ScoringResult>(`${BASE_PATH}/run`)
  return response.data
}

/**
 * Score a specific lead
 */
export async function scoreLead(leadId: number): Promise<{ lead_id: number; score: number }> {
  const response = await client.post<{ lead_id: number; score: number }>(`${BASE_PATH}/lead/${leadId}`)
  return response.data
}

/**
 * Get score distribution
 */
export async function getScoreDistribution(): Promise<Record<string, number>> {
  const response = await client.get<Record<string, number>>(`${BASE_PATH}/distribution`)
  return response.data
}

