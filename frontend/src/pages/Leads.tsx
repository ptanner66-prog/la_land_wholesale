import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search,
  Plus,
  Filter,
  ChevronLeft,
  ChevronRight,
  Flame,
  Phone,
  MapPin,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { useMarket } from '@/components/market-provider';
import { getLeadsPaginated, searchLeads, createManualLead } from '@/api/leads';
import type { LeadSummary, ManualLeadCreate, PipelineStage } from '@/lib/types';

const PAGE_SIZE = 25;

const STAGE_COLORS: Record<PipelineStage, string> = {
  NEW: 'bg-blue-500 hover:bg-blue-600',
  CONTACTED: 'bg-yellow-500 hover:bg-yellow-600',
  HOT: 'bg-red-500 hover:bg-red-600',
};

export function Leads() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { market } = useMarket();
  const { toast } = useToast();

  const [leads, setLeads] = useState<LeadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [_error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [_total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  // Filters - Default to hiding low-value leads (score >= 45)
  const [searchQuery, setSearchQuery] = useState(searchParams.get('q') || '');
  const [stageFilter, setStageFilter] = useState<PipelineStage | 'ALL'>(
    (searchParams.get('pipeline_stage') as PipelineStage) || 'ALL'
  );
  const [minScore, setMinScore] = useState<number | undefined>(
    searchParams.get('min_score') ? parseInt(searchParams.get('min_score')!) : 45 // Default to 45 to hide junk
  );
  const [showAllLeads, setShowAllLeads] = useState(false);

  // Manual lead dialog
  const [dialogOpen, setDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newLead, setNewLead] = useState<ManualLeadCreate>({
    owner_name: '',
    address: '',
    city: '',
    state: market,
    market_code: market,
    enrich: true,
  });

  useEffect(() => {
    fetchLeads();
  }, [market, page, stageFilter, minScore]);

  async function fetchLeads() {
    setLoading(true);
    setError(null);
    try {
      const data = await getLeadsPaginated({
        market,
        pipeline_stage: stageFilter === 'ALL' ? undefined : stageFilter,
        min_score: minScore,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        order_by: 'score_desc',
      });
      setLeads(data.items || []);
      setTotal(data.total || 0);
      setHasMore((page + 1) * PAGE_SIZE < (data.total || 0));
    } catch (err) {
      console.error('Failed to fetch leads:', err);
      setError('Failed to load leads');
      setLeads([]);
      setTotal(0);
      setHasMore(false);
      toast({ title: 'Error', description: 'Failed to fetch leads', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) {
      fetchLeads();
      return;
    }
    setLoading(true);
    try {
      const results = await searchLeads(searchQuery, market, 100);
      setLeads(results);
      setHasMore(false);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateLead() {
    if (!newLead.owner_name || !newLead.address) {
      toast({ title: 'Error', description: 'Name and address are required', variant: 'destructive' });
      return;
    }
    setCreating(true);
    try {
      const result = await createManualLead({ ...newLead, market_code: market });
      if (result.success && result.lead_id) {
        toast({ title: 'Success', description: `Lead created with score ${result.motivation_score}` });
        setDialogOpen(false);
        setNewLead({ owner_name: '', address: '', city: '', state: market, market_code: market, enrich: true });
        fetchLeads();
      } else {
        toast({ title: 'Error', description: result.message, variant: 'destructive' });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to create lead', variant: 'destructive' });
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Leads</h2>
          <p className="text-muted-foreground">Manage your {market} market leads</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Add Lead
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add New Lead</DialogTitle>
              <DialogDescription>
                Manually enter a lead. We'll enrich and score it automatically.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="owner_name">Owner Name *</Label>
                <Input
                  id="owner_name"
                  value={newLead.owner_name}
                  onChange={(e) => setNewLead({ ...newLead, owner_name: e.target.value })}
                  placeholder="John Smith"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  value={newLead.phone || ''}
                  onChange={(e) => setNewLead({ ...newLead, phone: e.target.value })}
                  placeholder="(555) 123-4567"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="address">Address *</Label>
                <Input
                  id="address"
                  value={newLead.address}
                  onChange={(e) => setNewLead({ ...newLead, address: e.target.value })}
                  placeholder="123 Main St"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="city">City</Label>
                  <Input
                    id="city"
                    value={newLead.city || ''}
                    onChange={(e) => setNewLead({ ...newLead, city: e.target.value })}
                    placeholder="Baton Rouge"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="postal_code">ZIP</Label>
                  <Input
                    id="postal_code"
                    value={newLead.postal_code || ''}
                    onChange={(e) => setNewLead({ ...newLead, postal_code: e.target.value })}
                    placeholder="70801"
                  />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateLead} disabled={creating}>
                {creating ? 'Creating...' : 'Create Lead'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Info Banner - Low value leads hidden by default */}
      {!showAllLeads && minScore === 45 && (
        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50 text-sm">
          <span className="text-muted-foreground">
            Showing qualified leads only (score ≥ 45). Low-value leads are hidden.
          </span>
          <Button 
            variant="ghost" 
            size="sm"
            onClick={() => {
              setShowAllLeads(true);
              setMinScore(undefined);
              setPage(0);
            }}
          >
            Show All
          </Button>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center">
            <form onSubmit={handleSearch} className="flex flex-1 gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search by name, address, or parcel ID..."
                  className="pl-8"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <Button type="submit" variant="secondary">
                Search
              </Button>
            </form>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <Select
                value={stageFilter}
                onValueChange={(v) => {
                  setStageFilter(v as PipelineStage | 'ALL');
                  setPage(0);
                }}
              >
                <SelectTrigger className="w-[130px]">
                  <SelectValue placeholder="Stage" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All Stages</SelectItem>
                  <SelectItem value="NEW">New</SelectItem>
                  <SelectItem value="CONTACTED">Contacted</SelectItem>
                  <SelectItem value="HOT">Hot</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={minScore?.toString() || 'any'}
                onValueChange={(v) => {
                  setMinScore(v === 'any' ? undefined : parseInt(v));
                  setShowAllLeads(v === 'any');
                  setPage(0);
                }}
              >
                <SelectTrigger className="w-[130px]">
                  <SelectValue placeholder="Min Score" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any Score</SelectItem>
                  <SelectItem value="45">45+ (Qualified)</SelectItem>
                  <SelectItem value="65">65+ (Contact)</SelectItem>
                  <SelectItem value="75">75+ (Hot)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Leads Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">Owner</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Address</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Score</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Stage</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Reply</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Outreach</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  [...Array(10)].map((_, i) => (
                    <tr key={i} className="border-b">
                      <td className="px-4 py-3"><Skeleton className="h-5 w-32" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-48" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-12" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-20" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-20" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-8" /></td>
                    </tr>
                  ))
                ) : leads.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      No leads found
                    </td>
                  </tr>
                ) : (
                  leads.map((lead) => (
                    <tr
                      key={lead.id}
                      className="border-b cursor-pointer hover:bg-muted/50 transition-colors"
                      onClick={() => navigate(`/leads/${lead.id}`)}
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium">{lead.owner_name}</div>
                        {lead.owner_phone && (
                          <div className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Phone className="h-3 w-3" />
                            {lead.owner_phone}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <MapPin className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                          <span className="text-sm font-medium">
                            {lead.display_address}
                          </span>
                          {!lead.has_situs_address && (
                            <Badge variant="outline" className="text-xs text-yellow-600 border-yellow-300 ml-1">
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              Parcel Only
                            </Badge>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {lead.display_location}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold">{lead.motivation_score}</span>
                          {lead.motivation_score >= 75 && (
                            <Flame className="h-4 w-4 text-orange-500" />
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge className={STAGE_COLORS[lead.pipeline_stage]}>
                          {lead.pipeline_stage}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        {lead.last_reply_classification ? (
                          <Badge variant="outline" className="text-xs">
                            {lead.last_reply_classification}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-sm">{lead.outreach_count}</span>
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
              Showing {page * PAGE_SIZE + 1} - {page * PAGE_SIZE + leads.length}
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

export default Leads;