import { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Calculator, TrendingUp, DollarSign, Users, AlertCircle, ChevronRight, FileText } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { useMarket } from '@/components/market-provider';
import { getLeads } from '@/api/leads';
import { getDealAnalysis, getBuyerMatches, analyzeManualDeal } from '@/api/evaluate';
import type { LeadSummary } from '@/lib/types';
import type { DealAnalysisResult, BuyerMatchesResult, ManualDealAnalysisResponse } from '@/api/evaluate';

export function DealCalculator() {
  const [_searchParams] = useSearchParams();
  const { market } = useMarket();
  const { toast } = useToast();

  // Tab state
  const [activeTab, setActiveTab] = useState<'lead' | 'manual'>('lead');

  // Lead-based analysis state
  const [leads, setLeads] = useState<LeadSummary[]>([]);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);
  const [purchasePrice, setPurchasePrice] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [leadsLoading, setLeadsLoading] = useState(true);
  const [analysis, setAnalysis] = useState<DealAnalysisResult | null>(null);
  const [matches, setMatches] = useState<BuyerMatchesResult | null>(null);

  // Manual analysis state
  const [manualAcres, setManualAcres] = useState<string>('');
  const [manualEstimatedValue, setManualEstimatedValue] = useState<string>('');
  const [manualPurchasePrice, setManualPurchasePrice] = useState<string>('');
  const [manualComps, setManualComps] = useState<string>(''); // Comma-separated
  const [manualMotivation, setManualMotivation] = useState<string>('50');
  const [manualAdjudicated, setManualAdjudicated] = useState(false);
  const [manualAnalysis, setManualAnalysis] = useState<ManualDealAnalysisResponse | null>(null);

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

  async function handleCalculate() {
    if (!selectedLeadId) {
      toast({
        title: 'No Lead Selected',
        description: 'Please select a lead to analyze',
        variant: 'destructive',
      });
      return;
    }

    const price = parseFloat(purchasePrice);
    if (isNaN(price) || price <= 0) {
      toast({
        title: 'Invalid Price',
        description: 'Please enter a valid purchase price',
        variant: 'destructive',
      });
      return;
    }

    setLoading(true);
    setAnalysis(null);
    setMatches(null);

    try {
      // Fetch analysis and buyer matches in parallel
      const [analysisData, matchesData] = await Promise.all([
        getDealAnalysis(selectedLeadId, price),
        getBuyerMatches(selectedLeadId, price, 30, 20),
      ]);

      setAnalysis(analysisData);
      setMatches(matchesData);
    } catch (error: any) {
      console.error('Deal analysis failed:', error);
      toast({
        title: 'Analysis Failed',
        description: error.response?.data?.detail || 'Failed to analyze deal',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleManualCalculate() {
    const acres = parseFloat(manualAcres);
    if (isNaN(acres) || acres <= 0) {
      toast({
        title: 'Invalid Acreage',
        description: 'Please enter a valid acreage',
        variant: 'destructive',
      });
      return;
    }

    setLoading(true);
    setManualAnalysis(null);

    try {
      // Parse comps if provided
      const comps = manualComps
        ? manualComps.split(',').map(c => parseFloat(c.trim())).filter(c => !isNaN(c))
        : undefined;

      const result = await analyzeManualDeal({
        acres,
        estimated_value: manualEstimatedValue ? parseFloat(manualEstimatedValue) : undefined,
        purchase_price: manualPurchasePrice ? parseFloat(manualPurchasePrice) : undefined,
        comps,
        market_code: market,
        motivation_score: parseInt(manualMotivation) || 50,
        is_adjudicated: manualAdjudicated,
      });

      setManualAnalysis(result);
    } catch (error: any) {
      console.error('Manual deal analysis failed:', error);
      toast({
        title: 'Analysis Failed',
        description: error.response?.data?.detail || 'Failed to analyze deal',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }

  const selectedLead = leads.find((l) => l.id === selectedLeadId);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Deal Calculator</h1>
          <p className="text-muted-foreground">
            Analyze deal margins, assignment fees, and buyer matches
          </p>
        </div>
        <Badge variant="outline" className="text-lg">
          Market: {market}
        </Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Input Form */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calculator className="h-5 w-5" />
              Deal Inputs
            </CardTitle>
            <CardDescription>
              Analyze a lead or enter manual property details
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'lead' | 'manual')}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="lead">From Lead</TabsTrigger>
                <TabsTrigger value="manual">Manual Entry</TabsTrigger>
              </TabsList>

              {/* Lead-Based Analysis */}
              <TabsContent value="lead" className="space-y-4 mt-4">
                {/* Lead Selection */}
                <div className="space-y-2">
                  <Label htmlFor="lead-select">Select Lead</Label>
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
                          {lead.parcel_id} ({lead.parish}) - Score: {lead.motivation_score}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {/* Purchase Price */}
                <div className="space-y-2">
                  <Label htmlFor="purchase-price">Purchase Price</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-muted-foreground">$</span>
                    <Input
                      id="purchase-price"
                      type="number"
                      placeholder="0.00"
                      className="pl-7"
                      value={purchasePrice}
                      onChange={(e) => setPurchasePrice(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleCalculate()}
                    />
                  </div>
                </div>

                {/* Selected Lead Info */}
                {selectedLead && (
                  <div className="p-3 border rounded-lg space-y-1 text-sm">
                    <div className="font-medium">{selectedLead.parcel_id}</div>
                    <div className="text-muted-foreground">
                      {selectedLead.acreage ? `${selectedLead.acreage} acres` : 'Acreage unknown'}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">Score: {selectedLead.motivation_score}</Badge>
                      <Badge>{selectedLead.pipeline_stage}</Badge>
                    </div>
                    <Link
                      to={`/leads/${selectedLead.id}`}
                      className="text-blue-600 hover:underline flex items-center gap-1 mt-2"
                    >
                      View Details <ChevronRight className="h-3 w-3" />
                    </Link>
                  </div>
                )}

                {/* Calculate Button */}
                <Button
                  onClick={handleCalculate}
                  className="w-full"
                  disabled={loading || !selectedLeadId || !purchasePrice}
                >
                  {loading ? 'Analyzing...' : 'Calculate Deal'}
                </Button>
              </TabsContent>

              {/* Manual Entry Analysis */}
              <TabsContent value="manual" className="space-y-4 mt-4">
                {/* Acreage */}
                <div className="space-y-2">
                  <Label htmlFor="manual-acres">Acreage *</Label>
                  <Input
                    id="manual-acres"
                    type="number"
                    placeholder="e.g., 5.5"
                    value={manualAcres}
                    onChange={(e) => setManualAcres(e.target.value)}
                  />
                </div>

                {/* Estimated Value */}
                <div className="space-y-2">
                  <Label htmlFor="manual-value">Estimated Value (optional)</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-muted-foreground">$</span>
                    <Input
                      id="manual-value"
                      type="number"
                      placeholder="Leave blank to auto-calculate"
                      className="pl-7"
                      value={manualEstimatedValue}
                      onChange={(e) => setManualEstimatedValue(e.target.value)}
                    />
                  </div>
                </div>

                {/* Purchase Price */}
                <div className="space-y-2">
                  <Label htmlFor="manual-purchase">Target Purchase Price (optional)</Label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-muted-foreground">$</span>
                    <Input
                      id="manual-purchase"
                      type="number"
                      placeholder="Leave blank to auto-calculate"
                      className="pl-7"
                      value={manualPurchasePrice}
                      onChange={(e) => setManualPurchasePrice(e.target.value)}
                    />
                  </div>
                </div>

                {/* Comps */}
                <div className="space-y-2">
                  <Label htmlFor="manual-comps">Comp Prices/Acre (optional)</Label>
                  <Input
                    id="manual-comps"
                    type="text"
                    placeholder="e.g., 5000, 6000, 4500"
                    value={manualComps}
                    onChange={(e) => setManualComps(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Comma-separated price per acre values</p>
                </div>

                {/* Motivation Score */}
                <div className="space-y-2">
                  <Label htmlFor="manual-motivation">Motivation Score (0-100)</Label>
                  <Input
                    id="manual-motivation"
                    type="number"
                    min="0"
                    max="100"
                    value={manualMotivation}
                    onChange={(e) => setManualMotivation(e.target.value)}
                  />
                </div>

                {/* Adjudicated Checkbox */}
                <div className="flex items-center space-x-2">
                  <input
                    id="manual-adjudicated"
                    type="checkbox"
                    className="h-4 w-4"
                    checked={manualAdjudicated}
                    onChange={(e) => setManualAdjudicated(e.target.checked)}
                  />
                  <Label htmlFor="manual-adjudicated">Adjudicated Property</Label>
                </div>

                {/* Calculate Button */}
                <Button
                  onClick={handleManualCalculate}
                  className="w-full"
                  disabled={loading || !manualAcres}
                >
                  {loading ? 'Analyzing...' : 'Analyze Deal'}
                </Button>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {/* Right: Results */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Deal Analysis
            </CardTitle>
            <CardDescription>
              Projected margins, assignment fee, and buyer demand
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!analysis && !manualAnalysis && !loading && (
              <div className="flex flex-col items-center justify-center h-64 text-center text-muted-foreground">
                <Calculator className="h-12 w-12 mb-4 opacity-50" />
                <p>Enter deal details and click Calculate to see results</p>
              </div>
            )}

            {loading && (
              <div className="space-y-4">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            )}

            {analysis && (
              <div className="space-y-6">
                {/* Key Metrics */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Purchase Price</div>
                    <div className="text-2xl font-bold">
                      ${analysis.analysis.purchase_price.toLocaleString()}
                    </div>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Retail Value</div>
                    <div className="text-2xl font-bold">
                      ${analysis.analysis.retail_value.toLocaleString()}
                    </div>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Gross Margin</div>
                    <div className="text-2xl font-bold text-green-600">
                      ${analysis.analysis.gross_margin.toLocaleString()}
                    </div>
                  </div>
                </div>

                {/* Assignment Fee Range */}
                <div className="p-4 border rounded-lg bg-blue-50 dark:bg-blue-950">
                  <div className="flex items-center gap-2 mb-3">
                    <DollarSign className="h-5 w-5 text-blue-600" />
                    <h3 className="font-semibold">Recommended Assignment Fee</h3>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">Low</div>
                      <div className="text-lg font-bold">
                        ${analysis.analysis.min_assignment_fee.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">Recommended</div>
                      <div className="text-2xl font-bold text-blue-600">
                        ${analysis.analysis.recommended_assignment_fee.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">High</div>
                      <div className="text-lg font-bold">
                        ${analysis.analysis.max_assignment_fee.toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Deal Quality & Risk */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">ROI</div>
                    <div className="text-xl font-bold text-green-600">
                      {analysis.analysis.roi_percentage.toFixed(1)}%
                    </div>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Deal Quality</div>
                    <Badge className="text-sm">{analysis.analysis.deal_quality}</Badge>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Risk Level</div>
                    <Badge variant="outline" className="text-sm">
                      {analysis.analysis.risk_level}
                    </Badge>
                  </div>
                </div>

                {/* Buyer Matches */}
                {matches && (
                  <div className="p-4 border rounded-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <Users className="h-5 w-5" />
                      <h3 className="font-semibold">
                        Buyer Matches ({matches.total_matches})
                      </h3>
                    </div>
                    {matches.total_matches === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No buyers match this property yet. Consider adding buyers to your pipeline.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {matches.matches.slice(0, 5).map((match) => (
                          <div
                            key={match.buyer_id}
                            className="flex items-center justify-between p-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded"
                          >
                            <div className="flex items-center gap-2">
                              <span className="font-medium">{match.buyer_name}</span>
                              {match.vip && <Badge variant="secondary">VIP</Badge>}
                              {match.pof_verified && (
                                <Badge variant="outline" className="text-xs">
                                  POF ✓
                                </Badge>
                              )}
                            </div>
                            <div className="text-sm font-semibold text-green-600">
                              {match.match_percentage}% match
                            </div>
                          </div>
                        ))}
                        {matches.total_matches > 5 && (
                          <Link
                            to={`/leads/${selectedLeadId}`}
                            className="text-sm text-blue-600 hover:underline block text-center mt-2"
                          >
                            View all {matches.total_matches} matches
                          </Link>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Summary */}
                {analysis.analysis.summary && (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{analysis.analysis.summary}</AlertDescription>
                  </Alert>
                )}
              </div>
            )}

            {/* Manual Analysis Results */}
            {manualAnalysis && (
              <div className="space-y-6">
                {/* Key Metrics */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">ARV (Retail Value)</div>
                    <div className="text-2xl font-bold">
                      ${manualAnalysis.arv.toLocaleString()}
                    </div>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">MAO (Max Offer)</div>
                    <div className="text-2xl font-bold text-green-600">
                      ${manualAnalysis.mao.toLocaleString()}
                    </div>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <div className="text-sm text-muted-foreground mb-1">Confidence</div>
                    <div className="text-2xl font-bold">
                      {(manualAnalysis.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>

                {/* Assignment Fee */}
                <div className="p-4 border rounded-lg bg-blue-50 dark:bg-blue-950">
                  <div className="flex items-center gap-2 mb-3">
                    <DollarSign className="h-5 w-5 text-blue-600" />
                    <h3 className="font-semibold">Assignment Fee</h3>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">Conservative</div>
                      <div className="text-lg font-bold">
                        ${manualAnalysis.offer_range[0].toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">Recommended</div>
                      <div className="text-2xl font-bold text-blue-600">
                        ${manualAnalysis.assignment_fee.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">Aggressive</div>
                      <div className="text-lg font-bold">
                        ${manualAnalysis.offer_range[1].toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Analysis Notes */}
                {manualAnalysis.notes.length > 0 && (
                  <div className="p-4 border rounded-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <FileText className="h-5 w-5" />
                      <h3 className="font-semibold">Analysis Notes</h3>
                    </div>
                    <ul className="space-y-1 text-sm">
                      {manualAnalysis.notes.map((note, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-muted-foreground">•</span>
                          <span>{note}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Full Analysis Details */}
                {manualAnalysis.full_analysis && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 border rounded-lg">
                      <div className="text-sm text-muted-foreground mb-1">ROI</div>
                      <div className="text-xl font-bold text-green-600">
                        {((manualAnalysis.full_analysis as any).roi_percentage || 0).toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-4 border rounded-lg">
                      <div className="text-sm text-muted-foreground mb-1">Gross Margin</div>
                      <div className="text-xl font-bold">
                        ${((manualAnalysis.full_analysis as any).gross_margin || 0).toLocaleString()}
                      </div>
                    </div>
                    <div className="p-4 border rounded-lg">
                      <div className="text-sm text-muted-foreground mb-1">Risk Level</div>
                      <Badge variant="outline" className="text-sm">
                        {(manualAnalysis.full_analysis as any).risk_level || 'Unknown'}
                      </Badge>
                    </div>
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

export default DealCalculator;

