/**
 * Dashboard - Mission Control
 * 
 * This is the landing page that tells the user exactly what to do next.
 * 
 * Primary CTAs:
 * - Send Batch SMS (with size selector and confirmation)
 * - Open Inbox
 * - View YES Queue
 * 
 * Shows funnel progress, response rate, and key metrics.
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare,
  Send,
  Users,
  Flame,
  ChevronRight,
  Phone,
  Check,
  TrendingUp,
  ArrowRight,
  Inbox,
  MapPin,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { useActiveMarket } from '@/components/active-market-provider';
import { getLeadStatistics } from '@/api/leads';
import { getConversationStats, type ConversationStats } from '@/api/conversations';
import type { LeadStatistics } from '@/lib/types';

export function Dashboard() {
  const navigate = useNavigate();
  const { activeMarket } = useActiveMarket();
  const [loading, setLoading] = useState(true);
  const [leadStats, setLeadStats] = useState<LeadStatistics | null>(null);
  const [convStats, setConvStats] = useState<ConversationStats | null>(null);
  
  // Batch send modal state
  const [batchModalOpen, setBatchModalOpen] = useState(false);
  const [batchSize, setBatchSize] = useState<string>('25');
  const [batchConfirmed, setBatchConfirmed] = useState(false);

  useEffect(() => {
    async function fetchData() {
      if (!activeMarket?.active) {
        setLoading(false);
        return;
      }
      
      setLoading(true);
      try {
        const market = activeMarket.market_code as 'LA' | 'TX' | 'MS' | 'AR' | 'AL';
        const [leads, conversations] = await Promise.all([
          getLeadStatistics(market),
          getConversationStats(market),
        ]);
        setLeadStats(leads);
        setConvStats(conversations);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [activeMarket]);

  // Calculate funnel metrics
  const totalLeads = leadStats?.total_leads || 0;
  const tcpaSafe = leadStats?.tcpa_safe_leads || 0;
  const contacted = convStats?.total_threads || 0;
  const replied = (convStats?.yes_queue || 0) + (convStats?.maybe_queue || 0) + (convStats?.unread || 0);
  const yesQueue = convStats?.yes_queue || 0;
  const unread = convStats?.unread || 0;
  
  // Calculate response rate
  const responseRate = contacted > 0 ? Math.round((replied / contacted) * 100) : 0;

  // Handle batch send
  const handleBatchSend = () => {
    // Navigate to outreach with batch size param
    navigate(`/outreach?batch_size=${batchSize}`);
    setBatchModalOpen(false);
    setBatchConfirmed(false);
  };

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
        <Skeleton className="h-32" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            {activeMarket?.active 
              ? `Working in ${activeMarket.display_name}`
              : 'Select a market to get started'}
          </p>
        </div>
        {activeMarket?.active && (
          <Badge variant="outline" className="text-sm">
            <MapPin className="h-3 w-3 mr-1" />
            {activeMarket.display_name}
          </Badge>
        )}
      </div>

      {/* Primary Action Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* Send Batch SMS */}
        <Card className="border-2 hover:border-primary transition-colors cursor-pointer" onClick={() => setBatchModalOpen(true)}>
          <CardHeader className="pb-2">
            <div className="w-12 h-12 rounded-lg bg-blue-500/10 flex items-center justify-center mb-2">
              <Send className="h-6 w-6 text-blue-500" />
            </div>
            <CardTitle className="text-lg">Send Batch SMS</CardTitle>
            <CardDescription>Text qualified sellers in your market</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">{tcpaSafe}</p>
                <p className="text-sm text-muted-foreground">Ready to text</p>
              </div>
              <Button size="sm" onClick={(e) => { e.stopPropagation(); setBatchModalOpen(true); }}>
                Send
                <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Open Inbox */}
        <Card 
          className={`border-2 hover:border-primary transition-colors cursor-pointer ${unread > 0 ? 'border-red-500' : ''}`}
          onClick={() => navigate('/inbox')}
        >
          <CardHeader className="pb-2">
            <div className="w-12 h-12 rounded-lg bg-purple-500/10 flex items-center justify-center mb-2 relative">
              <Inbox className="h-6 w-6 text-purple-500" />
              {unread > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">
                  {unread}
                </span>
              )}
            </div>
            <CardTitle className="text-lg">Open Inbox</CardTitle>
            <CardDescription>View and classify seller replies</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">{contacted}</p>
                <p className="text-sm text-muted-foreground">Conversations</p>
              </div>
              <Button size="sm" variant={unread > 0 ? 'default' : 'outline'}>
                {unread > 0 ? `${unread} Unread` : 'View'}
                <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* YES Queue */}
        <Card 
          className={`border-2 hover:border-primary transition-colors cursor-pointer ${yesQueue > 0 ? 'border-green-500' : ''}`}
          onClick={() => navigate('/inbox?filter=yes')}
        >
          <CardHeader className="pb-2">
            <div className="w-12 h-12 rounded-lg bg-green-500/10 flex items-center justify-center mb-2">
              <Check className="h-6 w-6 text-green-500" />
            </div>
            <CardTitle className="text-lg">YES Queue</CardTitle>
            <CardDescription>Qualified leads ready for calls</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-green-600">{yesQueue}</p>
                <p className="text-sm text-muted-foreground">Ready to call</p>
              </div>
              <Button size="sm" variant={yesQueue > 0 ? 'default' : 'outline'} className={yesQueue > 0 ? 'bg-green-500 hover:bg-green-600' : ''}>
                <Phone className="h-4 w-4 mr-1" />
                Call
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Funnel Progress */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Your Funnel
          </CardTitle>
          <CardDescription>
            Track your progress from leads to deals
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-4">
            {/* Funnel Steps */}
            <div className="flex-1 flex items-center gap-2">
              <div className="text-center flex-1">
                <div className="text-2xl font-bold">{totalLeads}</div>
                <div className="text-xs text-muted-foreground">Total Leads</div>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
              <div className="text-center flex-1">
                <div className="text-2xl font-bold">{tcpaSafe}</div>
                <div className="text-xs text-muted-foreground">TCPA Safe</div>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
              <div className="text-center flex-1">
                <div className="text-2xl font-bold">{contacted}</div>
                <div className="text-xs text-muted-foreground">Contacted</div>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
              <div className="text-center flex-1">
                <div className="text-2xl font-bold">{replied}</div>
                <div className="text-xs text-muted-foreground">Replied</div>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
              <div className="text-center flex-1">
                <div className="text-2xl font-bold text-green-600">{yesQueue}</div>
                <div className="text-xs text-muted-foreground">YES</div>
              </div>
            </div>
          </div>
          
          {/* Progress Bar */}
          <div className="mt-4">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Funnel Progress</span>
              <span className="font-medium">
                {tcpaSafe > 0 ? Math.round((yesQueue / tcpaSafe) * 100) : 0}% conversion
              </span>
            </div>
            <Progress value={tcpaSafe > 0 ? (yesQueue / tcpaSafe) * 100 : 0} className="h-2" />
          </div>
          
          {/* Response Rate */}
          <div className="mt-4 pt-4 border-t">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm text-muted-foreground">Response Rate (All Time)</span>
                <p className="text-2xl font-bold">{responseRate}%</p>
              </div>
              <div className="text-right">
                <span className="text-sm text-muted-foreground">Replied / Contacted</span>
                <p className="text-lg font-medium">{replied} / {contacted}</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* What's Next Section */}
      <Card>
        <CardHeader>
          <CardTitle>What's Next?</CardTitle>
          <CardDescription>
            Recommended actions based on your pipeline
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Priority 1: Unread replies */}
          {unread > 0 && (
            <div 
              className="flex items-center justify-between p-4 rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 cursor-pointer hover:bg-red-100 dark:hover:bg-red-950/30 transition-colors"
              onClick={() => navigate('/inbox?filter=unread')}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-red-500 flex items-center justify-center">
                  <MessageSquare className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="font-medium">You have {unread} unread replies!</p>
                  <p className="text-sm text-muted-foreground">Classify them to move deals forward</p>
                </div>
              </div>
              <Button variant="destructive" size="sm">
                View Now
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          )}

          {/* Priority 2: YES queue */}
          {yesQueue > 0 && (
            <div 
              className="flex items-center justify-between p-4 rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 cursor-pointer hover:bg-green-100 dark:hover:bg-green-950/30 transition-colors"
              onClick={() => navigate('/inbox?filter=yes')}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-green-500 flex items-center justify-center">
                  <Phone className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="font-medium">{yesQueue} sellers said YES</p>
                  <p className="text-sm text-muted-foreground">Open their Call Prep Pack and make the call</p>
                </div>
              </div>
              <Button className="bg-green-500 hover:bg-green-600" size="sm">
                Start Calling
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          )}

          {/* Priority 3: Send more texts */}
          {tcpaSafe > contacted && (
            <div 
              className="flex items-center justify-between p-4 rounded-lg bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-950/30 transition-colors"
              onClick={() => navigate('/outreach')}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center">
                  <Send className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="font-medium">{tcpaSafe - contacted} sellers haven't been texted</p>
                  <p className="text-sm text-muted-foreground">Send a batch to start more conversations</p>
                </div>
              </div>
              <Button variant="outline" size="sm">
                Send Batch
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          )}

          {/* No actions needed */}
          {unread === 0 && yesQueue === 0 && tcpaSafe <= contacted && (
            <div className="flex items-center justify-center p-8 text-center text-muted-foreground">
              <div>
                <Check className="h-12 w-12 mx-auto mb-4 text-green-500" />
                <p className="font-medium">You're all caught up!</p>
                <p className="text-sm">Check back later for new replies</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Links */}
      <div className="grid gap-4 md:grid-cols-4">
        <Button variant="outline" className="h-auto py-4 flex-col" onClick={() => navigate('/leads')}>
          <Users className="h-5 w-5 mb-2" />
          <span>All Leads</span>
          <span className="text-xs text-muted-foreground">{totalLeads}</span>
        </Button>
        <Button variant="outline" className="h-auto py-4 flex-col" onClick={() => navigate('/leads?pipeline_stage=HOT')}>
          <Flame className="h-5 w-5 mb-2 text-red-500" />
          <span>Hot Leads</span>
          <span className="text-xs text-muted-foreground">{leadStats?.hot_leads || 0}</span>
        </Button>
        <Button variant="outline" className="h-auto py-4 flex-col" onClick={() => navigate('/buyers')}>
          <Users className="h-5 w-5 mb-2" />
          <span>Buyers</span>
          <span className="text-xs text-muted-foreground">Manage</span>
        </Button>
        <Button variant="outline" className="h-auto py-4 flex-col" onClick={() => navigate('/comps')}>
          <TrendingUp className="h-5 w-5 mb-2" />
          <span>Comps</span>
          <span className="text-xs text-muted-foreground">Research</span>
        </Button>
      </div>

      {/* Batch Send Modal */}
      <Dialog open={batchModalOpen} onOpenChange={setBatchModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="h-5 w-5" />
              Send Batch SMS
            </DialogTitle>
            <DialogDescription>
              Select how many sellers to text. Messages will be sent to TCPA-safe leads only.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {/* Batch Size Selector */}
            <div className="space-y-2">
              <Label>Batch Size</Label>
              <Select value={batchSize} onValueChange={setBatchSize}>
                <SelectTrigger>
                  <SelectValue placeholder="Select batch size" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">10 messages</SelectItem>
                  <SelectItem value="25">25 messages</SelectItem>
                  <SelectItem value="50">50 messages</SelectItem>
                  <SelectItem value="100">100 messages</SelectItem>
                  <SelectItem value="all">All available ({tcpaSafe - contacted})</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Preview */}
            <div className="p-4 rounded-lg bg-muted">
              <div className="flex justify-between text-sm">
                <span>Available to text:</span>
                <span className="font-medium">{Math.max(0, tcpaSafe - contacted)}</span>
              </div>
              <div className="flex justify-between text-sm mt-1">
                <span>Will send:</span>
                <span className="font-medium">
                  {batchSize === 'all' 
                    ? Math.max(0, tcpaSafe - contacted)
                    : Math.min(parseInt(batchSize), Math.max(0, tcpaSafe - contacted))
                  }
                </span>
              </div>
            </div>

            {/* Warning */}
            <div className="flex items-start gap-2 p-3 rounded-lg bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800">
              <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm">
                <p className="font-medium text-yellow-800 dark:text-yellow-200">TCPA Compliance</p>
                <p className="text-yellow-700 dark:text-yellow-300">
                  Only leads with valid mobile numbers and proper consent will receive messages.
                </p>
              </div>
            </div>

            {/* Confirmation Checkbox */}
            <div className="flex items-center space-x-2">
              <Checkbox 
                id="confirm" 
                checked={batchConfirmed}
                onCheckedChange={(checked) => setBatchConfirmed(checked === true)}
              />
              <Label htmlFor="confirm" className="text-sm">
                I understand this will send real SMS messages to sellers
              </Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setBatchModalOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleBatchSend}
              disabled={!batchConfirmed || (tcpaSafe - contacted) <= 0}
            >
              <Send className="h-4 w-4 mr-2" />
              Send Batch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default Dashboard;
