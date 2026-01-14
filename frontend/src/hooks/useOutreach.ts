import { useState, useEffect, useCallback } from 'react';
import { getOutreachAttempts, getOutreachStatistics, getFollowupsDue } from '@/api/outreach';
import type { OutreachAttempt, OutreachStats, FollowupDueResponse, MarketCode } from '@/lib/types';

interface UseOutreachOptions {
  market?: MarketCode;
  leadId?: number;
  status?: string;
  limit?: number;
  autoFetch?: boolean;
}

export function useOutreach(options: UseOutreachOptions = {}) {
  const { market, leadId, status, limit = 100, autoFetch = true } = options;

  const [attempts, setAttempts] = useState<OutreachAttempt[]>([]);
  const [stats, setStats] = useState<OutreachStats | null>(null);
  const [followupsDue, setFollowupsDue] = useState<FollowupDueResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchAttempts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getOutreachAttempts({
        market,
        lead_id: leadId,
        status,
        limit,
      });
      setAttempts(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch outreach attempts'));
    } finally {
      setLoading(false);
    }
  }, [market, leadId, status, limit]);

  const fetchStats = useCallback(async () => {
    try {
      const data = await getOutreachStatistics(market, 7);
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch outreach stats:', err);
    }
  }, [market]);

  const fetchFollowupsDue = useCallback(async () => {
    try {
      const data = await getFollowupsDue(market, 50);
      setFollowupsDue(data);
    } catch (err) {
      console.error('Failed to fetch followups due:', err);
    }
  }, [market]);

  const refresh = useCallback(async () => {
    await Promise.all([fetchAttempts(), fetchStats(), fetchFollowupsDue()]);
  }, [fetchAttempts, fetchStats, fetchFollowupsDue]);

  useEffect(() => {
    if (autoFetch) {
      refresh();
    }
  }, [autoFetch, refresh]);

  return {
    attempts,
    stats,
    followupsDue,
    loading,
    error,
    refresh,
    fetchAttempts,
    fetchStats,
    fetchFollowupsDue,
  };
}

export default useOutreach;
