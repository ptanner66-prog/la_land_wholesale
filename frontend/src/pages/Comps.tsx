import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { FileText, MapPin, DollarSign, Calendar, Ruler, AlertCircle, ChevronRight, Ban } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useToast } from '@/components/ui/use-toast';
import { useMarket } from '@/components/market-provider';
import { useActiveMarket } from '@/components/active-market-provider';
import { getLeads, getLeadComps } from '@/api/leads';
import type { LeadSummary, CompsResult } from '@/lib/types';

export function Comps() {
  const { market } = useMarket();
  const { activeMarket, summary } = useActiveMarket();
  const { toast } = useToast();
  
  // Comps are disabled if no sales data exists for the active market
  const hasSalesData = summary?.has_sales_data ?? false;

  const [leads, setLeads] = useState<LeadSummary[]>([]);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [leadsLoading, setLeadsLoading] = useState(true);
  const [compsResult, setCompsResult] = useState<CompsResult | null>(null);
  const [maxComps, setMaxComps] = useState<number>(5);

  // Load leads on mount
  useEffect(() => {
    loadLeads();
  }, [market]);

  async function loadLeads() {
    setLeadsLoading(true);
    try {
      const data = await getLeads({
        market,
        order_by: 'score_desc',
        limit: 50,
      });
      setLeads(data);
      
      // Auto-select first lead if available
      if (data.length > 0 && !selectedLeadId) {
        setSelectedLeadId(data[0].id);
      }
    } catch (error) {
      console.error('Failed to load leads:', error);
      toast({
        title: 'Error',
        description: 'Failed to load leads',
        variant: 'destructive',
      });
    } finally {
      setLeadsLoading(false);
    }
  }

  async function handleFetchComps() {
    if (!selectedLeadId) {
      toast({
        title: 'No Lead Selected',
        description: 'Please select a lead to fetch comps',
        variant: 'destructive',
      });
      return;
    }

    setLoading(true);
    setCompsResult(null);

    try {
      const data = await getLeadComps(selectedLeadId, maxComps);
      setCompsResult(data);
      
      if (data.total_comps_found === 0) {
        toast({
          title: 'No Comps Found',
          description: 'No comparable sales found in this area',
        });
      }
    } catch (error: any) {
      console.error('Failed to fetch comps:', error);
      // Never show generic error - provide helpful message
      const errorDetail = error.response?.data?.detail;
      if (errorDetail?.includes('no sales data') || errorDetail?.includes('not available')) {
        setCompsResult({
          comps: [],
          total_comps_found: 0,
          avg_price_per_acre: null,
          median_price_per_acre: null,
          cached: false,
          is_mock_data: false,
        });
        toast({
          title: 'No Comps Available',
          description: 'No comparable sales data exists for this area yet.',
        });
      } else {
        // Show 0 comps instead of error
        setCompsResult({
          comps: [],
          total_comps_found: 0,
          avg_price_per_acre: null,
          median_price_per_acre: null,
          cached: false,
          is_mock_data: false,
        });
        toast({
          title: 'No Comps Found',
          description: 'Unable to find comparable sales for this property.',
        });
      }
    } finally {
      setLoading(false);
    }
  }

  const selectedLead = leads.find((l) => l.id === selectedLeadId);

  // If no sales data, show disabled state
  if (!hasSalesData) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Comparable Sales</h1>
            <p className="text-muted-foreground">
              Find recent sales of similar properties in the area
            </p>
          </div>
          {activeMarket?.active && (
            <Badge variant="outline" className="text-lg">
              {activeMarket.display_name}
            </Badge>
          )}
        </div>
        
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <div className="p-4 rounded-full bg-muted mb-4">
              <Ban className="h-12 w-12 text-muted-foreground" />
            </div>
            <h3 className="text-xl font-semibold mb-2">Comps Unavailable</h3>
            <p className="text-muted-foreground text-center max-w-md mb-4">
              Comparable sales data is not available for{' '}
              <strong>{activeMarket?.display_name || 'this market'}</strong>.
            </p>
            <Alert className="max-w-md mb-6">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>No Deed Records Ingested</AlertTitle>
              <AlertDescription>
                To enable comparable sales, deed/conveyance records must be ingested for this parish.
              </AlertDescription>
            </Alert>
            
            {/* Next Actions */}
            <div className="space-y-3 w-full max-w-md">
              <div className="p-4 rounded-lg border bg-muted/50">
                <h4 className="font-medium mb-2">✅ Offer Range Works Without Comps</h4>
                <p className="text-sm text-muted-foreground mb-3">
                  You can still make offers using assessed value. Open any lead's Call Prep Pack to see the Offer Helper.
                </p>
                <Link to="/leads">
                  <Button variant="outline" size="sm" className="w-full">
                    <ChevronRight className="h-4 w-4 mr-2" />
                    Go to Leads
                  </Button>
                </Link>
              </div>
              
              <div className="p-4 rounded-lg border">
                <h4 className="font-medium mb-2">📊 Request Deed Ingestion</h4>
                <p className="text-sm text-muted-foreground mb-3">
                  To enable comps, deed/conveyance records need to be ingested for this parish.
                </p>
                <Link to="/ingestion">
                  <Button variant="outline" size="sm" className="w-full">
                    <ChevronRight className="h-4 w-4 mr-2" />
                    Go to Ingestion
                  </Button>
                </Link>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Comparable Sales</h1>
          <p className="text-muted-foreground">
            Find recent sales of similar properties in the area
          </p>
        </div>
        {activeMarket?.active && (
          <Badge variant="outline" className="text-lg">
            {activeMarket.display_name}
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Selection Panel */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Select Property
            </CardTitle>
            <CardDescription>
              Choose a lead to view comparable sales data
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Lead Selection */}
            <div className="space-y-2">
              <Label htmlFor="lead-select">Lead</Label>
              {leadsLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : leads.length === 0 ? (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    No leads found. Create a lead first.
                  </AlertDescription>
                </Alert>
              ) : (
                <select
                  id="lead-select"
                  className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={selectedLeadId || ''}
                  onChange={(e) => setSelectedLeadId(Number(e.target.value))}
                >
                  {leads.map((lead) => (
                    <option key={lead.id} value={lead.id}>
                      {lead.parcel_id} ({lead.parish}) - {lead.acreage ? `${lead.acreage} ac` : 'N/A'}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Max Comps */}
            <div className="space-y-2">
              <Label htmlFor="max-comps">Number of Comps</Label>
              <select
                id="max-comps"
                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={maxComps}
                onChange={(e) => setMaxComps(Number(e.target.value))}
              >
                <option value={3}>3</option>
                <option value={5}>5</option>
                <option value={10}>10</option>
              </select>
            </div>

            {/* Selected Lead Info */}
            {selectedLead && (
              <div className="p-3 border rounded-lg space-y-1 text-sm">
                <div className="font-medium">{selectedLead.parcel_id}</div>
                <div className="text-muted-foreground">
                  {selectedLead.acreage ? `${selectedLead.acreage} acres` : 'Acreage unknown'}
                </div>
                {selectedLead.parish && (
                  <div className="text-muted-foreground">{selectedLead.parish}</div>
                )}
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant="secondary">Score: {selectedLead.motivation_score}</Badge>
                </div>
                <Link
                  to={`/leads/${selectedLead.id}`}
                  className="text-blue-600 hover:underline flex items-center gap-1 mt-2"
                >
                  View Details <ChevronRight className="h-3 w-3" />
                </Link>
              </div>
            )}

            {/* Fetch Button */}
            <Button
              onClick={handleFetchComps}
              className="w-full"
              disabled={loading || !selectedLeadId}
            >
              {loading ? 'Fetching Comps...' : 'Fetch Comps'}
            </Button>
          </CardContent>
        </Card>

        {/* Right: Results */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MapPin className="h-5 w-5" />
              Comparable Sales
            </CardTitle>
            <CardDescription>
              Recent sales of similar properties within the area
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!compsResult && !loading && (
              <div className="flex flex-col items-center justify-center h-64 text-center text-muted-foreground">
                <FileText className="h-12 w-12 mb-4 opacity-50" />
                <p>Select a lead and click Fetch Comps to see comparable sales</p>
              </div>
            )}

            {loading && (
              <div className="space-y-4">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            )}

            {compsResult && (
              <div className="space-y-6">
                {/* Summary Stats */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Avg Price/Acre</div>
                    <div className="text-2xl font-bold">
                      ${compsResult.avg_price_per_acre?.toLocaleString() || 'N/A'}
                    </div>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Median Price/Acre</div>
                    <div className="text-2xl font-bold">
                      ${compsResult.median_price_per_acre?.toLocaleString() || 'N/A'}
                    </div>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Comps Found</div>
                    <div className="text-2xl font-bold">{compsResult.total_comps_found}</div>
                  </div>
                </div>

                {/* Comps List */}
                {compsResult.total_comps_found === 0 ? (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      No comparable sales found in this area. This could mean the property is in
                      a unique market or data is not available.
                    </AlertDescription>
                  </Alert>
                ) : (
                  <div className="space-y-3">
                    {compsResult.comps.map((comp, index) => (
                      <div
                        key={index}
                        className="p-4 border rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <div className="font-medium">{comp.address || 'Address N/A'}</div>
                            {comp.distance && (
                              <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                <MapPin className="h-3 w-3" />
                                {comp.distance.toFixed(2)} miles away
                              </div>
                            )}
                          </div>
                          <Badge variant="secondary">Comp #{index + 1}</Badge>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
                          <div className="flex items-center gap-2">
                            <DollarSign className="h-4 w-4 text-muted-foreground" />
                            <div>
                              <div className="text-xs text-muted-foreground">Sale Price</div>
                              <div className="font-semibold">
                                ${comp.sale_price?.toLocaleString() || 'N/A'}
                              </div>
                            </div>
                          </div>
                          
                          <div className="flex items-center gap-2">
                            <Ruler className="h-4 w-4 text-muted-foreground" />
                            <div>
                              <div className="text-xs text-muted-foreground">Acreage</div>
                              <div className="font-semibold">
                                {comp.acreage ? `${comp.acreage.toFixed(2)} ac` : 'N/A'}
                              </div>
                            </div>
                          </div>
                          
                          <div className="flex items-center gap-2">
                            <DollarSign className="h-4 w-4 text-muted-foreground" />
                            <div>
                              <div className="text-xs text-muted-foreground">Price/Acre</div>
                              <div className="font-semibold text-green-600">
                                ${comp.price_per_acre?.toLocaleString() || 'N/A'}
                              </div>
                            </div>
                          </div>
                          
                          <div className="flex items-center gap-2">
                            <Calendar className="h-4 w-4 text-muted-foreground" />
                            <div>
                              <div className="text-xs text-muted-foreground">Sale Date</div>
                              <div className="font-semibold">
                                {comp.sale_date
                                  ? new Date(comp.sale_date).toLocaleDateString()
                                  : 'N/A'}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Cache Info */}
                {compsResult.cached && (
                  <div className="text-xs text-muted-foreground text-center">
                    Results cached from previous fetch
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default Comps;

