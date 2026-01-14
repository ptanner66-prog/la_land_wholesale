/**
 * PropertyMap - Leaflet/OpenStreetMap based map component
 * 
 * PRODUCTION HARDENED - No silent fallbacks, no guessing
 * 
 * No API keys required.
 * 
 * Trust hierarchy (STRICTLY ENFORCED):
 * 1. Parcel coordinates (lat/lng) → pin (HIGHEST TRUST)
 * 2. Parcel polygon (GIS) → draw + fit
 * 3. Situs address (from parcel records) → can search
 * 4. No geometry → show explicit warning + actionable buttons
 * 
 * CRITICAL: Mailing address is NEVER used for map queries
 */
import { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polygon, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ExternalLink, Search, AlertTriangle, CheckCircle } from 'lucide-react';

// Fix Leaflet default marker icons
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

// @ts-ignore
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

interface PropertyMapProps {
  latitude?: number | null;
  longitude?: number | null;
  parcelId: string;
  parish: string;
  /** 
   * Situs address - MUST be from parcel records, never mailing address.
   * Pass undefined if no situs address exists.
   */
  situsAddress?: string | null;
  geometryWkt?: string | null;
  className?: string;
}

// Component to fit bounds when we have a polygon
function FitBounds({ bounds }: { bounds: L.LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [20, 20] });
  }, [map, bounds]);
  return null;
}

// Parse simple WKT polygon to coordinates
function parseWktPolygon(wkt: string): [number, number][] | null {
  try {
    // Match POLYGON((lon lat, lon lat, ...))
    const match = wkt.match(/POLYGON\s*\(\(([^)]+)\)\)/i);
    if (!match) return null;
    
    const coordStr = match[1];
    const coords = coordStr.split(',').map(pair => {
      const [lon, lat] = pair.trim().split(/\s+/).map(Number);
      return [lat, lon] as [number, number]; // Leaflet uses [lat, lng]
    });
    
    return coords.length > 2 ? coords : null;
  } catch {
    return null;
  }
}

// Calculate centroid of polygon
function getCentroid(coords: [number, number][]): [number, number] {
  const sum = coords.reduce(
    (acc, [lat, lng]) => [acc[0] + lat, acc[1] + lng],
    [0, 0]
  );
  return [sum[0] / coords.length, sum[1] / coords.length];
}

export function PropertyMap({
  latitude,
  longitude,
  parcelId,
  parish,
  situsAddress,
  geometryWkt,
  className = 'h-64',
}: PropertyMapProps) {
  // Parse geometry if available
  const polygonCoords = useMemo(() => {
    if (geometryWkt) {
      return parseWktPolygon(geometryWkt);
    }
    return null;
  }, [geometryWkt]);

  // Determine what we can show - STRICT trust hierarchy
  const hasCoordinates = latitude != null && longitude != null;
  const hasPolygon = polygonCoords && polygonCoords.length > 2;
  const hasSitusAddress = situsAddress != null && situsAddress.trim() !== '';
  
  // Determine trust level for display
  const trustLevel = useMemo(() => {
    if (hasCoordinates) return 'verified';
    if (hasPolygon) return 'polygon';
    if (hasSitusAddress) return 'situs';
    return 'none';
  }, [hasCoordinates, hasPolygon, hasSitusAddress]);
  
  // Calculate center for map - ONLY from verified sources
  const center = useMemo((): [number, number] => {
    if (hasCoordinates) {
      return [latitude!, longitude!];
    }
    if (hasPolygon) {
      return getCentroid(polygonCoords!);
    }
    // Default to Louisiana center - but we won't show a map without verified data
    return [30.9843, -91.9623];
  }, [hasCoordinates, hasPolygon, latitude, longitude, polygonCoords]);

  // Google Maps search URL - ONLY from verified parcel data
  const googleMapsUrl = useMemo(() => {
    if (hasCoordinates) {
      // HIGHEST TRUST: Direct coordinates
      return `https://www.google.com/maps?q=${latitude},${longitude}`;
    }
    if (hasSitusAddress) {
      // MEDIUM TRUST: Situs address from parcel records
      return `https://www.google.com/maps/search/${encodeURIComponent(situsAddress!)}`;
    }
    // LOW TRUST: Search by parcel ID (user must verify)
    return `https://www.google.com/maps/search/${encodeURIComponent(`${parish} parish parcel ${parcelId}`)}`;
  }, [hasCoordinates, latitude, longitude, hasSitusAddress, situsAddress, parish, parcelId]);

  // Parish assessor URL (Louisiana specific)
  const assessorUrl = useMemo(() => {
    // Common Louisiana parish assessor GIS portals
    const parishUrls: Record<string, string> = {
      'East Baton Rouge': 'https://www.ebrso.org/gis/',
      'Caddo': 'https://www.caddoassessor.org/',
      'Jefferson': 'https://www.jpao.net/',
      'Orleans': 'https://nolaassessor.com/',
      'Calcasieu': 'https://www.calcasieuassessor.org/',
      'Lafayette': 'https://www.lafayetteassessor.com/',
    };
    return parishUrls[parish] || `https://www.google.com/search?q=${encodeURIComponent(`${parish} parish assessor GIS Louisiana`)}`;
  }, [parish]);

  // PRODUCTION RULE: If we have nothing verified, show explicit warning
  if (!hasCoordinates && !hasPolygon) {
    return (
      <div className={`${className} rounded-lg bg-muted flex flex-col items-center justify-center p-6 border-2 border-dashed border-yellow-300`}>
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="h-6 w-6 text-yellow-500" />
          <span className="font-medium text-yellow-700">Location Not Verified</span>
        </div>
        <p className="text-sm text-muted-foreground text-center mb-2">
          No verified coordinates available for this property.
        </p>
        <p className="text-xs text-muted-foreground text-center mb-4">
          Parcel: <span className="font-mono">{parcelId}</span> • {parish} Parish
        </p>
        
        {/* Trust Warning */}
        <div className="w-full max-w-xs mb-4 p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-700 text-center">
          ⚠️ Verify property location before making offer
        </div>
        
        <div className="flex flex-col gap-2 w-full max-w-xs">
          <Button
            variant={hasSitusAddress ? "default" : "outline"}
            className="w-full"
            onClick={() => window.open(googleMapsUrl, '_blank')}
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            {hasSitusAddress ? 'Search Situs Address' : 'Search Parcel ID'}
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => window.open(assessorUrl, '_blank')}
          >
            <Search className="h-4 w-4 mr-2" />
            Open Parish Assessor / GIS
          </Button>
        </div>
        
        {/* Data Source Label */}
        <p className="text-xs text-muted-foreground mt-3 italic">
          {hasSitusAddress 
            ? `Situs: ${situsAddress}` 
            : 'No situs address on file'}
        </p>
      </div>
    );
  }

  // Render map with Leaflet - ONLY if we have verified data
  return (
    <div className={`${className} rounded-lg overflow-hidden border relative`}>
      {/* Trust Level Indicator */}
      <div className="absolute top-2 left-2 z-[1000]">
        <Badge 
          variant="secondary" 
          className={`shadow-md ${
            trustLevel === 'verified' 
              ? 'bg-green-100 text-green-700 border-green-300' 
              : 'bg-blue-100 text-blue-700 border-blue-300'
          }`}
        >
          {trustLevel === 'verified' && <CheckCircle className="h-3 w-3 mr-1" />}
          {trustLevel === 'verified' ? 'Verified Coordinates' : 'Parcel Boundary'}
        </Badge>
      </div>
      
      <MapContainer
        center={center}
        zoom={hasCoordinates ? 17 : 15}
        style={{ height: '100%', width: '100%' }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        
        {hasCoordinates && (
          <Marker position={[latitude!, longitude!]}>
            <Popup>
              <div className="text-sm">
                <strong>{situsAddress || `Parcel ${parcelId}`}</strong>
                <br />
                {parish} Parish
                <br />
                <span className="text-xs text-green-600">✓ Verified coordinates</span>
              </div>
            </Popup>
          </Marker>
        )}
        
        {hasPolygon && (
          <>
            <Polygon
              positions={polygonCoords!}
              pathOptions={{ color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 0.2 }}
            />
            <FitBounds bounds={polygonCoords!} />
          </>
        )}
      </MapContainer>
      
      {/* External link overlay */}
      <div className="absolute bottom-2 right-2 z-[1000]">
        <Button
          size="sm"
          variant="secondary"
          className="shadow-md"
          onClick={() => window.open(googleMapsUrl, '_blank')}
        >
          <ExternalLink className="h-3 w-3 mr-1" />
          Google Maps
        </Button>
      </div>
    </div>
  );
}

export default PropertyMap;
