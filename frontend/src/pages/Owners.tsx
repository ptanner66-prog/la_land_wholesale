import { useState, useEffect } from 'react';
import {
  Phone,
  Mail,
  Shield,
  ShieldOff,
  ChevronLeft,
  ChevronRight,
  Search,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { useMarket } from '@/components/market-provider';
import { getOwners } from '@/api/owners';
import type { Owner } from '@/lib/types';

const PAGE_SIZE = 25;

export function Owners() {
  const { market } = useMarket();

  const [owners, setOwners] = useState<Owner[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchOwners();
  }, [market, page]);

  async function fetchOwners() {
    setLoading(true);
    try {
      const data = await getOwners({
        market,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setOwners(data);
      setHasMore(data.length === PAGE_SIZE);
    } catch (error) {
      console.error('Failed to fetch owners:', error);
    } finally {
      setLoading(false);
    }
  }

  const filteredOwners = searchQuery
    ? owners.filter(
        (o) =>
          o.phone_primary?.includes(searchQuery) ||
          o.email?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : owners;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Owners</h2>
          <p className="text-muted-foreground">Property owner contacts in {market}</p>
        </div>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="pt-6">
          <div className="relative max-w-md">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by phone or email..."
              className="pl-8"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Owners Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">ID</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Phone</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Email</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">TCPA</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">DNR</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Opt Out</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  [...Array(10)].map((_, i) => (
                    <tr key={i} className="border-b">
                      <td className="px-4 py-3"><Skeleton className="h-5 w-16" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-28" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-40" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-12" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-12" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-12" /></td>
                    </tr>
                  ))
                ) : filteredOwners.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      No owners found
                    </td>
                  </tr>
                ) : (
                  filteredOwners.map((owner) => (
                    <tr key={owner.id} className="border-b hover:bg-muted/50">
                      <td className="px-4 py-3 font-mono text-sm">#{owner.id}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Phone className="h-4 w-4 text-muted-foreground" />
                          <span>{owner.phone_primary || '—'}</span>
                        </div>
                        {owner.phone_secondary && (
                          <div className="text-xs text-muted-foreground">
                            Alt: {owner.phone_secondary}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {owner.email ? (
                          <div className="flex items-center gap-2">
                            <Mail className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm">{owner.email}</span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {owner.is_tcpa_safe ? (
                          <Badge className="bg-green-500">
                            <Shield className="h-3 w-3 mr-1" />
                            Safe
                          </Badge>
                        ) : (
                          <Badge variant="outline">
                            <ShieldOff className="h-3 w-3 mr-1" />
                            No
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={owner.is_dnr ? 'destructive' : 'outline'}>
                          {owner.is_dnr ? 'Yes' : 'No'}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={owner.opt_out ? 'destructive' : 'outline'}>
                          {owner.opt_out ? 'Yes' : 'No'}
                        </Badge>
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
              Showing {page * PAGE_SIZE + 1} - {page * PAGE_SIZE + filteredOwners.length}
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

export default Owners;