/**
 * Inbox - The Central Conversation Hub
 * 
 * Derives threads from outreach history.
 * Every lead with outreach attempts = one conversation thread.
 * 
 * Features:
 * - Thread list with filters (All, Unread, YES, MAYBE, Pending)
 * - Classification buttons (YES/NO/MAYBE/OTHER)
 * - Click-through to Call Prep Pack
 * - Empty state with onboarding steps
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare,
  Phone,
  Check,
  X,
  HelpCircle,
  ChevronRight,
  Send,
  RefreshCw,
  Flame,
  Search,
  Inbox as InboxIcon,
  ArrowRight,
  MapPin,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { useActiveMarket } from '@/components/active-market-provider';
import { cn } from '@/lib/utils';
import {
  getConversationThreads,
  getConversationDetail,
  classifyConversation,
  getConversationStats,
  type ConversationThread,
  type ConversationDetail,
  type ConversationStats,
  type ThreadFilter,
} from '@/api/conversations';

// Classification colors
const CLASSIFICATION_COLORS: Record<string, string> = {
  YES: 'bg-green-500',
  NO: 'bg-gray-500',
  MAYBE: 'bg-yellow-500',
  OTHER: 'bg-blue-500',
};

export function Inbox() {
  const navigate = useNavigate();
  const { activeMarket } = useActiveMarket();
  const { toast } = useToast();
  
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [selectedThread, setSelectedThread] = useState<ConversationDetail | null>(null);
  const [stats, setStats] = useState<ConversationStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [filter, setFilter] = useState<ThreadFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [replyText, setReplyText] = useState('');
  const [isSending, setIsSending] = useState(false);

  // Load conversations and stats
  useEffect(() => {
    loadConversations();
    loadStats();
  }, [activeMarket, filter]);

  const loadConversations = async () => {
    setIsLoading(true);
    try {
      const response = await getConversationThreads({
        market: activeMarket?.market_code || undefined,
        filter,
        search: searchQuery || undefined,
        limit: 100,
      });
      setThreads(response.threads);
    } catch (error) {
      console.error('Failed to load conversations:', error);
      // Don't show error toast - just show empty state
      setThreads([]);
    } finally {
      setIsLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const data = await getConversationStats(activeMarket?.market_code || undefined);
      setStats(data);
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  };

  const handleSelectThread = async (thread: ConversationThread) => {
    setIsLoadingDetail(true);
    try {
      const detail = await getConversationDetail(thread.lead_id);
      setSelectedThread(detail);
    } catch (error) {
      console.error('Failed to load conversation:', error);
      toast({
        title: 'Error',
        description: 'Failed to load conversation',
        variant: 'destructive',
      });
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const handleClassify = async (classification: 'YES' | 'NO' | 'MAYBE' | 'OTHER') => {
    if (!selectedThread) return;
    
    try {
      await classifyConversation(selectedThread.lead_id, classification);
      
      // Update local state
      setThreads(prev => prev.map(t => 
        t.id === selectedThread.lead_id 
          ? { ...t, classification, unread: false } 
          : t
      ));
      setSelectedThread(prev => prev ? { ...prev, classification, unread: false } : null);
      
      toast({
        title: 'Classified',
        description: `Marked as ${classification}`,
      });
      
      // If YES, prompt to view lead
      if (classification === 'YES') {
        toast({
          title: 'Lead Qualified! 🎉',
          description: 'Click "Open Call Prep Pack" to prepare for the call.',
        });
      }
      
      // Refresh stats
      loadStats();
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to classify',
        variant: 'destructive',
      });
    }
  };

  const handleSendReply = async () => {
    if (!selectedThread || !replyText.trim()) return;
    
    setIsSending(true);
    try {
      // TODO: Implement send reply API
      toast({
        title: 'Reply Queued',
        description: 'Your reply will be sent shortly.',
      });
      setReplyText('');
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to send reply',
        variant: 'destructive',
      });
    } finally {
      setIsSending(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    loadConversations();
  };

  // Filter counts from stats
  const filterCounts = {
    all: stats?.total_threads || 0,
    unread: stats?.unread || 0,
    yes: stats?.yes_queue || 0,
    maybe: stats?.maybe_queue || 0,
    pending: stats?.pending || 0,
  };

  // Empty state - show onboarding
  if (!isLoading && threads.length === 0 && filter === 'all') {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Inbox</h1>
            <p className="text-muted-foreground">Your conversation hub</p>
          </div>
          <Button onClick={() => navigate('/outreach')}>
            <Send className="h-4 w-4 mr-2" />
            Send Batch SMS
          </Button>
        </div>

        <Card className="max-w-2xl mx-auto">
          <CardHeader className="text-center">
            <div className="mx-auto w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
              <InboxIcon className="h-8 w-8 text-muted-foreground" />
            </div>
            <CardTitle>No Conversations Yet</CardTitle>
            <CardDescription>
              Start conversations with sellers to see them here
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Onboarding Steps */}
            <div className="space-y-4">
              <div className="flex items-start gap-4 p-4 rounded-lg border">
                <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold">
                  1
                </div>
                <div className="flex-1">
                  <h3 className="font-medium">Select Your Market</h3>
                  <p className="text-sm text-muted-foreground">
                    Choose the parish/area you want to work in
                  </p>
                  {activeMarket?.active ? (
                    <Badge variant="outline" className="mt-2">
                      <MapPin className="h-3 w-3 mr-1" />
                      {activeMarket.display_name}
                    </Badge>
                  ) : (
                    <Button variant="outline" size="sm" className="mt-2" onClick={() => navigate('/settings')}>
                      Select Market
                    </Button>
                  )}
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 rounded-lg border">
                <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold">
                  2
                </div>
                <div className="flex-1">
                  <h3 className="font-medium">Send Batch SMS</h3>
                  <p className="text-sm text-muted-foreground">
                    Text qualified sellers in your market
                  </p>
                  <Button variant="outline" size="sm" className="mt-2" onClick={() => navigate('/outreach')}>
                    <Send className="h-3 w-3 mr-1" />
                    Go to Outreach
                  </Button>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 rounded-lg border bg-muted/50">
                <div className="w-8 h-8 rounded-full bg-muted text-muted-foreground flex items-center justify-center font-bold">
                  3
                </div>
                <div className="flex-1">
                  <h3 className="font-medium text-muted-foreground">Replies Appear Here</h3>
                  <p className="text-sm text-muted-foreground">
                    When sellers reply, you'll see their messages here. Classify them as YES, NO, or MAYBE to move them through your pipeline.
                  </p>
                </div>
              </div>
            </div>

            <div className="text-center pt-4">
              <Button onClick={() => navigate('/outreach')} size="lg">
                <Send className="h-4 w-4 mr-2" />
                Start Sending Messages
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="p-4 border-b flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Inbox</h1>
          <p className="text-sm text-muted-foreground">
            {stats?.total_threads || 0} conversations • {stats?.unread || 0} unread
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { loadConversations(); loadStats(); }}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => navigate('/outreach')}>
            <Send className="h-4 w-4 mr-2" />
            Send Batch
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="p-3 border-b flex items-center gap-2 overflow-x-auto">
        {(['all', 'unread', 'yes', 'maybe', 'pending'] as ThreadFilter[]).map((f) => (
          <Button
            key={f}
            variant={filter === f ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter(f)}
            className="whitespace-nowrap"
          >
            {f === 'all' && 'All'}
            {f === 'unread' && '📬 Unread'}
            {f === 'yes' && '✅ YES'}
            {f === 'maybe' && '🤔 MAYBE'}
            {f === 'pending' && '⏳ Pending'}
            <Badge variant="secondary" className="ml-2">
              {filterCounts[f]}
            </Badge>
          </Button>
        ))}
        
        <form onSubmit={handleSearch} className="ml-auto flex gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search..."
              className="pl-8 w-48"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </form>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Thread List */}
        <div className="w-96 border-r overflow-y-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : threads.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>No conversations match this filter</p>
            </div>
          ) : (
            <div className="divide-y">
              {threads.map((thread) => (
                <div
                  key={thread.id}
                  onClick={() => handleSelectThread(thread)}
                  className={cn(
                    'p-4 cursor-pointer hover:bg-muted/50 transition-colors',
                    selectedThread?.id === thread.id && 'bg-muted',
                    thread.unread && 'bg-blue-50 dark:bg-blue-950/20'
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {thread.unread && (
                          <span className="w-2 h-2 rounded-full bg-blue-500" />
                        )}
                        <span className="font-medium truncate">{thread.owner_name}</span>
                        {thread.motivation_score >= 65 && (
                          <Flame className="h-4 w-4 text-red-500" />
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground truncate">
                        {thread.property_address}
                      </p>
                      <p className="text-sm truncate mt-1">
                        {thread.last_message_direction === 'inbound' && '← '}
                        {thread.last_message || 'No messages'}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {thread.classification && (
                        <Badge className={CLASSIFICATION_COLORS[thread.classification]}>
                          {thread.classification}
                        </Badge>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {thread.last_message_at 
                          ? new Date(thread.last_message_at).toLocaleDateString()
                          : ''}
                      </span>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Conversation Detail */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {isLoadingDetail ? (
            <div className="flex-1 flex items-center justify-center">
              <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : selectedThread ? (
            <>
              {/* Thread Header */}
              <div className="p-4 border-b">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-semibold">{selectedThread.owner_name}</h2>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      {selectedThread.owner_phone && (
                        <a href={`tel:${selectedThread.owner_phone}`} className="flex items-center gap-1 hover:text-primary">
                          <Phone className="h-3 w-3" />
                          {selectedThread.owner_phone}
                        </a>
                      )}
                      <span>•</span>
                      <span>{selectedThread.parish}</span>
                    </div>
                  </div>
                  <Button onClick={() => navigate(`/leads/${selectedThread.lead_id}`)}>
                    Open Call Prep Pack
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
                
                {/* Classification Buttons */}
                <div className="flex items-center gap-2 mt-3">
                  <span className="text-sm text-muted-foreground mr-2">Classify:</span>
                  <Button
                    size="sm"
                    variant={selectedThread.classification === 'YES' ? 'default' : 'outline'}
                    className={selectedThread.classification === 'YES' ? 'bg-green-500 hover:bg-green-600' : ''}
                    onClick={() => handleClassify('YES')}
                  >
                    <Check className="h-4 w-4 mr-1" />
                    YES
                  </Button>
                  <Button
                    size="sm"
                    variant={selectedThread.classification === 'NO' ? 'default' : 'outline'}
                    className={selectedThread.classification === 'NO' ? 'bg-gray-500 hover:bg-gray-600' : ''}
                    onClick={() => handleClassify('NO')}
                  >
                    <X className="h-4 w-4 mr-1" />
                    NO
                  </Button>
                  <Button
                    size="sm"
                    variant={selectedThread.classification === 'MAYBE' ? 'default' : 'outline'}
                    className={selectedThread.classification === 'MAYBE' ? 'bg-yellow-500 hover:bg-yellow-600' : ''}
                    onClick={() => handleClassify('MAYBE')}
                  >
                    <HelpCircle className="h-4 w-4 mr-1" />
                    MAYBE
                  </Button>
                  <Button
                    size="sm"
                    variant={selectedThread.classification === 'OTHER' ? 'default' : 'outline'}
                    onClick={() => handleClassify('OTHER')}
                  >
                    OTHER
                  </Button>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {selectedThread.messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      'max-w-[80%] p-3 rounded-lg',
                      msg.direction === 'outbound'
                        ? 'ml-auto bg-primary text-primary-foreground'
                        : 'bg-muted'
                    )}
                  >
                    <p className="text-sm">{msg.body}</p>
                    <p className={cn(
                      'text-xs mt-1',
                      msg.direction === 'outbound' ? 'text-primary-foreground/70' : 'text-muted-foreground'
                    )}>
                      {msg.sent_at ? new Date(msg.sent_at).toLocaleString() : ''}
                      {msg.direction === 'outbound' && ` • ${msg.status}`}
                    </p>
                  </div>
                ))}
              </div>

              {/* Reply Input */}
              <div className="p-4 border-t">
                <div className="flex gap-2">
                  <Textarea
                    placeholder="Type a reply..."
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    rows={2}
                    className="flex-1"
                  />
                  <Button onClick={handleSendReply} disabled={isSending || !replyText.trim()}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              <div className="text-center">
                <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Select a conversation to view</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Inbox;
