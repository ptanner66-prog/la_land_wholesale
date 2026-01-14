import client from './client';
import type { MarketCode } from '@/lib/types';

export interface Alert {
  type: 'hot_lead' | 'high_score' | 'followup_due';
  priority: 'high' | 'medium' | 'low';
  lead_id: number;
  title: string;
  description: string;
  market_code: MarketCode;
  created_at: string | null;
}

export interface AlertsResponse {
  total: number;
  alerts: Alert[];
  counts: {
    hot_leads: number;
    high_score: number;
    followups_due: number;
  };
}

export async function getAlerts(
  market?: MarketCode,
  limit: number = 10
): Promise<AlertsResponse> {
  const response = await client.get<AlertsResponse>('/automation/alerts', {
    params: { market, limit },
  });
  return response.data;
}

export default {
  getAlerts,
};

