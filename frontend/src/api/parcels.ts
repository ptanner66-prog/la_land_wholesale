import client from './client';
import type { Parcel, MarketCode } from '@/lib/types';

interface GetParcelsParams {
  market?: MarketCode;
  is_adjudicated?: boolean;
  limit?: number;
  offset?: number;
}

export async function getParcels(params: GetParcelsParams = {}): Promise<Parcel[]> {
  const response = await client.get<Parcel[]>('/parcels', { params });
  return response.data;
}

export async function getParcelById(parcelId: string): Promise<Parcel> {
  const response = await client.get<Parcel>(`/parcels/${parcelId}`);
  return response.data;
}

export default {
  getParcels,
  getParcelById,
};
