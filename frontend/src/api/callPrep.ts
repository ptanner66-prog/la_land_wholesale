/**
 * Call Prep Pack API - PRODUCTION HARDENED
 * 
 * Everything needed to quote and close a lead:
 * - Location (property + mailing, clearly separated with trust indicators)
 * - Offer range with justification and explicit warnings
 * - Call script with live injection
 * 
 * CRITICAL: Property location and mailing address are SEPARATE.
 * Never confuse them.
 */
import { apiClient } from './client';

// Data Trust Levels
export type DataTrust = 'verified_gis' | 'parcel_record' | 'derived' | 'owner_provided' | 'missing';

// Data Warnings
export type DataWarning = 
  | 'no_situs_address' 
  | 'no_coordinates' 
  | 'no_parcel' 
  | 'no_geometry' 
  | 'geocode_needed' 
  | 'mailing_only' 
  | 'unverified_location';

// Offer Warnings
export type OfferWarning = 
  | 'missing_land_value'
  | 'missing_acreage'
  | 'zero_land_value'
  | 'adjudicated_title_risk'
  | 'tax_delinquent'
  | 'no_parcel_data'
  | 'estimate_only';

// Types
export interface PropertyLocation {
  address_line1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  parish: string;
  parcel_id: string;
  latitude: number | null;
  longitude: number | null;
  data_trust: DataTrust;
  has_situs_address: boolean;
  has_coordinates: boolean;
  has_geometry: boolean;
  full_address: string;
  short_address: string;
  location_descriptor: string;
  map_query: string | null;
  assessor_search_query: string;
  can_show_map: boolean;
  map_trust_level: string;
  missing_data_message: string | null;
  warnings: DataWarning[];
}

export interface MailingAddress {
  line1: string | null;
  line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  raw_address: string | null;
  display: string;
  is_available: boolean;
  data_trust: DataTrust;
  _warning?: string;
}

export interface LocationSummary {
  property_location: PropertyLocation;
  mailing_address: MailingAddress;
  _trust_warning?: string;
}

export interface JustificationBullet {
  factor: string;
  description: string;
  impact: 'increase' | 'decrease' | 'neutral';
}

export type OfferConfidence = 'high' | 'medium' | 'low' | 'cannot_compute';

export interface OfferRange {
  low_offer: number;
  high_offer: number;
  midpoint: number;
  range_display: string;
  land_value: number | null;
  acreage: number | null;
  discount_low: number;
  discount_high: number;
  price_per_acre_low: number | null;
  price_per_acre_high: number | null;
  per_acre_display: string | null;
  justifications: JustificationBullet[];
  confidence: OfferConfidence;
  confidence_reason: string;
  warnings: OfferWarning[];
  missing_data_summary: string | null;
  can_make_offer: boolean;
  cannot_offer_reason: string | null;
}

export interface ObjectionHandler {
  objection: string;
  response: string;
}

export interface CallScript {
  lead_id: number;
  owner_name: string;
  property_location: string;
  acreage: number | null;
  parish: string;
  offer_range: OfferRange;
  opening: string;
  discovery: string;
  price_discussion: string;
  objection_handlers: ObjectionHandler[];
  closing: string;
}

export interface ParcelSnapshot {
  parcel_id: string | null;
  parish: string | null;
  acreage: number | null;
  land_value: number | null;
  is_adjudicated: boolean;
  years_tax_delinquent: number;
}

export interface MapData {
  has_coordinates: boolean;
  latitude: number | null;
  longitude: number | null;
  geocode_needed: boolean;
}

export interface OwnerInfo {
  name: string;
  phone: string | null;
  email: string | null;
  is_tcpa_safe: boolean;
}

export interface CallPrepPack {
  lead_id: number;
  motivation_score: number;
  pipeline_stage: string;
  owner: OwnerInfo;
  location: LocationSummary;
  parcel: ParcelSnapshot;
  offer: OfferRange;
  script: CallScript;
  map: MapData;
}

/**
 * Get normalized location for a lead
 */
export async function getLeadLocation(leadId: number): Promise<LocationSummary> {
  const response = await apiClient.get<LocationSummary>(`/call-prep/${leadId}/location`);
  return response.data;
}

/**
 * Get computed offer range for a lead
 */
export async function getOfferRange(
  leadId: number,
  discountLow?: number,
  discountHigh?: number
): Promise<OfferRange> {
  const params: Record<string, number> = {};
  if (discountLow !== undefined) params.discount_low = discountLow;
  if (discountHigh !== undefined) params.discount_high = discountHigh;
  
  const response = await apiClient.get<OfferRange>(`/call-prep/${leadId}/offer`, { params });
  return response.data;
}

/**
 * Get call script for a lead
 */
export async function getCallScript(
  leadId: number,
  discountLow?: number,
  discountHigh?: number
): Promise<CallScript> {
  const params: Record<string, number> = {};
  if (discountLow !== undefined) params.discount_low = discountLow;
  if (discountHigh !== undefined) params.discount_high = discountHigh;
  
  const response = await apiClient.get<CallScript>(`/call-prep/${leadId}/script`, { params });
  return response.data;
}

/**
 * Get complete Call Prep Pack for a lead
 */
export async function getCallPrepPack(
  leadId: number,
  discountLow?: number,
  discountHigh?: number
): Promise<CallPrepPack> {
  const params: Record<string, number> = {};
  if (discountLow !== undefined) params.discount_low = discountLow;
  if (discountHigh !== undefined) params.discount_high = discountHigh;
  
  const response = await apiClient.get<CallPrepPack>(`/call-prep/${leadId}/prep-pack`, { params });
  return response.data;
}
