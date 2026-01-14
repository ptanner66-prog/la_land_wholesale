import client from './client';
import type { MarketCode, MarketConfig, MarketStats } from '@/lib/types';

export async function getAllMarkets(): Promise<MarketConfig[]> {
  const response = await client.get<MarketConfig[]>('/markets');
  return response.data;
}

export async function getMarketCodes(): Promise<MarketCode[]> {
  const response = await client.get<MarketCode[]>('/markets/codes');
  return response.data;
}

export async function getMarketConfig(marketCode: MarketCode): Promise<MarketConfig> {
  const response = await client.get<MarketConfig>(`/markets/${marketCode}`);
  return response.data;
}

export async function getMarketStats(marketCode: MarketCode): Promise<MarketStats> {
  const response = await client.get<MarketStats>(`/markets/${marketCode}/stats`);
  return response.data;
}

/**
 * Get all markets (alias for getAllMarkets)
 */
export async function getMarkets(): Promise<MarketConfig[]> {
  const response = await client.get<MarketConfig[]>('/markets');
  return response.data;
}

/**
 * Get a single market by ID
 */
export async function getMarket(id: number): Promise<MarketConfig> {
  const response = await client.get<MarketConfig>(`/markets/${id}`);
  return response.data;
}

export default {
  getAllMarkets,
  getMarketCodes,
  getMarketConfig,
  getMarketStats,
  getMarkets,
  getMarket,
};
