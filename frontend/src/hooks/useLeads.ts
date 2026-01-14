import { useState, useEffect, useCallback } from 'react';
import { getLeads, getLeadStatistics, searchLeads } from '@/api/leads';
import type { LeadSummary, LeadStatistics, MarketCode, PipelineStage } from '@/lib/types';

interface UseLeadsOptions {
  market?: MarketCode;
  pipelineStage?: PipelineStage;
  minScore?: number;
  status?: string;
  tcpaSafeOnly?: boolean;
  orderBy?: 'score_desc' | 'score_asc' | 'created_desc' | 'created_asc';
  limit?: number;
  offset?: number;
  autoFetch?: boolean;
}

export function useLeads(options: UseLeadsOptions = {}) {
  const {
    market,
    pipelineStage,
    minScore,
    status,
    tcpaSafeOnly,
    orderBy = 'score_desc',
    limit = 100,
    offset = 0,
    autoFetch = true,
  } = options;

  const [leads, setLeads] = useState<LeadSummary[]>([]);
  const [statistics, setStatistics] = useState<LeadStatistics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getLeads({
        market,
        pipeline_stage: pipelineStage,
        min_score: minScore,
        status,
        tcpa_safe_only: tcpaSafeOnly,
        order_by: orderBy,
        limit,
        offset,
      });
      setLeads(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch leads'));
    } finally {
      setLoading(false);
    }
  }, [market, pipelineStage, minScore, status, tcpaSafeOnly, orderBy, limit, offset]);

  const fetchStatistics = useCallback(async () => {
    try {
      const data = await getLeadStatistics(market);
      setStatistics(data);
    } catch (err) {
      console.error('Failed to fetch lead statistics:', err);
    }
  }, [market]);

  const search = useCallback(
    async (query: string) => {
      setLoading(true);
      setError(null);
      try {
        const data = await searchLeads(query, market, limit);
        setLeads(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Search failed'));
      } finally {
        setLoading(false);
      }
    },
    [market, limit]
  );

  const refresh = useCallback(async () => {
    await Promise.all([fetchLeads(), fetchStatistics()]);
  }, [fetchLeads, fetchStatistics]);

  useEffect(() => {
    if (autoFetch) {
      refresh();
    }
  }, [autoFetch, refresh]);

  return {
    leads,
    statistics,
    loading,
    error,
    refresh,
    fetchLeads,
    fetchStatistics,
    search,
  };
}

export default useLeads;
