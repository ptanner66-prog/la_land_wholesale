import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus,
  Search,
  Star,
  FileCheck,
  Phone,
  Mail,
  Users,
  Filter,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { useMarket } from '@/components/market-provider';
import {
  getBuyers,
  createBuyer,
  getBuyerStatistics,
} from '@/api/buyers';
import type { BuyerSummary, BuyerCreate, BuyerStatistics, MarketCode } from '@/lib/types';

const MARKET_OPTIONS: MarketCode[] = ['LA', 'TX', 'MS', 'AR', 'AL'];

export function Buyers() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { market } = useMarket();

  const [buyers, setBuyers] = useState<BuyerSummary[]>([]);
  const [stats, setStats] = useState<BuyerStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [vipOnly, setVipOnly] = useState(false);
  const [pofOnly, setPofOnly] = useState(false);

  // Create dialog
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newBuyer, setNewBuyer] = useState<BuyerCreate>({
    name: '',
    phone: '',
    email: '',
    market_codes: [],
    counties: [],
    min_acres: undefined,
    max_acres: undefined,
    price_min: undefined,
    price_max: undefined,
    vip: false,
    notes: '',
  });

  useEffect(() => {
    fetchBuyers();
    fetchStats();
  }, [market, vipOnly, pofOnly]);

  async function fetchBuyers() {
    setLoading(true);
    try {
      const data = await getBuyers({
        market: market,
        vip_only: vipOnly,
        pof_verified_only: pofOnly,
        search: search || undefined,
        limit: 200,
      });
      setBuyers(data);
    } catch (error) {
      console.error('Failed to fetch buyers:', error);
      toast({ title: 'Error', description: 'Failed to load buyers', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }

  async function fetchStats() {
    try {
      const data = await getBuyerStatistics();
      setStats(data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  }

  function handleSearch() {
    fetchBuyers();
  }

  async function handleCreateBuyer() {
    if (!newBuyer.name.trim()) {
      toast({ title: 'Error', description: 'Name is required', variant: 'destructive' });
      return;
    }

    setCreating(true);
    try {
      const buyer = await createBuyer(newBuyer);
      toast({ title: 'Success', description: `Buyer "${buyer.name}" created` });
      setCreateDialogOpen(false);
      setNewBuyer({
        name: '',
        phone: '',
        email: '',
        market_codes: [],
        counties: [],
        vip: false,
        notes: '',
      });
      fetchBuyers();
      fetchStats();
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to create buyer', variant: 'destructive' });
    } finally {
      setCreating(false);
    }
  }

  const filteredBuyers = search
    ? buyers.filter(
        (b) =>
          b.name.toLowerCase().includes(search.toLowerCase()) ||
          b.phone?.includes(search) ||
          b.email?.toLowerCase().includes(search.toLowerCase())
      )
    : buyers;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Land Buyers</h2>
          <p className="text-muted-foreground">Manage your buyer list and preferences</p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Buyer
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Buyers</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_buyers || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">VIP Buyers</CardTitle>
            <Star className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.vip_buyers || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">POF Verified</CardTitle>
            <FileCheck className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.pof_verified_buyers || 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search buyers..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="pl-10"
                />
              </div>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={vipOnly}
                  onCheckedChange={(c) => setVipOnly(c as boolean)}
                />
                VIP Only
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={pofOnly}
                  onCheckedChange={(c) => setPofOnly(c as boolean)}
                />
                POF Verified
              </label>
              <Button variant="outline" onClick={handleSearch}>
                <Filter className="mr-2 h-4 w-4" />
                Filter
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Buyers Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Markets</TableHead>
                  <TableHead>Budget</TableHead>
                  <TableHead>Acreage</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Deals</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredBuyers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      No buyers found
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredBuyers.map((buyer) => (
                    <TableRow
                      key={buyer.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/buyers/${buyer.id}`)}
                    >
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {buyer.vip && <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />}
                          <span className="font-medium">{buyer.name}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          {buyer.phone && (
                            <div className="flex items-center gap-1 text-sm">
                              <Phone className="h-3 w-3" />
                              {buyer.phone}
                            </div>
                          )}
                          {buyer.email && (
                            <div className="flex items-center gap-1 text-sm text-muted-foreground">
                              <Mail className="h-3 w-3" />
                              {buyer.email}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {buyer.market_codes?.slice(0, 3).map((m) => (
                            <Badge key={m} variant="outline" className="text-xs">
                              {m}
                            </Badge>
                          ))}
                          {buyer.market_codes?.length > 3 && (
                            <Badge variant="outline" className="text-xs">
                              +{buyer.market_codes.length - 3}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {buyer.price_min || buyer.price_max ? (
                          <span className="text-sm">
                            ${(buyer.price_min || 0).toLocaleString()} -{' '}
                            ${(buyer.price_max || '∞').toLocaleString()}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Any</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {buyer.min_acres || buyer.max_acres ? (
                          <span className="text-sm">
                            {buyer.min_acres || 0} - {buyer.max_acres || '∞'} ac
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Any</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          {buyer.pof_verified && (
                            <Badge variant="default" className="bg-green-500 text-xs">
                              POF
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="font-medium">{buyer.deals_count}</span>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create Buyer Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add New Buyer</DialogTitle>
            <DialogDescription>Enter buyer information and preferences</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={newBuyer.name}
                  onChange={(e) => setNewBuyer({ ...newBuyer, name: e.target.value })}
                  placeholder="John Smith"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  value={newBuyer.phone || ''}
                  onChange={(e) => setNewBuyer({ ...newBuyer, phone: e.target.value })}
                  placeholder="+1 555-555-5555"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={newBuyer.email || ''}
                  onChange={(e) => setNewBuyer({ ...newBuyer, email: e.target.value })}
                  placeholder="john@example.com"
                />
              </div>
              <div className="space-y-2">
                <Label>Markets</Label>
                <div className="flex flex-wrap gap-2">
                  {MARKET_OPTIONS.map((m) => (
                    <label key={m} className="flex items-center gap-1">
                      <Checkbox
                        checked={newBuyer.market_codes?.includes(m)}
                        onCheckedChange={(checked) => {
                          const codes = newBuyer.market_codes || [];
                          setNewBuyer({
                            ...newBuyer,
                            market_codes: checked
                              ? [...codes, m]
                              : codes.filter((c) => c !== m),
                          });
                        }}
                      />
                      <span className="text-sm">{m}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-4">
              <div className="space-y-2">
                <Label htmlFor="min_acres">Min Acres</Label>
                <Input
                  id="min_acres"
                  type="number"
                  value={newBuyer.min_acres || ''}
                  onChange={(e) =>
                    setNewBuyer({ ...newBuyer, min_acres: parseFloat(e.target.value) || undefined })
                  }
                  placeholder="0"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="max_acres">Max Acres</Label>
                <Input
                  id="max_acres"
                  type="number"
                  value={newBuyer.max_acres || ''}
                  onChange={(e) =>
                    setNewBuyer({ ...newBuyer, max_acres: parseFloat(e.target.value) || undefined })
                  }
                  placeholder="100"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="price_min">Min Price</Label>
                <Input
                  id="price_min"
                  type="number"
                  value={newBuyer.price_min || ''}
                  onChange={(e) =>
                    setNewBuyer({ ...newBuyer, price_min: parseFloat(e.target.value) || undefined })
                  }
                  placeholder="0"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="price_max">Max Price</Label>
                <Input
                  id="price_max"
                  type="number"
                  value={newBuyer.price_max || ''}
                  onChange={(e) =>
                    setNewBuyer({ ...newBuyer, price_max: parseFloat(e.target.value) || undefined })
                  }
                  placeholder="100000"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="notes">Notes</Label>
              <Textarea
                id="notes"
                value={newBuyer.notes || ''}
                onChange={(e) => setNewBuyer({ ...newBuyer, notes: e.target.value })}
                placeholder="Additional notes about this buyer..."
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="vip"
                checked={newBuyer.vip}
                onCheckedChange={(c) => setNewBuyer({ ...newBuyer, vip: c as boolean })}
              />
              <Label htmlFor="vip" className="flex items-center gap-1">
                <Star className="h-4 w-4 text-yellow-500" />
                VIP Buyer
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateBuyer} disabled={creating}>
              {creating ? 'Creating...' : 'Create Buyer'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default Buyers;
