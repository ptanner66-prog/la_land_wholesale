import client from './client';
import type {
  OutreachAttempt,
  OutreachStats,
  GenerateMessageResponse,
  ClassifyReplyResponse,
  FollowupDueResponse,
  SendMessageRequest,
  SendMessageResponse,
  MarketCode,
} from '@/lib/types';

interface GetOutreachHistoryParams {
  market?: MarketCode;
  lead_id?: number;
  status?: string;
  limit?: number;
  offset?: number;
}

export async function getOutreachAttempts(
  params: GetOutreachHistoryParams = {}
): Promise<OutreachAttempt[]> {
  const response = await client.get<OutreachAttempt[]>('/outreach/history', { params });
  return response.data;
}

export async function triggerOutreachBatch(
  market?: MarketCode,
  limit: number = 50,
  min_score?: number,
  _background: boolean = true
): Promise<{ message: string; limit: number; market?: string }> {
  const response = await client.post('/outreach/run', null, {
    params: { market, limit, min_score },
  });
  return response.data;
}

/**
 * Send a message to a lead.
 * 
 * FIXED: Now accepts optional message_body to send user-selected variant.
 */
export async function sendToLead(
  leadId: number,
  context: 'intro' | 'followup' | 'final' = 'intro',
  force: boolean = false,
  messageBody?: string
): Promise<SendMessageResponse> {
  const body: SendMessageRequest = {
    context,
    force,
  };

  // FIXED: Include user-selected message if provided
  if (messageBody) {
    body.message_body = messageBody;
  }

  const response = await client.post<SendMessageResponse>(`/outreach/send/${leadId}`, body);
  return response.data;
}

export async function sendReply(
  leadId: number,
  message: string
): Promise<{ success: boolean; message_sid?: string; message: string }> {
  const response = await client.post(`/outreach/reply/${leadId}`, { message });
  return response.data;
}

export async function getOutreachStatistics(
  market?: MarketCode,
  days: number = 7
): Promise<OutreachStats> {
  const response = await client.get<OutreachStats>('/outreach/stats', {
    params: { market, days },
  });
  return response.data;
}

export async function classifyReply(text: string): Promise<ClassifyReplyResponse> {
  const response = await client.post<ClassifyReplyResponse>('/outreach/classify_reply', {
    text,
  });
  return response.data;
}

export async function generateMessage(
  lead_id: number,
  context: 'intro' | 'followup' | 'final'
): Promise<GenerateMessageResponse> {
  const response = await client.post<GenerateMessageResponse>('/outreach/generate_message', {
    lead_id,
    context,
  });
  return response.data;
}

export async function getFollowupsDue(
  market?: MarketCode,
  limit: number = 50
): Promise<FollowupDueResponse> {
  const response = await client.get<FollowupDueResponse>('/outreach/followup_due', {
    params: { market, limit },
  });
  return response.data;
}

export default {
  getOutreachAttempts,
  triggerOutreachBatch,
  sendToLead,
  sendReply,
  getOutreachStatistics,
  classifyReply,
  generateMessage,
  getFollowupsDue,
};
