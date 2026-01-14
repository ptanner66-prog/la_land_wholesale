# Production Safety Summary - LA Land Wholesale

## Date: December 17, 2025

## Executive Summary

This document summarizes the production hardening changes made to eliminate trust violations that could cause operators to misidentify properties, quote wrong land, trust incorrect maps, or believe unverified data is authoritative.

---

## 🚨 CRITICAL TRUST RULES (NON-NEGOTIABLE)

1. **Mailing address must NEVER be promoted as property location**
2. **Property location must ONLY come from parcel/GIS truth**
3. **If data is missing, the UI must say so explicitly**
4. **No silent fallbacks, no "best guess" maps, no demo shortcuts**
5. **Every displayed field must have a clear source of truth**

---

## Trust Violations Found and Resolved

### 1. Address/Location Trust Violations

#### ISSUE: Mailing Address Shown as Property Location
**What was dangerous:**
- The LeadDetail page header showed `lead.situs_address || lead.city` - this could fall back to city from mailing data
- When no situs address existed, the UI silently fell back without warning
- Users could mistake a house address (where owner lives) for the vacant land location

**How it was fixed:**
- `LeadDetail.tsx` header now shows explicit "No Situs Address" badge when situs is missing
- Property location section shows "Parcel {id}" instead of any fallback
- Added explicit warning text: "⚠️ No situs address on file. Use parcel ID for property identification."

**Why it can't regress:**
- `address_utils.py` now has `assert_property_location_not_mailing()` guard
- Test suite `test_trust_violations.py` includes tests that fail if mailing address leaks into property location
- `DisplayLocation.address_line1` is now explicitly `None` when no situs exists

---

### 2. Map Trust Violations

#### ISSUE: Maps Could Render from Unverified Data
**What was dangerous:**
- Maps could potentially geocode from mailing address if no coordinates existed
- No indication to user whether map location was verified or guessed
- Silent fallbacks could show wrong property location

**How it was fixed:**
- `PropertyMap.tsx` now shows explicit trust badges: "Verified Coordinates" or "Location Not Verified"
- Map query (`map_query`) returns `None` if no coordinates or situs - no guessing
- Fallback state shows clear warning: "Location Not Verified" with parcel ID
- Added "Open Parish Assessor / GIS" button for manual verification

**Why it can't regress:**
- `DisplayLocation.map_query` property returns `None` when no verified data exists
- `assert_map_not_from_mailing()` guard in backend
- `PropertyMap` component explicitly checks `hasCoordinates` before rendering pin

---

### 3. Offer/Valuation Trust Violations

#### ISSUE: Offers Computed with Missing Data
**What was dangerous:**
- Per-acre pricing could divide by zero or missing acreage
- Confidence indicators showed "high" even with incomplete data
- Users could make offers without knowing critical data was missing

**How it was fixed:**
- `offer_helper.py` now has explicit `OfferConfidence` enum: HIGH, MEDIUM, LOW, CANNOT_COMPUTE
- `can_make_offer` flag prevents offers when land value is missing
- `missing_data_summary` provides human-readable explanation of what's missing
- Per-acre prices return `None` (not zero) when acreage is missing
- Justification bullets now include "Acreage unknown - per-acre pricing unavailable"

**Why it can't regress:**
- `assert_offer_not_from_incomplete_data()` guard fails if HIGH confidence with missing data
- `assert_per_acre_not_from_missing_acreage()` guard fails if per-acre computed without acreage
- Test suite verifies confidence levels match data availability

---

### 4. Data Trust Level System

#### NEW: Explicit Trust Hierarchy
All data now has explicit trust levels:

| Trust Level | Source | Usage |
|-------------|--------|-------|
| `VERIFIED_GIS` | Parcel coordinates from GIS | Maps, property identification |
| `PARCEL_RECORD` | Tax roll / parcel data | Situs address, valuations |
| `DERIVED` | Computed from parcel ID | Fallback display only |
| `OWNER_PROVIDED` | Mailing address, contact info | Mail outreach ONLY |
| `MISSING` | No data available | Show explicit warning |

**UI Implementation:**
- Property Location card shows trust badge (green for verified, yellow for unverified)
- Mailing Address card is visually distinct with "Mail Only" badge
- Warning: "🚫 Never use this address for property identification or mapping"

---

## Files Changed

### Backend
| File | Changes |
|------|---------|
| `src/core/address_utils.py` | Complete rewrite with DataTrust enum, DataWarning enum, explicit guards |
| `src/services/offer_helper.py` | Added OfferConfidence enum, can_make_offer flag, missing_data_summary |

### Frontend
| File | Changes |
|------|---------|
| `frontend/src/pages/LeadDetail.tsx` | Fixed header fallback, added explicit situs warnings |
| `frontend/src/pages/CallPrepPack.tsx` | Added trust badges, data source labels, missing data warnings |
| `frontend/src/components/PropertyMap.tsx` | Added trust indicators, explicit "not verified" state |
| `frontend/src/api/callPrep.ts` | Updated types for new trust/warning fields |

### Tests
| File | Purpose |
|------|---------|
| `tests/test_trust_violations.py` | Regression tests for all trust rules |

---

## Regression Guards

### Backend Guards (`address_utils.py`, `offer_helper.py`)
```python
# Fails if mailing address used as property location
assert_property_location_not_mailing(property_location, mailing_address)

# Fails if map query contains mailing data
assert_map_not_from_mailing(property_location, mailing_address)

# Fails if HIGH confidence with incomplete data
assert_offer_not_from_incomplete_data(offer)

# Fails if per-acre price computed without acreage
assert_per_acre_not_from_missing_acreage(offer)
```

### Test Suite (`test_trust_violations.py`)
- `TestMailingAddressNeverPropertyLocation` - 3 tests
- `TestMapNeverFromMailing` - 4 tests
- `TestOfferNeverWithMissingData` - 5 tests
- `TestConfidenceAccurate` - 3 tests
- `TestDataTrustLevels` - 4 tests
- `TestRegressionGuards` - 3 tests

---

## UI Behavior Summary

### When Situs Address Exists
- Property Location shows address with green "Verified" badge
- Map renders with pin at coordinates (if available)
- Offer shows full per-acre pricing

### When Situs Address Missing
- Property Location shows "Parcel {id}, {Parish} Parish"
- Yellow "No Situs Address" badge
- Warning text: "⚠️ No situs address on file. Use parcel ID for property identification."
- Map shows "Location Not Verified" with search buttons
- Per-acre pricing shows "unavailable - acreage data missing"

### When Land Value Missing
- Offer shows "Cannot compute offer"
- Red warning: "No assessed land value on record"
- `can_make_offer: false`

---

## Verification Checklist

✅ Mailing address never appears in Property Location section  
✅ Maps show trust indicator (verified/unverified)  
✅ Missing situs shows explicit warning badge  
✅ Offer confidence matches data availability  
✅ Per-acre pricing is None when acreage missing  
✅ All regression guards pass  
✅ TypeScript compiles without errors  

---

## Running Tests

```bash
# Run trust violation tests
cd la_land_wholesale
pytest tests/test_trust_violations.py -v

# Run frontend type check
cd frontend
npx tsc --noEmit
```

---

## Conclusion

This system now treats **incorrect confidence as a critical bug**. Every piece of data has an explicit trust level, every missing field has an explicit warning, and regression guards prevent future violations.

The platform now behaves like a **production wholesaling OS**, not a prototype.

