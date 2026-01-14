import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Phone,
  Mail,
  MapPin,
  RefreshCw,
  MessageSquare,
  Calculator,
  BarChart3,
  Clock,
  Send,
  Flame,
  Home,
  User,
  FileText,
  AlertTriangle,
  Users,
  Zap,
  PhoneCall,
  DollarSign,
  Trash2,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  getLeadById,
  updatePipelineStage,
  rescoreLead,
  getLeadComps,
  getLeadOffer,
  getLeadTimeline,
  getScoreDetails,
  deleteLead,
} from '@/api/leads';
import { sendToLead, generateMessage } from '@/api/outreach';
import { matchBuyersToLead, sendBuyerBlast, getDealsForLead } from '@/api/buyers';
import { getDealSheet, getCallScript } from '@/api/dispositions';
import type {
  LeadDetail as LeadDetailType,
  PipelineStage,
  CompsResult,
  OfferResult,
  TimelineEvent,
  ScoreDetails,
  MessageVariant,
  BuyerMatch,
  DealSheet,
  CallScript,
  BuyerDeal,
} from '@/lib/types';

const STAGE_COLORS: Record<PipelineStage, string> = {
  NEW: 'bg-blue-500',
  CONTACTED: 'bg-yellow-500',
  HOT: 'bg-red-500',
};

export function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [lead, setLead] = useState<LeadDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [rescoring, setRescoring] = useState(false);
  const [updatingStage, setUpdatingStage] = useState(false);

  // Tab data
  const [comps, setComps] = useState<CompsResult | null>(null);
  const [offer, setOffer] = useState<OfferResult | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [scoreDetails, setScoreDetails] = useState<ScoreDetails | null>(null);

  // Message dialog
  const [messageDialogOpen, setMessageDialogOpen] = useState(false);
  const [messageContext, setMessageContext] = useState<'intro' | 'followup' | 'final'>('intro');
  const [messageVariants, setMessageVariants] = useState<MessageVariant[]>([]);
  const [generatingMessages, setGeneratingMessages] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [selectedVariant, setSelectedVariant] = useState<MessageVariant | null>(null);

  // Delete dialog
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Disposition state
  const [buyerMatches, setBuyerMatches] = useState<BuyerMatch[]>([]);
  const [dealSheet, setDealSheet] = useState<DealSheet | null>(null);
  const [callScript, setCallScript] = useState<CallScript | null>(null);
  const [buyerDeals, setBuyerDeals] = useState<BuyerDeal[]>([]);
  const [loadingMatches, setLoadingMatches] = useState(false);
  const [loadingDealSheet, setLoadingDealSheet] = useState(false);
  const [loadingCallScript, setLoadingCallScript] = useState(false);
  const [blastDialogOpen, setBlastDialogOpen] = useState(false);
  const [blasting, setBlasting] = useState(false);
  const [callScriptDialogOpen, setCallScriptDialogOpen] = useState(false);

  useEffect(() => {
    if (id) {
      fetchLead();
      fetchBuyerDeals();
    }
  }, [id]);

  async function fetchLead() {
    setLoading(true);
    try {
      const data = await getLeadById(parseInt(id!));
      setLead(data);
      
      // Fetch additional data
      const [compsData, timelineData, scoreData] = await Promise.all([
        getLeadComps(parseInt(id!), 5).catch(() => null),
        getLeadTimeline(parseInt(id!), 20).catch(() => []),
        getScoreDetails(parseInt(id!)).catch(() => null),
      ]);
      setComps(compsData);
      setTimeline(timelineData);
      // FIXED: Use fresh score data, don't fall back to potentially stale lead data
      setScoreDetails(scoreData);
    } catch (error) {
      console.error('Failed to fetch lead:', error);
      toast({ title: 'Error', description: 'Failed to load lead', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }

  async function handleRescore() {
    if (!lead) return;
    setRescoring(true);
    try {
      const result = await rescoreLead(lead.id);
      toast({
        title: 'Lead Rescored',
        description: `Score updated: ${result.old_score} → ${result.new_score}`,
      });
      setScoreDetails(result.score_details);
      setLead({ ...lead, motivation_score: result.new_score, score_details: result.score_details });
      fetchLead(); // Refresh timeline
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to rescore lead', variant: 'destructive' });
    } finally {
      setRescoring(false);
    }
  }

  async function handleStageChange(stage: PipelineStage) {
    if (!lead) return;
    setUpdatingStage(true);
    try {
      await updatePipelineStage(lead.id, stage);
      setLead({ ...lead, pipeline_stage: stage });
      toast({ title: 'Stage Updated', description: `Lead moved to ${stage}` });
      fetchLead(); // Refresh timeline
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to update stage', variant: 'destructive' });
    } finally {
      setUpdatingStage(false);
    }
  }

  async function handleCalculateOffer() {
    if (!lead) return;
    try {
      const result = await getLeadOffer(lead.id);
      setOffer(result);
      toast({ title: 'Offer Calculated', description: `Recommended: $${result.recommended_offer.toLocaleString()}` });
      fetchLead(); // Refresh timeline (offer calculation logs an event)
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to calculate offer', variant: 'destructive' });
    }
  }

  async function handleGenerateMessages(context: 'intro' | 'followup' | 'final') {
    if (!lead) return;
    setMessageContext(context);
    setGeneratingMessages(true);
    setMessageDialogOpen(true);
    setSelectedVariant(null);
    setMessageVariants([]);
    try {
      const result = await generateMessage(lead.id, context);
      if (result.success) {
        setMessageVariants(result.variants);
      } else {
        toast({ title: 'Error', description: result.error || 'Failed to generate messages', variant: 'destructive' });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to generate messages', variant: 'destructive' });
    } finally {
      setGeneratingMessages(false);
    }
  }

  /**
   * FIXED: Now sends the selected message variant's text to the backend
   */
  async function handleSendMessage() {
    if (!lead || !selectedVariant) return;
    setSendingMessage(true);
    try {
      // FIXED: Pass the selected variant's message body to the backend
      const result = await sendToLead(
        lead.id,
        messageContext,
        false,
        selectedVariant.message  // Pass the user-selected message!
      );
      
      if (result.success) {
        toast({ title: 'Message Sent', description: 'Outreach sent successfully' });
        setMessageDialogOpen(false);
        setSelectedVariant(null);
        fetchLead();
      } else {
        toast({ 
          title: 'Error', 
          description: result.error || 'Failed to send message', 
          variant: 'destructive' 
        });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to send message', variant: 'destructive' });
    } finally {
      setSendingMessage(false);
    }
  }

  // Disposition handlers
  async function handleMatchBuyers() {
    if (!lead) return;
    setLoadingMatches(true);
    try {
      const result = await matchBuyersToLead(lead.id, {
        offer_price: offer?.recommended_offer,
        limit: 20,
      });
      setBuyerMatches(result.matches);
      toast({ title: 'Buyers Matched', description: `Found ${result.total_matches} matching buyers` });
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to match buyers', variant: 'destructive' });
    } finally {
      setLoadingMatches(false);
    }
  }

  async function handleLoadDealSheet() {
    if (!lead) return;
    setLoadingDealSheet(true);
    try {
      const sheet = await getDealSheet(lead.id);
      setDealSheet(sheet);
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to generate deal sheet', variant: 'destructive' });
    } finally {
      setLoadingDealSheet(false);
    }
  }

  async function handleLoadCallScript() {
    if (!lead) return;
    setLoadingCallScript(true);
    try {
      const script = await getCallScript(lead.id);
      setCallScript(script);
      setCallScriptDialogOpen(true);
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to generate call script', variant: 'destructive' });
    } finally {
      setLoadingCallScript(false);
    }
  }

  async function handleSendBlast() {
    if (!lead) return;
    setBlasting(true);
    try {
      const selectedBuyerIds = buyerMatches.filter(m => m.match_percentage >= 50).map(m => m.buyer_id);
      const result = await sendBuyerBlast(lead.id, {
        buyer_ids: selectedBuyerIds.length > 0 ? selectedBuyerIds : undefined,
        min_match_score: 50,
        max_buyers: 10,
      });
      
      if (result.success) {
        toast({ 
          title: 'Blast Sent', 
          description: `Sent to ${result.buyers_blasted} buyers` 
        });
        setBlastDialogOpen(false);
        fetchLead();
      } else {
        toast({ 
          title: 'Blast Partial', 
          description: `Sent: ${result.buyers_blasted}, Skipped: ${result.buyers_skipped}`,
          variant: result.buyers_blasted === 0 ? 'destructive' : 'default',
        });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to send blast', variant: 'destructive' });
    } finally {
      setBlasting(false);
    }
  }

  async function fetchBuyerDeals() {
    if (!lead) return;
    try {
      const deals = await getDealsForLead(lead.id);
      setBuyerDeals(deals);
    } catch (error) {
      console.error('Failed to fetch buyer deals:', error);
    }
  }

  async function handleDeleteLead() {
    if (!lead) return;
    setDeleting(true);
    try {
      const result = await deleteLead(lead.id);
      if (result.success) {
        toast({ 
          title: 'Lead Deleted', 
          description: `Lead and ${result.outreach_deleted} outreach records deleted.` 
        });
        setDeleteDialogOpen(false);
        navigate('/leads');
      } else {
        toast({ title: 'Error', description: 'Failed to delete lead', variant: 'destructive' });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to delete lead', variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-muted-foreground">Lead not found</p>
        <Button variant="link" onClick={() => navigate('/leads')}>
          Back to Leads
        </Button>
      </div>
    );
  }

  // Check if lead is blocked from outreach
  const isOptedOut = lead.recent_outreach?.some(a => 
    a.reply_classification === 'DEAD' || a.reply_classification === 'NOT_INTERESTED'
  ) || lead.last_reply_classification === 'DEAD';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/leads')}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold">{lead.owner_name}</h2>
              <Badge className={STAGE_COLORS[lead.pipeline_stage]}>{lead.pipeline_stage}</Badge>
              {lead.motivation_score >= 75 && <Flame className="h-5 w-5 text-orange-500" />}
              {isOptedOut && (
                <Badge variant="destructive" className="flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  Opted Out
                </Badge>
              )}
            </div>
            <p className="text-muted-foreground">
              {lead.situs_address ? (
                lead.situs_address
              ) : (
                <span className="flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3 text-yellow-500" />
                  <span>Parcel {lead.parcel_id}, {lead.parish} Parish</span>
                  <Badge variant="outline" className="text-xs text-yellow-600 border-yellow-300 ml-1">
                    No Situs Address
                  </Badge>
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={lead.pipeline_stage}
            onValueChange={(v) => handleStageChange(v as PipelineStage)}
            disabled={updatingStage}
          >
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="NEW">New</SelectItem>
              <SelectItem value="CONTACTED">Contacted</SelectItem>
              <SelectItem value="HOT">Hot</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={handleRescore} disabled={rescoring}>
            <RefreshCw className={`mr-2 h-4 w-4 ${rescoring ? 'animate-spin' : ''}`} />
            Rescore
          </Button>
          <Button 
            onClick={() => handleGenerateMessages('intro')}
            disabled={isOptedOut}
            title={isOptedOut ? 'Cannot send to opted-out leads' : undefined}
          >
            <Send className="mr-2 h-4 w-4" />
            Send Message
          </Button>
          <Button 
            variant="destructive"
            onClick={() => setDeleteDialogOpen(true)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Lead</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this lead? This will permanently remove:
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>The lead record</li>
                <li>All outreach attempts ({lead.outreach_count || 0} records)</li>
                <li>All timeline events</li>
              </ul>
              <p className="mt-2 font-semibold text-destructive">This action cannot be undone.</p>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteLead} disabled={deleting}>
              {deleting ? 'Deleting...' : 'Delete Lead'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Main Content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left Column - Main Info */}
        <div className="space-y-6 lg:col-span-2">
          <Tabs defaultValue="details">
            <TabsList>
              <TabsTrigger value="details">Details</TabsTrigger>
              <TabsTrigger value="score">Score</TabsTrigger>
              <TabsTrigger value="comps">Comps</TabsTrigger>
              <TabsTrigger value="offer">Offer</TabsTrigger>
              <TabsTrigger value="dispo">Dispo</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
            </TabsList>

            <TabsContent value="details" className="space-y-4">
              {/* Owner Info */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <User className="h-5 w-5" />
                    Owner Information
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground">Name</p>
                    <p className="font-medium">{lead.owner_name}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground">Phone</p>
                    <div className="flex items-center gap-2">
                      <Phone className="h-4 w-4 text-muted-foreground" />
                      <p className="font-medium">{lead.owner_phone || 'Not available'}</p>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground">Email</p>
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <p className="font-medium">{lead.owner_email || 'Not available'}</p>
                    </div>
                  </div>
                  <div className="space-y-1 md:col-span-2">
                    <p className="text-sm text-muted-foreground font-medium">
                      Mailing Address (Raw)
                    </p>
                    <p className="text-sm text-muted-foreground italic mb-1">
                      Use for direct mail outreach
                    </p>
                    <div className="p-3 bg-muted rounded-md">
                      <p className="font-medium">{lead.mailing_address || 'Not available'}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Parcel Info */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Home className="h-5 w-5" />
                    Property Information
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Property Location - PARCEL DATA ONLY */}
                  <div className="p-4 border rounded-lg bg-muted/30">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-medium text-muted-foreground">
                        Property Location
                      </p>
                      {!lead.situs_address && (
                        <Badge variant="outline" className="text-xs text-yellow-600 border-yellow-300">
                          <AlertTriangle className="h-3 w-3 mr-1" />
                          No Situs Address
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-start gap-2">
                      <MapPin className="h-4 w-4 text-primary mt-0.5" />
                      <div>
                        {lead.situs_address ? (
                          <p className="font-medium">{lead.situs_address}</p>
                        ) : (
                          <p className="font-medium text-muted-foreground italic">
                            Parcel {lead.parcel_id}
                          </p>
                        )}
                        <p className="text-sm text-muted-foreground">
                          {lead.parish} Parish, {lead.market_code}
                        </p>
                      </div>
                    </div>
                    {!lead.situs_address && (
                      <p className="text-xs text-muted-foreground mt-2 italic">
                        ⚠️ No situs address on file. Use parcel ID for property identification.
                      </p>
                    )}
                  </div>
                  
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">Parcel ID</p>
                      <p className="font-mono text-sm bg-muted px-2 py-1 rounded">{lead.parcel_id}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">Parish / County</p>
                      <p className="font-medium">{lead.parish}</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">Acreage</p>
                      <p className="font-medium">{lead.acreage?.toFixed(2) || 'N/A'} acres</p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">Land Assessed Value</p>
                      <p className="font-medium">
                        {lead.land_value ? `$${lead.land_value.toLocaleString()}` : 'N/A'}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">Tax Delinquent</p>
                      <p className="font-medium">{lead.years_tax_delinquent} years</p>
                    </div>
                    <div className="space-y-1">
                      {lead.is_adjudicated && (
                        <Badge variant="destructive" className="w-fit">Adjudicated Property</Badge>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Map View - ALWAYS SHOW */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <MapPin className="h-5 w-5" />
                    Property Map
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {lead.latitude && lead.longitude ? (
                    <div className="space-y-3">
                      {/* Embedded Map */}
                      <div className="aspect-video rounded-lg overflow-hidden border">
                        <iframe
                          width="100%"
                          height="100%"
                          frameBorder="0"
                          style={{ border: 0 }}
                          src={`https://www.google.com/maps/embed/v1/place?key=${import.meta.env.VITE_GOOGLE_MAPS_API_KEY || 'AIzaSyBpBdmEbx2dJ_-TfiWtGW4sbTqAVkZfDvE'}&q=${lead.latitude},${lead.longitude}&zoom=16&maptype=satellite`}
                          allowFullScreen
                        />
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">
                          {lead.latitude.toFixed(6)}, {lead.longitude.toFixed(6)}
                        </span>
                        <a
                          href={`https://www.google.com/maps?q=${lead.latitude},${lead.longitude}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline flex items-center gap-1"
                        >
                          Open in Google Maps
                          <ChevronRight className="h-3 w-3" />
                        </a>
                      </div>
                    </div>
                  ) : (
                    <div className="aspect-video rounded-lg bg-muted flex items-center justify-center">
                      <div className="text-center">
                        <MapPin className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                        <p className="text-sm text-muted-foreground">
                          No coordinates available for this property
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Parcel ID: {lead.parcel_id}
                        </p>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="score">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Score Breakdown
                  </CardTitle>
                  <CardDescription>
                    Total Score: <span className="font-bold text-2xl">{lead.motivation_score}</span>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {scoreDetails?.factors && scoreDetails.factors.length > 0 ? (
                    <div className="space-y-3">
                      {scoreDetails.factors.map((factor, i) => (
                        <div key={i} className="flex items-center justify-between">
                          <span className="text-sm">{factor.label}</span>
                          <Badge
                            variant={factor.value > 0 ? 'default' : 'outline'}
                            className={factor.value > 0 ? 'bg-green-500' : ''}
                          >
                            {factor.value > 0 ? '+' : ''}{factor.value}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No score details available. Click "Rescore" to generate.</p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="comps">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    Comparable Sales
                    {comps?.is_mock_data && (
                      <Badge variant="outline" className="ml-2">Mock Data</Badge>
                    )}
                  </CardTitle>
                  {comps && comps.total_comps_found > 0 && comps.avg_price_per_acre && (
                    <CardDescription>
                      Avg: ${comps.avg_price_per_acre.toLocaleString()}/acre
                      {comps.min_price_per_acre && comps.max_price_per_acre && (
                        <> • Range: ${comps.min_price_per_acre.toLocaleString()} - ${comps.max_price_per_acre.toLocaleString()}</>
                      )}
                    </CardDescription>
                  )}
                </CardHeader>
                <CardContent>
                  {comps?.comps?.length ? (
                    <div className="space-y-3">
                      {comps.comps.map((comp, i) => (
                        <div key={i} className="flex items-center justify-between border-b pb-2">
                          <div>
                            <p className="font-medium text-sm">{comp.address}</p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(comp.sale_date).toLocaleDateString()} • {comp.lot_size_acres.toFixed(2)} acres
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="font-medium">${comp.sale_price.toLocaleString()}</p>
                            <p className="text-xs text-muted-foreground">
                              ${comp.price_per_acre.toLocaleString()}/acre
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No comparable sales found</p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="offer">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Calculator className="h-5 w-5" />
                    Offer Calculator
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {offer ? (
                    <div className="space-y-4">
                      <div className="text-center py-4 bg-primary/10 rounded-lg">
                        <p className="text-sm text-muted-foreground">Recommended Offer</p>
                        <p className="text-4xl font-bold text-primary">
                          ${offer.recommended_offer.toLocaleString()}
                        </p>
                        <p className="text-sm text-muted-foreground mt-1">
                          Range: ${offer.low_offer.toLocaleString()} - ${offer.high_offer.toLocaleString()}
                        </p>
                      </div>
                      <div className="space-y-2">
                        {offer.explanation.map((line, i) => (
                          <p key={i} className="text-sm text-muted-foreground">• {line}</p>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <Calculator className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                      <Button onClick={handleCalculateOffer}>Calculate Offer</Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="dispo" className="space-y-4">
              {/* Deal Sheet */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    Deal Sheet
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {dealSheet ? (
                    <div className="space-y-4">
                      <div className="grid gap-4 md:grid-cols-3">
                        <div className="p-4 bg-primary/10 rounded-lg text-center">
                          <p className="text-sm text-muted-foreground">Recommended Offer</p>
                          <p className="text-2xl font-bold">${dealSheet.recommended_offer.toLocaleString()}</p>
                        </div>
                        <div className="p-4 bg-green-500/10 rounded-lg text-center">
                          <p className="text-sm text-muted-foreground">Retail Estimate</p>
                          <p className="text-2xl font-bold text-green-600">${dealSheet.retail_estimate.toLocaleString()}</p>
                        </div>
                        <div className="p-4 bg-purple-500/10 rounded-lg text-center">
                          <p className="text-sm text-muted-foreground">Assignment Potential</p>
                          <p className="text-2xl font-bold text-purple-600">${dealSheet.assignment_potential.toLocaleString()}</p>
                          <p className="text-xs text-muted-foreground">{dealSheet.assignment_percentage.toFixed(0)}% spread</p>
                        </div>
                      </div>
                      {dealSheet.ai_description && (
                        <div className="p-4 border rounded-lg">
                          <p className="text-sm font-medium mb-2">AI Description</p>
                          <p className="text-sm text-muted-foreground">{dealSheet.ai_description}</p>
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground">Generated: {new Date(dealSheet.generated_at).toLocaleString()}</p>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                      <Button onClick={handleLoadDealSheet} disabled={loadingDealSheet}>
                        {loadingDealSheet ? 'Generating...' : 'Generate Deal Sheet'}
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Buyer Matching */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Users className="h-5 w-5" />
                    Matched Buyers ({buyerMatches.length})
                  </CardTitle>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={handleMatchBuyers} disabled={loadingMatches}>
                      {loadingMatches ? 'Matching...' : 'Match Buyers'}
                    </Button>
                    {buyerMatches.length > 0 && (
                      <Button onClick={() => setBlastDialogOpen(true)}>
                        <Zap className="mr-2 h-4 w-4" />
                        Send Blast
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {buyerMatches.length > 0 ? (
                    <div className="space-y-3">
                      {buyerMatches.slice(0, 5).map((match) => (
                        <div key={match.buyer_id} className="flex items-center justify-between p-3 border rounded-lg">
                          <div className="flex items-center gap-3">
                            {match.vip && <Badge className="bg-yellow-500">VIP</Badge>}
                            {match.pof_verified && <Badge className="bg-green-500">POF</Badge>}
                            <div>
                              <p className="font-medium">{match.buyer_name}</p>
                              <p className="text-xs text-muted-foreground">{match.buyer_phone}</p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="font-bold text-lg">{match.match_percentage.toFixed(0)}%</p>
                            <p className="text-xs text-muted-foreground">Match Score</p>
                          </div>
                        </div>
                      ))}
                      {buyerMatches.length > 5 && (
                        <p className="text-sm text-muted-foreground text-center">
                          +{buyerMatches.length - 5} more buyers
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="text-center text-muted-foreground py-4">
                      Click "Match Buyers" to find interested buyers
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Active Buyer Deals */}
              {buyerDeals.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <DollarSign className="h-5 w-5" />
                      Active Deals ({buyerDeals.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {buyerDeals.map((deal) => (
                        <div key={deal.id} className="flex items-center justify-between p-3 border rounded-lg">
                          <div>
                            <p className="font-medium">{deal.buyer_name || `Buyer #${deal.buyer_id}`}</p>
                            <Badge variant="outline">{deal.stage}</Badge>
                          </div>
                          <div className="text-right">
                            {deal.offer_amount && <p className="font-bold">${deal.offer_amount.toLocaleString()}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="timeline">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Clock className="h-5 w-5" />
                    Activity Timeline
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {timeline.length > 0 ? (
                    <div className="space-y-4">
                      {timeline.map((event) => (
                        <div key={event.id} className="flex gap-3 border-l-2 border-muted pl-4 pb-4">
                          <div className="flex-1">
                            <p className="font-medium text-sm">{event.title}</p>
                            {event.description && (
                              <p className="text-xs text-muted-foreground">{event.description}</p>
                            )}
                            <p className="text-xs text-muted-foreground mt-1">
                              {new Date(event.created_at).toLocaleString()}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">No activity yet</p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        {/* Right Column - Actions & Outreach */}
        <div className="space-y-6">
          {/* Quick Stats */}
          <Card>
            <CardHeader>
              <CardTitle>Quick Stats</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Score</span>
                <span className="font-bold">{lead.motivation_score}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Outreach</span>
                <span className="font-bold">{lead.outreach_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Followups</span>
                <span className="font-bold">{lead.followup_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">TCPA Safe</span>
                <Badge variant={lead.is_tcpa_safe ? 'default' : 'secondary'}>
                  {lead.is_tcpa_safe ? 'Yes' : 'No'}
                </Badge>
              </div>
              {lead.last_reply_classification && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last Reply</span>
                  <Badge 
                    variant={lead.last_reply_classification === 'DEAD' ? 'destructive' : 'outline'}
                  >
                    {lead.last_reply_classification}
                  </Badge>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Message Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                Send Message
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {isOptedOut && (
                <p className="text-sm text-destructive mb-3">
                  This lead has opted out and cannot receive messages.
                </p>
              )}
              <Button
                className="w-full"
                variant="outline"
                onClick={() => handleGenerateMessages('intro')}
                disabled={isOptedOut}
              >
                Generate Intro
              </Button>
              <Button
                className="w-full"
                variant="outline"
                onClick={() => handleGenerateMessages('followup')}
                disabled={isOptedOut}
              >
                Generate Followup
              </Button>
              <Button
                className="w-full"
                variant="outline"
                onClick={() => handleGenerateMessages('final')}
                disabled={isOptedOut}
              >
                Generate Final
              </Button>
            </CardContent>
          </Card>

          {/* Disposition Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Disposition
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button
                className="w-full"
                variant="outline"
                onClick={handleLoadCallScript}
                disabled={loadingCallScript}
              >
                <PhoneCall className="mr-2 h-4 w-4" />
                {loadingCallScript ? 'Generating...' : 'Call Script'}
              </Button>
              <Button
                className="w-full"
                variant="outline"
                onClick={handleLoadDealSheet}
                disabled={loadingDealSheet}
              >
                <FileText className="mr-2 h-4 w-4" />
                {loadingDealSheet ? 'Generating...' : 'Deal Sheet'}
              </Button>
              <Button
                className="w-full"
                variant="outline"
                onClick={handleMatchBuyers}
                disabled={loadingMatches}
              >
                <Users className="mr-2 h-4 w-4" />
                {loadingMatches ? 'Matching...' : 'Match Buyers'}
              </Button>
            </CardContent>
          </Card>

          {/* Recent Outreach */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Outreach</CardTitle>
            </CardHeader>
            <CardContent>
              {lead.recent_outreach?.length > 0 ? (
                <div className="space-y-3">
                  {lead.recent_outreach.slice(0, 5).map((attempt) => (
                    <div key={attempt.id} className="border-b pb-2">
                      <div className="flex items-center justify-between">
                        <Badge variant="outline">{attempt.status}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {attempt.created_at ? new Date(attempt.created_at).toLocaleDateString() : ''}
                        </span>
                      </div>
                      {attempt.reply_classification && (
                        <Badge 
                          className="mt-1" 
                          variant={attempt.reply_classification === 'DEAD' ? 'destructive' : 'secondary'}
                        >
                          {attempt.reply_classification}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">No outreach yet</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Message Generation Dialog */}
      <Dialog open={messageDialogOpen} onOpenChange={setMessageDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Generate {messageContext.charAt(0).toUpperCase() + messageContext.slice(1)} Message</DialogTitle>
            <DialogDescription>
              Select a message variant to send to {lead.owner_name}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {generatingMessages ? (
              <div className="space-y-3">
                <Skeleton className="h-24" />
                <Skeleton className="h-24" />
                <Skeleton className="h-24" />
              </div>
            ) : messageVariants.length > 0 ? (
              messageVariants.map((variant) => (
                <div
                  key={variant.style}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selectedVariant?.style === variant.style}
                  className={`border rounded-lg p-4 cursor-pointer transition-colors ${
                    selectedVariant?.style === variant.style
                      ? 'border-primary bg-primary/5'
                      : 'hover:border-muted-foreground'
                  }`}
                  onClick={() => setSelectedVariant(variant)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedVariant(variant);
                    }
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <Badge variant="outline" className="capitalize">
                      {variant.style}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {variant.message.length} chars
                    </span>
                  </div>
                  <p className="text-sm">{variant.message}</p>
                </div>
              ))
            ) : (
              <p className="text-center text-muted-foreground">No variants generated yet.</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMessageDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSendMessage}
              disabled={!selectedVariant || sendingMessage}
            >
              {sendingMessage ? 'Sending...' : 'Send Message'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Buyer Blast Dialog */}
      <Dialog open={blastDialogOpen} onOpenChange={setBlastDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Send Buyer Blast
            </DialogTitle>
            <DialogDescription>
              Send this deal to {buyerMatches.filter(m => m.match_percentage >= 50).length} matching buyers
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {dealSheet && (
              <div className="p-4 border rounded-lg bg-muted/50">
                <p className="font-medium mb-2">Deal Summary</p>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Price</p>
                    <p className="font-bold">${dealSheet.recommended_offer.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Acreage</p>
                    <p className="font-bold">{dealSheet.acreage.toFixed(2)} ac</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Spread</p>
                    <p className="font-bold text-green-600">${dealSheet.assignment_potential.toLocaleString()}</p>
                  </div>
                </div>
              </div>
            )}
            <div>
              <p className="font-medium mb-2">Selected Buyers ({buyerMatches.filter(m => m.match_percentage >= 50).length})</p>
              <div className="max-h-48 overflow-y-auto space-y-2">
                {buyerMatches.filter(m => m.match_percentage >= 50).map((match) => (
                  <div key={match.buyer_id} className="flex items-center justify-between p-2 border rounded">
                    <div className="flex items-center gap-2">
                      {match.vip && <Badge className="bg-yellow-500 text-xs">VIP</Badge>}
                      <span className="font-medium">{match.buyer_name}</span>
                    </div>
                    <span className="text-sm text-muted-foreground">{match.match_percentage.toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBlastDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSendBlast} disabled={blasting}>
              <Zap className="mr-2 h-4 w-4" />
              {blasting ? 'Sending...' : 'Send Blast'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Call Script Dialog */}
      <Dialog open={callScriptDialogOpen} onOpenChange={setCallScriptDialogOpen}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PhoneCall className="h-5 w-5" />
              Call Script for {lead.owner_name}
            </DialogTitle>
            <DialogDescription>
              {lead.situs_address || lead.city}
            </DialogDescription>
          </DialogHeader>
          {callScript && (
            <div className="space-y-6 py-4">
              {/* Opening */}
              <div className="space-y-2">
                <h4 className="font-bold text-lg border-b pb-2">Opening</h4>
                <div className="p-3 bg-primary/10 rounded-lg">
                  <p className="text-sm">{callScript.opening_line}</p>
                </div>
                <p className="text-sm text-muted-foreground italic">{callScript.rapport_builder}</p>
              </div>

              {/* Discovery */}
              <div className="space-y-2">
                <h4 className="font-bold text-lg border-b pb-2">Discovery Questions</h4>
                <ul className="space-y-1">
                  {callScript.discovery_questions.map((q, i) => (
                    <li key={i} className="text-sm flex gap-2">
                      <span className="text-primary font-bold">{i + 1}.</span>
                      {q}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Negotiation */}
              <div className="space-y-2">
                <h4 className="font-bold text-lg border-b pb-2">Negotiation</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Anchor Price</p>
                    <p className="text-xl font-bold">${callScript.anchor_price.toLocaleString()}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Walk Away</p>
                    <p className="text-xl font-bold">${callScript.walk_away_price.toLocaleString()}</p>
                  </div>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <p className="text-sm font-medium mb-1">Negotiation Angle</p>
                  <p className="text-sm">{callScript.negotiation_angle}</p>
                </div>
                <div className="p-3 border rounded-lg">
                  <p className="text-sm font-medium mb-1">Price Justification</p>
                  <p className="text-sm text-muted-foreground">{callScript.price_justification}</p>
                </div>
              </div>

              {/* Objections */}
              <div className="space-y-2">
                <h4 className="font-bold text-lg border-b pb-2">Objection Handling</h4>
                <div className="space-y-3">
                  {callScript.objections.map((obj, i) => (
                    <div key={i} className="border rounded-lg overflow-hidden">
                      <div className="p-2 bg-red-500/10">
                        <p className="text-sm font-medium">"{obj.objection}"</p>
                      </div>
                      <div className="p-2 bg-green-500/10">
                        <p className="text-sm">{obj.response}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Closing */}
              <div className="space-y-2">
                <h4 className="font-bold text-lg border-b pb-2">Closing</h4>
                <div className="p-3 bg-primary/10 rounded-lg">
                  <p className="text-sm">{callScript.closing_script}</p>
                </div>
                <div className="p-3 border rounded-lg">
                  <p className="text-sm font-medium mb-1">Create Urgency</p>
                  <p className="text-sm text-muted-foreground">{callScript.urgency_creator}</p>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <p className="text-sm font-medium mb-1">Next Steps</p>
                  <p className="text-sm">{callScript.next_steps}</p>
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setCallScriptDialogOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default LeadDetail;