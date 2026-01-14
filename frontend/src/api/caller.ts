/**
 * Caller Sheet API - Sales-call-first workflow
 */
import { apiClient } from './client';

export type CallOutcome =
  | 'not_interested'
  | 'call_back'
  | 'interested'
  | 'no_answer'
  | 'wrong_number'
  | 'voicemail';

export interface CallerSheetLead {
  id: number;
  owner_name: string;
  phone: string;
  parcel_id: string;
  parish: string;
  acreage: number | null;
  land_value: number | null;
  motivation_score: number;
  tier: 'HOT' | 'CONTACT';
  is_adjudicated: boolean;
  years_delinquent: number;
  property_address: string | null;
  mailing_address: string | null;
  notes: string | null;
}

export interface CallerSheet {
  active_market: {
    state: string;
    parish: string;
    display_name: string;
    market_code: string;
  };
  generated_at: string;
  leads: CallerSheetLead[];
  total_eligible: number;
  hot_count: number;
  contact_count: number;
  unavailable_reason: string | null;
}

export interface LeadForCall {
  id: number;
  owner_name: string;
  phone: string | null;
  motivation_score: number;
  pipeline_stage: string;
  parcel: {
    parcel_id: string | null;
    parish: string | null;
    acreage: number | null;
    land_value: number | null;
    is_adjudicated: boolean;
    years_delinquent: number;
    property_address: string | null;
  };
  mailing_address: string | null;
  previous_calls: {
    date: string | null;
    outcome: string | null;
    notes: string | null;
  }[];
}

export interface LogOutcomeResponse {
  success: boolean;
  lead_id: number;
  outcome: string;
  pipeline_update: string | null;
  message: string;
}

/**
 * Get the caller work queue
 */
export async function getCallerSheet(limit: number = 50): Promise<CallerSheet> {
  const response = await apiClient.get<CallerSheet>('/caller/sheet', {
    params: { limit },
  });
  return response.data;
}

/**
 * Get lead details for a call
 */
export async function getLeadForCall(leadId: number): Promise<LeadForCall> {
  const response = await apiClient.get<LeadForCall>(`/caller/${leadId}`);
  return response.data;
}

/**
 * Log the outcome of a call
 */
export async function logCallOutcome(
  leadId: number,
  outcome: CallOutcome,
  notes?: string,
  callbackDate?: string
): Promise<LogOutcomeResponse> {
  const response = await apiClient.post<LogOutcomeResponse>(`/caller/${leadId}/outcome`, {
    outcome,
    notes,
    callback_date: callbackDate,
  });
  return response.data;
}

export const CALL_OUTCOME_LABELS: Record<CallOutcome, string> = {
  not_interested: 'Not Interested',
  call_back: 'Call Back Later',
  interested: 'Interested!',
  no_answer: 'No Answer',
  wrong_number: 'Wrong Number',
  voicemail: 'Left Voicemail',
};

export const CALL_OUTCOME_COLORS: Record<CallOutcome, string> = {
  not_interested: 'bg-gray-500',
  call_back: 'bg-yellow-500',
  interested: 'bg-green-500',
  no_answer: 'bg-blue-500',
  wrong_number: 'bg-red-500',
  voicemail: 'bg-purple-500',
};

