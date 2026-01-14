import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Send,
  Filter,
  ChevronLeft,
  ChevronRight,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/components/ui/use-toast';
import { useMarket } from '@/components/market-provider';
import {
  getOutreachAttempts,
  getOutreachStatistics,
  triggerOutreachBatch,
  getFollowupsDue,
} from '@/api/outreach';
import { runFollowups } from '@/api/automation';
import type { OutreachAttempt, OutreachStats, FollowupDueResponse, ReplyClassification } from '@/lib/types';

const PAGE_SIZE = 25;

const STATUS_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  delivered: CheckCircle,
  sent: Clock,
  pending: Clock,
  failed: XCircle,
};

const STATUS_COLORS: Record<string, string> = {
  delivered: 'text-green-500',
  sent: 'text-blue-500',
  pending: 'text-yellow-500',
  failed: 'text-red-500',
};

const CLASSIFICATION_COLORS: Record<ReplyClassification, string> = {
  INTERESTED: 'bg-green-500',
  NOT_INTERESTED: 'bg-gray-500',
  SEND_OFFER: 'bg-purple-500',
  CONFUSED: 'bg-yellow-500',
  DEAD: 'bg-red-800',
};

export function Outreach() {
  const navigate = useNavigate();
  const { market } = useMarket();
  const { toast } = useToast();

  const [attempts, setAttempts] = useState<OutreachAttempt[]>([]);
  const [stats, setStats] = useState<OutreachStats | null>(null);
  const [followupsDue, setFollowupsDue] = useState<FollowupDueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Batch outreach dialog
  const [batchDialogOpen, setBatchDialogOpen] = useState(false);
  const [batchLimit, setBatchLimit] = useState(50);
  const [batchMinScore, setBatchMinScore] = useState(65);
  const [runningBatch, setRunningBatch] = useState(false);

  // Followup dialog
  const [followupDialogOpen, setFollowupDialogOpen] = useState(false);
  const [followupDryRun, setFollowupDryRun] = useState(true);
  const [runningFollowups, setRunningFollowups] = useState(false);

  useEffect(() => {
    fetchData();
  }, [market, page, statusFilter]);

  async function fetchData() {
    setLoading(true);
    try {
      const [attemptsData, statsData, followupsData] = await Promise.all([
        getOutreachAttempts({
          market,
          status: statusFilter === 'all' ? undefined : statusFilter,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        }),
        getOutreachStatistics(market, 7),
        getFollowupsDue(market, 50),
      ]);
      setAttempts(attemptsData);
      setStats(statsData);
      setFollowupsDue(followupsData);
      setHasMore(attemptsData.length === PAGE_SIZE);
    } catch (error) {
      console.error('Failed to fetch outreach data:', error);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunBatch() {
    setRunningBatch(true);
    try {
      const result = await triggerOutreachBatch(market, batchLimit, batchMinScore, true);
      toast({
        title: 'Batch Started',
        description: result.message,
      });
      setBatchDialogOpen(false);
      // Wait a bit then refresh
      setTimeout(fetchData, 2000);
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to start batch', variant: 'destructive' });
    } finally {
      setRunningBatch(false);
    }
  }

  async function handleRunFollowups() {
    setRunningFollowups(true);
    try {
      const result = await runFollowups({ market, dry_run: followupDryRun, limit: 50 });
      toast({
        title: followupDryRun ? 'Dry Run Complete' : 'Followups Sent',
        description: `Total due: ${result.total_due}, Sent: ${result.sent}, Skipped: ${result.skipped}`,
      });
      setFollowupDialogOpen(false);
      fetchData();
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to run followups', variant: 'destructive' });
    } finally {
      setRunningFollowups(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Outreach</h2>
          <p className="text-muted-foreground">Manage SMS outreach for {market}</p>
        </div>
        <div className="flex items-center gap-2">
          <Dialog open={followupDialogOpen} onOpenChange={setFollowupDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">
                <Clock className="mr-2 h-4 w-4" />
                Run Followups ({followupsDue?.total_due ?? 0})
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Run Follow-up Messages</DialogTitle>
                <DialogDescription>
                  Send scheduled follow-up messages to leads.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="flex items-center justify-between">
                  <Label htmlFor="dry-run">Dry Run (preview only)</Label>
                  <Switch
                    id="dry-run"
                    checked={followupDryRun}
                    onCheckedChange={setFollowupDryRun}
                  />
                </div>
                <p className="text-sm text-muted-foreground">
                  {followupsDue?.total_due ?? 0} leads are due for follow-up in {market}.
                </p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setFollowupDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleRunFollowups} disabled={runningFollowups}>
                  {runningFollowups ? 'Running...' : followupDryRun ? 'Preview' : 'Send Followups'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Dialog open={batchDialogOpen} onOpenChange={setBatchDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Send className="mr-2 h-4 w-4" />
                Run Batch
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Run Outreach Batch</DialogTitle>
                <DialogDescription>
                  Send intro messages to new high-priority leads.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="batch-limit">Max Leads</Label>
                  <Input
                    id="batch-limit"
                    type="number"
                    value={batchLimit}
                    onChange={(e) => setBatchLimit(parseInt(e.target.value))}
                    min={1}
                    max={500}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="batch-min-score">Min Score</Label>
                  <Input
                    id="batch-min-score"
                    type="number"
                    value={batchMinScore}
                    onChange={(e) => setBatchMinScore(parseInt(e.target.value))}
                    min={0}
                    max={100}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setBatchDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleRunBatch} disabled={runningBatch}>
                  {runningBatch ? 'Starting...' : 'Start Batch'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Sent</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{stats?.total_attempts ?? 0}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Delivered</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold text-green-500">{stats?.successful ?? 0}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Failed</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold text-red-500">{stats?.failed ?? 0}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Response Rate</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">
                {Math.round((stats?.response_rate ?? 0) * 100)}%
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select
              value={statusFilter}
              onValueChange={(v) => {
                setStatusFilter(v);
                setPage(0);
              }}
            >
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="delivered">Delivered</SelectItem>
                <SelectItem value="sent">Sent</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Attempts Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">Lead</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Type</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Classification</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Sent</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Message</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  [...Array(10)].map((_, i) => (
                    <tr key={i} className="border-b">
                      <td className="px-4 py-3"><Skeleton className="h-5 w-16" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-20" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-20" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-24" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-24" /></td>
                      <td className="px-4 py-3"><Skeleton className="h-5 w-40" /></td>
                    </tr>
                  ))
                ) : attempts.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      No outreach attempts found
                    </td>
                  </tr>
                ) : (
                  attempts.map((attempt) => {
                    const StatusIcon = STATUS_ICONS[attempt.status] || Clock;
                    return (
                      <tr
                        key={attempt.id}
                        className="border-b cursor-pointer hover:bg-muted/50 transition-colors"
                        onClick={() => navigate(`/leads/${attempt.lead_id}`)}
                      >
                        <td className="px-4 py-3">
                          <span className="font-mono text-sm">#{attempt.lead_id}</span>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline" className="capitalize">
                            {attempt.message_context || 'intro'}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <StatusIcon className={`h-4 w-4 ${STATUS_COLORS[attempt.status]}`} />
                            <span className="capitalize">{attempt.status}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {attempt.reply_classification ? (
                            <Badge className={CLASSIFICATION_COLORS[attempt.reply_classification]}>
                              {attempt.reply_classification}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {attempt.sent_at
                            ? new Date(attempt.sent_at).toLocaleString()
                            : attempt.created_at
                            ? new Date(attempt.created_at).toLocaleString()
                            : '—'}
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm truncate max-w-[200px] block">
                            {attempt.message_body?.slice(0, 50)}
                            {(attempt.message_body?.length ?? 0) > 50 ? '...' : ''}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Showing {page * PAGE_SIZE + 1} - {page * PAGE_SIZE + attempts.length}
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

export default Outreach;