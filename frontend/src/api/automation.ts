import client from './client';
import type {
  MarketCode,
  RunFollowupsResult,
  NightlyPipelineResult,
  AlertConfig,
} from '@/lib/types';

interface RunFollowupsParams {
  market?: MarketCode;
  dry_run?: boolean;
  limit?: number;
}

export async function runFollowups(params: RunFollowupsParams = {}): Promise<RunFollowupsResult> {
  const response = await client.post<RunFollowupsResult>('/automation/run_followups', params);
  return response.data;
}

export async function runNightlyPipeline(
  markets?: MarketCode[],
  dryRun: boolean = false
): Promise<NightlyPipelineResult> {
  const response = await client.post<NightlyPipelineResult>('/automation/run_nightly', null, {
    params: { markets, dry_run: dryRun },
  });
  return response.data;
}

export async function getAlertConfigs(): Promise<AlertConfig[]> {
  const response = await client.get<AlertConfig[]>('/automation/alerts/config');
  return response.data;
}

export async function getAlertConfig(marketCode: MarketCode): Promise<AlertConfig> {
  const response = await client.get<AlertConfig>(`/automation/alerts/config/${marketCode}`);
  return response.data;
}

export async function updateAlertConfig(
  marketCode: MarketCode,
  config: Partial<AlertConfig>
): Promise<AlertConfig> {
  const response = await client.put<AlertConfig>(`/automation/alerts/config/${marketCode}`, config);
  return response.data;
}

export async function sendTestAlert(marketCode: MarketCode): Promise<{
  success: boolean;
  results: { sms: boolean | null; slack: boolean | null };
}> {
  const response = await client.post('/automation/alerts/test', null, {
    params: { market: marketCode },
  });
  return response.data;
}

export default {
  runFollowups,
  runNightlyPipeline,
  getAlertConfigs,
  getAlertConfig,
  updateAlertConfig,
  sendTestAlert,
};
