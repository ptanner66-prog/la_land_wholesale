/**
 * Active Market API - Area locking for all operations
 */
import { apiClient } from './client';

export interface ActiveMarket {
  active: boolean;
  state: string | null;
  parish: string | null;
  display_name: string | null;
  market_code: string | null;
}

export interface ParishInfo {
  parish: string;
  lead_count: number;
}

export interface ParishesByState {
  [state: string]: ParishInfo[];
}

export interface ParishSummary {
  state: string;
  parish: string;
  total_leads: number;
  hot_leads: number;
  contact_leads: number;
  has_sales_data: boolean;
}

export interface SetActiveMarketResponse {
  success: boolean;
  active_market: {
    state: string;
    parish: string;
    display_name: string;
    market_code: string;
  };
  summary: ParishSummary;
}

/**
 * Get the currently active market
 */
export async function getActiveMarket(): Promise<ActiveMarket> {
  const response = await apiClient.get<ActiveMarket>('/active-market');
  return response.data;
}

/**
 * Set the active market (working area)
 */
export async function setActiveMarket(state: string, parish: string): Promise<SetActiveMarketResponse> {
  const response = await apiClient.post<SetActiveMarketResponse>('/active-market', {
    state,
    parish,
  });
  return response.data;
}

/**
 * Clear the active market
 */
export async function clearActiveMarket(): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete<{ success: boolean; message: string }>('/active-market');
  return response.data;
}

/**
 * Get all available parishes grouped by state
 */
export async function getAvailableParishes(state?: string): Promise<{
  parishes_by_state: ParishesByState;
  total_states: number;
}> {
  const params = state ? { state } : {};
  const response = await apiClient.get<{
    parishes_by_state: ParishesByState;
    total_states: number;
  }>('/active-market/parishes', { params });
  return response.data;
}

/**
 * Get summary for the active market
 */
export async function getActiveMarketSummary(): Promise<{
  active_market: ActiveMarket;
  summary: ParishSummary;
}> {
  const response = await apiClient.get<{
    active_market: ActiveMarket;
    summary: ParishSummary;
  }>('/active-market/summary');
  return response.data;
}

