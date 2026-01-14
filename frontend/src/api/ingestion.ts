import client from './client'
import type { IngestionResult } from '@/lib/types'

const BASE_PATH = '/ingest'

/**
 * Get ingestion status
 */
export async function getIngestionStatus(): Promise<Record<string, unknown>> {
  const response = await client.get<Record<string, unknown>>(`${BASE_PATH}/status`)
  return response.data
}

/**
 * Run full ingestion pipeline
 */
export async function runFullIngestion(): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/full`)
  return response.data
}

/**
 * Ingest tax roll data
 */
export async function ingestTaxRoll(filePath?: string): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/tax-roll`, { file_path: filePath })
  return response.data
}

/**
 * Ingest GIS data
 */
export async function ingestGis(filePath?: string): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/gis`, { file_path: filePath })
  return response.data
}

/**
 * Ingest adjudicated properties
 */
export async function ingestAdjudicated(filePath?: string): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/adjudicated`, { file_path: filePath })
  return response.data
}

/**
 * Get recent ingestion history
 */
export async function getIngestionHistory(): Promise<IngestionResult[]> {
  const response = await client.get<IngestionResult[]>(`${BASE_PATH}/history`)
  return response.data
}

/**
 * Get ingestion summary/statistics
 */
export async function getIngestionSummary(): Promise<Record<string, unknown>> {
  const response = await client.get<Record<string, unknown>>(`${BASE_PATH}/statistics`)
  return response.data
}

/**
 * Universal ingestion - works with any parish tax roll
 */
export interface UniversalIngestionRequest {
  file_path: string
  parish_override?: string
  dry_run?: boolean
}

export async function ingestUniversal(request: UniversalIngestionRequest): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/universal`, request)
  return response.data
}

/**
 * Ingest auction properties
 */
export async function ingestAuctions(filePath: string): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/auctions`, null, {
    params: { file_path: filePath }
  })
  return response.data
}

/**
 * Ingest expired listings
 */
export async function ingestExpiredListings(filePath: string): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/expired`, null, {
    params: { file_path: filePath }
  })
  return response.data
}

/**
 * Ingest tax delinquent list
 */
export async function ingestTaxDelinquent(filePath: string): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/tax-delinquent`, null, {
    params: { file_path: filePath }
  })
  return response.data
}

/**
 * Ingest absentee owner list
 */
export async function ingestAbsenteeOwners(filePath: string): Promise<IngestionResult> {
  const response = await client.post<IngestionResult>(`${BASE_PATH}/absentee`, null, {
    params: { file_path: filePath }
  })
  return response.data
}

