/**
 * Conversations API - Inbox Thread Management
 * 
 * Derives threads from outreach history.
 * Every lead with outreach = one conversation thread.
 */
import { apiClient } from './client';

export interface ConversationMessage {
  id: number;
  direction: 'inbound' | 'outbound';
  body: string;
  sent_at: string | null;
  status: string;
  classification: string | null;
}

export interface ConversationThread {
  id: number;
  lead_id: number;
  owner_name: string;
  owner_phone: string | null;
  parcel_id: string;
  parish: string;
  property_address: string;
  motivation_score: number;
  pipeline_stage: string;
  classification: 'YES' | 'NO' | 'MAYBE' | 'OTHER' | null;
  last_message: string;
  last_message_direction: 'inbound' | 'outbound';
  last_message_at: string | null;
  unread: boolean;
  message_count: number;
  has_reply: boolean;
}

export interface ConversationDetail extends ConversationThread {
  messages: ConversationMessage[];
}

export interface ConversationStats {
  total_threads: number;
  unread: number;
  yes_queue: number;
  maybe_queue: number;
  pending: number;
}

export interface ThreadsResponse {
  threads: ConversationThread[];
  total: number;
  limit: number;
  offset: number;
  filters: {
    market: string | null;
    filter: string;
    search: string | null;
  };
}

export type ThreadFilter = 'all' | 'unread' | 'yes' | 'maybe' | 'pending';

/**
 * Get conversation threads
 */
export async function getConversationThreads(params: {
  market?: string;
  filter?: ThreadFilter;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<ThreadsResponse> {
  const response = await apiClient.get<ThreadsResponse>('/conversations/threads', { params });
  return response.data;
}

/**
 * Get conversation detail with messages
 */
export async function getConversationDetail(leadId: number): Promise<ConversationDetail> {
  const response = await apiClient.get<ConversationDetail>(`/conversations/threads/${leadId}`);
  return response.data;
}

/**
 * Classify a conversation
 */
export async function classifyConversation(
  leadId: number,
  classification: 'YES' | 'NO' | 'MAYBE' | 'OTHER'
): Promise<{ success: boolean; lead_id: number; classification: string; pipeline_stage: string }> {
  const response = await apiClient.post(`/conversations/threads/${leadId}/classify`, {
    classification,
  });
  return response.data;
}

/**
 * Get conversation stats for inbox
 */
export async function getConversationStats(market?: string): Promise<ConversationStats> {
  const params = market ? { market } : {};
  const response = await apiClient.get<ConversationStats>('/conversations/stats', { params });
  return response.data;
}

