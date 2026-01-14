/**
 * Today's Work - The primary sales-call-first workflow
 * 
 * This is the default landing experience after selecting a market.
 * - Active Market only
 * - HOT leads first
 * - One lead → one action
 * - No filters, no configuration
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Phone, 
  Flame, 
  Users, 
  MapPin, 
  AlertCircle,
  ChevronRight,
  DollarSign,
  Home,
  CheckCircle,
  XCircle,
  PhoneOff,
  Voicemail,
  Calendar,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { useActiveMarket } from '@/components/active-market-provider';
import { 
  getCallerSheet, 
  logCallOutcome,
  type CallerSheet, 
  type CallerSheetLead,
  type CallOutcome,
} from '@/api/caller';
import { useToast } from '@/components/ui/use-toast';

export function TodaysWork() {
  const navigate = useNavigate();
  const { activeMarket } = useActiveMarket();
  const { toast } = useToast();
  
  const [callerSheet, setCallerSheet] = useState<CallerSheet | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Current lead being called
  const [currentLead, setCurrentLead] = useState<CallerSheetLead | null>(null);
  const [showOutcomeDialog, setShowOutcomeDialog] = useState(false);
  const [outcomeNotes, setOutcomeNotes] = useState('');
  const [callbackDate, setCallbackDate] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Load caller sheet
  useEffect(() => {
    async function loadSheet() {
      if (!activeMarket?.active) return;
      
      setIsLoading(true);
      setError(null);
      
      try {
        const sheet = await getCallerSheet(50);
        setCallerSheet(sheet);
        
        // Auto-select first lead
        if (sheet.leads.length > 0) {
          setCurrentLead(sheet.leads[0]);
        }
      } catch (err: any) {
        if (err.response?.data?.error === 'no_active_market') {
          setError('Please select a working area first.');
        } else {
          setError(err.response?.data?.message || 'Failed to load caller sheet');
        }
      } finally {
        setIsLoading(false);
      }
    }
    
    loadSheet();
  }, [activeMarket]);

  const handleStartCall = (lead: CallerSheetLead) => {
    setCurrentLead(lead);
  };

  const handleLogOutcome = async (outcome: CallOutcome) => {
    if (!currentLead) return;
    
    setIsSubmitting(true);
    try {
      const result = await logCallOutcome(
        currentLead.id,
        outcome,
        outcomeNotes || undefined,
        outcome === 'call_back' ? callbackDate || undefined : undefined
      );
      
      toast({
        title: 'Outcome Logged',
        description: result.message,
      });
      
      // Remove lead from list and move to next
      if (callerSheet) {
        const newLeads = callerSheet.leads.filter(l => l.id !== currentLead.id);
        setCallerSheet({ ...callerSheet, leads: newLeads });
        setCurrentLead(newLeads[0] || null);
      }
      
      setShowOutcomeDialog(false);
      setOutcomeNotes('');
      setCallbackDate('');
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.response?.data?.message || 'Failed to log outcome',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (error || !callerSheet) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <AlertCircle className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">Unable to Load Work Queue</h3>
          <p className="text-muted-foreground text-center max-w-md">
            {error || callerSheet?.unavailable_reason || 'Unknown error'}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (callerSheet.unavailable_reason) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Today's Work</h1>
            <p className="text-muted-foreground">{callerSheet.active_market.display_name}</p>
          </div>
        </div>
        
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <AlertCircle className="h-12 w-12 text-yellow-500 mb-4" />
            <h3 className="text-lg font-semibold mb-2">No Leads Available</h3>
            <p className="text-muted-foreground text-center max-w-md mb-4">
              {callerSheet.unavailable_reason}
            </p>
            <Button onClick={() => navigate('/ingestion')}>
              Go to Ingestion
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Today's Work</h1>
          <div className="flex items-center gap-2 text-muted-foreground">
            <MapPin className="h-4 w-4" />
            <span>{callerSheet.active_market.display_name}</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-2xl font-bold">{callerSheet.total_eligible}</div>
            <div className="text-sm text-muted-foreground">leads to call</div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <div className="p-3 rounded-full bg-red-500/10">
              <Flame className="h-6 w-6 text-red-500" />
            </div>
            <div>
              <div className="text-2xl font-bold">{callerSheet.hot_count}</div>
              <div className="text-sm text-muted-foreground">Hot Leads</div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <div className="p-3 rounded-full bg-blue-500/10">
              <Users className="h-6 w-6 text-blue-500" />
            </div>
            <div>
              <div className="text-2xl font-bold">{callerSheet.contact_count}</div>
              <div className="text-sm text-muted-foreground">Contact Ready</div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <div className="p-3 rounded-full bg-green-500/10">
              <Phone className="h-6 w-6 text-green-500" />
            </div>
            <div>
              <div className="text-2xl font-bold">{callerSheet.leads.length}</div>
              <div className="text-sm text-muted-foreground">In Queue</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Current Lead Card */}
      {currentLead && (
        <Card className="border-2 border-primary">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge variant={currentLead.tier === 'HOT' ? 'destructive' : 'default'}>
                  {currentLead.tier === 'HOT' && <Flame className="h-3 w-3 mr-1" />}
                  {currentLead.tier}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  Score: {currentLead.motivation_score}
                </span>
              </div>
              <Button
                size="lg"
                className="gap-2"
                onClick={() => setShowOutcomeDialog(true)}
              >
                <Phone className="h-5 w-5" />
                Log Call Outcome
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-2 gap-6">
              {/* Owner Info */}
              <div className="space-y-3">
                <h3 className="font-semibold text-lg">{currentLead.owner_name}</h3>
                <div className="flex items-center gap-2 text-xl font-mono">
                  <Phone className="h-5 w-5 text-green-500" />
                  <a href={`tel:${currentLead.phone}`} className="hover:underline">
                    {currentLead.phone}
                  </a>
                </div>
                {currentLead.mailing_address && (
                  <div className="text-sm text-muted-foreground">
                    <div className="font-medium">Mailing Address</div>
                    {currentLead.mailing_address}
                  </div>
                )}
              </div>
              
              {/* Property Info */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Home className="h-4 w-4" />
                  <span className="font-mono">{currentLead.parcel_id}</span>
                </div>
                {currentLead.property_address && (
                  <div className="text-sm">
                    <div className="font-medium">Property Location</div>
                    {currentLead.property_address}
                  </div>
                )}
                <div className="flex items-center gap-4 text-sm">
                  {currentLead.acreage && (
                    <span>{currentLead.acreage.toFixed(2)} acres</span>
                  )}
                  {currentLead.land_value && (
                    <span className="flex items-center gap-1">
                      <DollarSign className="h-3 w-3" />
                      {currentLead.land_value.toLocaleString()}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {currentLead.is_adjudicated && (
                    <Badge variant="outline" className="text-red-500 border-red-500">
                      Adjudicated
                    </Badge>
                  )}
                  {currentLead.years_delinquent > 0 && (
                    <Badge variant="outline" className="text-yellow-500 border-yellow-500">
                      {currentLead.years_delinquent}yr delinquent
                    </Badge>
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Lead Queue */}
      <Card>
        <CardHeader>
          <CardTitle>Call Queue</CardTitle>
          <CardDescription>
            {callerSheet.leads.length} leads remaining • HOT leads first
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {callerSheet.leads.map((lead, idx) => (
              <div
                key={lead.id}
                className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors ${
                  currentLead?.id === lead.id 
                    ? 'border-primary bg-primary/5' 
                    : 'hover:bg-muted/50'
                }`}
                onClick={() => handleStartCall(lead)}
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 text-center text-muted-foreground font-mono">
                    {idx + 1}
                  </div>
                  <Badge variant={lead.tier === 'HOT' ? 'destructive' : 'secondary'} className="w-16 justify-center">
                    {lead.tier}
                  </Badge>
                  <div>
                    <div className="font-medium">{lead.owner_name}</div>
                    <div className="text-sm text-muted-foreground">{lead.phone}</div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right text-sm">
                    <div>{lead.acreage?.toFixed(2) || '—'} ac</div>
                    <div className="text-muted-foreground">Score: {lead.motivation_score}</div>
                  </div>
                  <ChevronRight className="h-5 w-5 text-muted-foreground" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Outcome Dialog */}
      <Dialog open={showOutcomeDialog} onOpenChange={setShowOutcomeDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Log Call Outcome</DialogTitle>
            <DialogDescription>
              {currentLead?.owner_name} • {currentLead?.phone}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {/* Quick Outcome Buttons */}
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                className="h-16 flex-col gap-1 border-green-500 hover:bg-green-500/10"
                onClick={() => handleLogOutcome('interested')}
                disabled={isSubmitting}
              >
                <CheckCircle className="h-5 w-5 text-green-500" />
                <span>Interested!</span>
              </Button>
              <Button
                variant="outline"
                className="h-16 flex-col gap-1 border-gray-500 hover:bg-gray-500/10"
                onClick={() => handleLogOutcome('not_interested')}
                disabled={isSubmitting}
              >
                <XCircle className="h-5 w-5 text-gray-500" />
                <span>Not Interested</span>
              </Button>
              <Button
                variant="outline"
                className="h-16 flex-col gap-1 border-yellow-500 hover:bg-yellow-500/10"
                onClick={() => handleLogOutcome('call_back')}
                disabled={isSubmitting}
              >
                <Calendar className="h-5 w-5 text-yellow-500" />
                <span>Call Back</span>
              </Button>
              <Button
                variant="outline"
                className="h-16 flex-col gap-1 border-blue-500 hover:bg-blue-500/10"
                onClick={() => handleLogOutcome('no_answer')}
                disabled={isSubmitting}
              >
                <PhoneOff className="h-5 w-5 text-blue-500" />
                <span>No Answer</span>
              </Button>
              <Button
                variant="outline"
                className="h-16 flex-col gap-1 border-purple-500 hover:bg-purple-500/10"
                onClick={() => handleLogOutcome('voicemail')}
                disabled={isSubmitting}
              >
                <Voicemail className="h-5 w-5 text-purple-500" />
                <span>Voicemail</span>
              </Button>
              <Button
                variant="outline"
                className="h-16 flex-col gap-1 border-red-500 hover:bg-red-500/10"
                onClick={() => handleLogOutcome('wrong_number')}
                disabled={isSubmitting}
              >
                <Phone className="h-5 w-5 text-red-500" />
                <span>Wrong #</span>
              </Button>
            </div>
            
            {/* Notes */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Notes (optional)</label>
              <Textarea
                placeholder="Any notes from the call..."
                value={outcomeNotes}
                onChange={(e) => setOutcomeNotes(e.target.value)}
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default TodaysWork;

