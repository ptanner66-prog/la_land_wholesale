import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MapPin,
  Home,
  Scale,
  ChevronLeft,
  ChevronRight,
  Search,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useMarket } from '@/components/market-provider';
import { getParcels } from '@/api/parcels';
import type { Parcel } from '@/lib/types';

const PAGE_SIZE = 25;

export function Parcels() {
  useNavigate(); // Keep hook for potential future use
  const { market } = useMarket();

  const [parcels, setParcels] = useState<Parcel[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [tab, setTab] = useState<'all' | 'adjudicated'>('all');

  useEffect(() => {
    fetchParcels();
  }, [market, page, tab]);

  async function fetchParcels() {
    setLoading(true);
    try {
      const data = await getParcels({
        market,
        is_adjudicated: tab === 'adjudicated' ? true : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setParcels(data);
      setHasMore(data.length === PAGE_SIZE);
    } catch (error) {
      console.error('Failed to fetch parcels:', error);
    } finally {
      setLoading(false);
    }
  }

  const filteredParcels = searchQuery
    ? parcels.filter(
        (p) =>
          p.canonical_parcel_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
          p.situs_address?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          p.city?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : parcels;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Parcels</h2>
          <p className="text-muted-foreground">Property parcels in {market}</p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={(v) => { setTab(v as 'all' | 'adjudicated'); setPage(0); }}>
        <TabsList>
          <TabsTrigger value="all">All Parcels</TabsTrigger>
          <TabsTrigger value="adjudicated">
            <Scale className="h-4 w-4 mr-2" />
            Adjudicated
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Search */}
      <Card>
        <CardContent className="pt-6">
          <div className="relative max-w-md">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by parcel ID or address..."
              className="pl-8"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Parcels Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">Parcel ID</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Address</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Parish</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Acreage</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Land Value</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  [...Array(10)].map((_, i) => (
                    <tr key={i} className="border-b">
                      <td className="px-4 py-3"><Skeleton className="h-5 w-24" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-48" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-32" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-16" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-20" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-24" /></td>
                    </tr>
                  ))
                ) : filteredParcels.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      No parcels found
                    </td>
                  </tr>
                ) : (
                  filteredParcels.map((parcel) => (
                    <tr key={parcel.id} className="border-b hover:bg-muted/50">
                      <td className="px-4 py-3">
                        <span className="font-mono text-sm">{parcel.canonical_parcel_id}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <MapPin className="h-4 w-4 text-muted-foreground" />
                          <div>
                            <p className="text-sm">{parcel.situs_address || 'No address'}</p>
                            <p className="text-xs text-muted-foreground">
                              {parcel.city}, {parcel.state} {parcel.postal_code}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">{parcel.parish}</td>
                      <td className="px-4 py-3 text-sm">
                        {parcel.lot_size_acres ? `${parcel.lot_size_acres.toFixed(2)} ac` : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {parcel.land_assessed_value
                          ? `$${parcel.land_assessed_value.toLocaleString()}`
                          : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {parcel.is_adjudicated && (
                            <Badge variant="destructive" className="text-xs">
                              <Scale className="h-3 w-3 mr-1" />
                              Adjudicated
                            </Badge>
                          )}
                          {parcel.years_tax_delinquent > 0 && (
                            <Badge variant="outline" className="text-xs">
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              {parcel.years_tax_delinquent}yr Tax Delinq
                            </Badge>
                          )}
                          {parcel.inside_city_limits === true && (
                            <Badge variant="secondary" className="text-xs">
                              <Home className="h-3 w-3 mr-1" />
                              In City
                            </Badge>
                          )}
                          {!parcel.is_adjudicated && parcel.years_tax_delinquent === 0 && (
                            <Badge variant="outline" className="text-xs text-muted-foreground">
                              Normal
                            </Badge>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Showing {page * PAGE_SIZE + 1} - {page * PAGE_SIZE + filteredParcels.length}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(page + 1)}
                disabled={!hasMore}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default Parcels;