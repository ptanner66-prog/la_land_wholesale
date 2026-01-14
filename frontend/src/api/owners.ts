import client from './client';
import type { Owner, MarketCode } from '@/lib/types';

interface GetOwnersParams {
  market?: MarketCode;
  limit?: number;
  offset?: number;
}

export async function getOwners(params: GetOwnersParams = {}): Promise<Owner[]> {
  const response = await client.get<Owner[]>('/owners', { params });
  return response.data;
}

export async function getOwnerById(ownerId: number): Promise<Owner> {
  const response = await client.get<Owner>(`/owners/${ownerId}`);
  return response.data;
}

export default {
  getOwners,
  getOwnerById,
};
