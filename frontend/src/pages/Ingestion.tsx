import { useState, useEffect } from 'react';
import {
  Upload,
  Database,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  FileSpreadsheet,
  Scale,
  RefreshCw,
  Gavel,
  FileWarning,
  Users,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { useMarket } from '@/components/market-provider';
import { 
  getIngestionSummary, 
  ingestUniversal, 
  ingestAuctions, 
  ingestExpiredListings, 
  ingestTaxDelinquent, 
  ingestAbsenteeOwners 
} from '@/api/ingestion';
import { startScoringJob, getJobStatus } from '@/api/leads';
import { runNightlyPipeline, runFollowups } from '@/api/automation';
import { getMarketConfig } from '@/api/markets';
import type { IngestionSummary, MarketConfig } from '@/lib/types';
import { Progress } from '@/components/ui/progress';

type JobStatusType = 'idle' | 'running' | 'success' | 'error';

interface JobState {
  status: JobStatusType;
  message?: string;
  lastRun?: string;
  progress?: number;
  jobId?: string;
}

export function Ingestion() {
  const { market } = useMarket();
  const { toast } = useToast();

  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<IngestionSummary | null>(null);
  const [marketConfig, setMarketConfig] = useState<MarketConfig | null>(null);

  // Job states
  const [pipelineState, setPipelineState] = useState<JobState>({ status: 'idle' });
  const [scoringState, setScoringState] = useState<JobState>({ status: 'idle' });
  const [followupState, setFollowupState] = useState<JobState>({ status: 'idle' });

  // Options
  const [dryRun, setDryRun] = useState(false);

  // Multi-source ingestion states
  const [universalFilePath, setUniversalFilePath] = useState('');
  const [universalParish, setUniversalParish] = useState('');
  const [ingestionStates, setIngestionStates] = useState<Record<string, JobState>>({
    universal: { status: 'idle' },
    auctions: { status: 'idle' },
    expired: { status: 'idle' },
    taxDelinquent: { status: 'idle' },
    absentee: { status: 'idle' },
  });

  useEffect(() => {
    fetchData();
  }, [market]);

  async function fetchData() {
    setLoading(true);
    try {
      const [summaryData, marketData] = await Promise.all([
        getIngestionSummary().catch(() => null),
        getMarketConfig(market).catch(() => null),
      ]);
      setSummary(summaryData as IngestionSummary | null);
      setMarketConfig(marketData);
    } catch (error) {
      console.error('Failed to fetch ingestion data:', error);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunPipeline() {
    setPipelineState({ status: 'running' });
    try {
      const result = await runNightlyPipeline([market], dryRun);
      const marketResult = result.steps[market];

      if (marketResult?.error) {
        setPipelineState({
          status: 'error',
          message: marketResult.error,
          lastRun: new Date().toISOString(),
        });
        toast({
          title: 'Pipeline Error',
          description: marketResult.error,
          variant: 'destructive',
        });
      } else {
        setPipelineState({
          status: 'success',
          message: dryRun ? 'Dry run completed' : 'Pipeline completed successfully',
          lastRun: new Date().toISOString(),
        });
        toast({
          title: dryRun ? 'Dry Run Complete' : 'Pipeline Complete',
          description: `Processed market: ${market}`,
        });
        fetchData();
      }
    } catch (error) {
      setPipelineState({
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error',
        lastRun: new Date().toISOString(),
      });
      toast({
        title: 'Pipeline Failed',
        description: 'Failed to run pipeline',
        variant: 'destructive',
      });
    }
  }

  async function handleRunScoring() {
    setScoringState({ status: 'running', progress: 0 });
    try {
      // Start background scoring job
      const jobResponse = await startScoringJob(market, 1000);
      const jobId = jobResponse.job_id;
      
      setScoringState({ status: 'running', progress: 0, jobId, message: 'Starting...' });
      
      // Poll for status
      const pollInterval = setInterval(async () => {
        try {
          const status = await getJobStatus(jobId);
          
          if (status.status === 'completed') {
            clearInterval(pollInterval);
            const result = status.result as { updated?: number; average_score?: number; high_priority_count?: number };
            setScoringState({
              status: 'success',
              progress: 100,
              message: `Scored ${result.updated || 0} leads, avg: ${result.average_score || 0}`,
              lastRun: new Date().toISOString(),
            });
            toast({
              title: 'Scoring Complete',
              description: `${result.updated || 0} leads scored. ${result.high_priority_count || 0} high priority.`,
            });
            fetchData();
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            setScoringState({
              status: 'error',
              message: status.error || 'Scoring failed',
              lastRun: new Date().toISOString(),
            });
            toast({
              title: 'Scoring Failed',
              description: status.error || 'Unknown error',
              variant: 'destructive',
            });
          } else {
            // Still running - update progress
            setScoringState({
              status: 'running',
              progress: status.progress_percent,
              message: `Processing... ${status.processed}/${status.total} leads`,
              jobId,
            });
          }
        } catch (pollError) {
          console.error('Failed to poll job status:', pollError);
        }
      }, 2000); // Poll every 2 seconds
      
      // Safety timeout after 30 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        if (scoringState.status === 'running') {
          setScoringState({
            status: 'error',
            message: 'Job timed out',
            lastRun: new Date().toISOString(),
          });
        }
      }, 30 * 60 * 1000);
      
    } catch (error) {
      setScoringState({
        status: 'error',
        message: error instanceof Error ? error.message : 'Failed to start scoring',
        lastRun: new Date().toISOString(),
      });
      toast({
        title: 'Scoring Failed',
        description: 'Failed to start scoring job',
        variant: 'destructive',
      });
    }
  }

  async function handleRunFollowups() {
    setFollowupState({ status: 'running' });
    try {
      const result = await runFollowups({ market, dry_run: dryRun, limit: 50 });
      setFollowupState({
        status: 'success',
        message: `Due: ${result.total_due}, Sent: ${result.sent}, Skipped: ${result.skipped}`,
        lastRun: new Date().toISOString(),
      });
      toast({
        title: dryRun ? 'Followup Preview' : 'Followups Sent',
        description: `${result.sent} messages sent`,
      });
    } catch (error) {
      setFollowupState({
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error',
        lastRun: new Date().toISOString(),
      });
      toast({
        title: 'Followups Failed',
        description: 'Failed to process followups',
        variant: 'destructive',
      });
    }
  }

  // Multi-source ingestion handlers
  async function handleUniversalIngest() {
    if (!universalFilePath) {
      toast({
        title: 'File Path Required',
        description: 'Please enter a file path',
        variant: 'destructive',
      });
      return;
    }

    setIngestionStates(prev => ({ ...prev, universal: { status: 'running' } }));
    try {
      await ingestUniversal({
        file_path: universalFilePath,
        parish_override: universalParish || undefined,
        dry_run: dryRun,
      });
      setIngestionStates(prev => ({
        ...prev,
        universal: { status: 'success', message: 'Ingestion started', lastRun: new Date().toISOString() },
      }));
      toast({
        title: 'Ingestion Started',
        description: 'Universal ingestion is running in the background',
      });
      fetchData();
    } catch (error) {
      setIngestionStates(prev => ({
        ...prev,
        universal: { status: 'error', message: error instanceof Error ? error.message : 'Failed', lastRun: new Date().toISOString() },
      }));
      toast({
        title: 'Ingestion Failed',
        description: 'Failed to start ingestion',
        variant: 'destructive',
      });
    }
  }

  async function handleSourceIngest(source: 'auctions' | 'expired' | 'taxDelinquent' | 'absentee', filePath: string) {
    if (!filePath) {
      toast({
        title: 'File Path Required',
        description: 'Please enter a file path',
        variant: 'destructive',
      });
      return;
    }

    setIngestionStates(prev => ({ ...prev, [source]: { status: 'running' } }));
    try {
      const ingestFn = {
        auctions: ingestAuctions,
        expired: ingestExpiredListings,
        taxDelinquent: ingestTaxDelinquent,
        absentee: ingestAbsenteeOwners,
      }[source];

      await ingestFn(filePath);
      setIngestionStates(prev => ({
        ...prev,
        [source]: { status: 'success', message: 'Ingestion started', lastRun: new Date().toISOString() },
      }));
      toast({
        title: 'Ingestion Started',
        description: `${source} ingestion is running in the background`,
      });
      fetchData();
    } catch (error) {
      setIngestionStates(prev => ({
        ...prev,
        [source]: { status: 'error', message: error instanceof Error ? error.message : 'Failed', lastRun: new Date().toISOString() },
      }));
      toast({
        title: 'Ingestion Failed',
        description: `Failed to start ${source} ingestion`,
        variant: 'destructive',
      });
    }
  }

  const StatusIcon = ({ status }: { status: JobStatusType }) => {
    switch (status) {
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
      case 'success':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'error':
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Ingestion & Pipeline</h2>
          <p className="text-muted-foreground">
            Data ingestion and automation for {market}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Switch id="dry-run" checked={dryRun} onCheckedChange={setDryRun} />
            <Label htmlFor="dry-run">Dry Run</Label>
          </div>
          <Button onClick={fetchData} variant="outline" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4" />
              Tax Roll Records
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <>
                <div className="text-2xl font-bold">{summary?.tax_roll?.total ?? 0}</div>
                <p className="text-xs text-muted-foreground">
                  {summary?.tax_roll?.new ?? 0} new, {summary?.tax_roll?.updated ?? 0} updated
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Scale className="h-4 w-4" />
              Adjudicated Properties
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <>
                <div className="text-2xl font-bold">{summary?.adjudicated?.total ?? 0}</div>
                <p className="text-xs text-muted-foreground">
                  {summary?.adjudicated?.new ?? 0} new
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Database className="h-4 w-4" />
              Leads Created
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <>
                <div className="text-2xl font-bold">{summary?.leads_created ?? 0}</div>
                <p className="text-xs text-muted-foreground">
                  {summary?.owners_created ?? 0} owners, {summary?.parties_created ?? 0} parties
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Market Configuration */}
      {marketConfig && (
        <Card>
          <CardHeader>
            <CardTitle>Market Configuration: {market}</CardTitle>
            <CardDescription>Current settings for {marketConfig.name}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-4">
              <div>
                <p className="text-sm text-muted-foreground">Min Score</p>
                <p className="font-medium">{marketConfig.min_motivation_score}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Hot Threshold</p>
                <p className="font-medium">{marketConfig.hot_score_threshold}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Followup Schedule</p>
                <p className="font-medium">
                  Day {marketConfig.followup_schedule.day_1}, Day {marketConfig.followup_schedule.day_2}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Outreach Window</p>
                <p className="font-medium">
                  {marketConfig.outreach_window.start_hour}:00 - {marketConfig.outreach_window.end_hour}:00
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Pipeline Jobs */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Play className="h-5 w-5" />
            Pipeline Jobs
          </CardTitle>
          <CardDescription>
            Run automation tasks for {market}. {dryRun && <Badge>Dry Run Mode</Badge>}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Full Pipeline */}
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div className="flex items-center gap-4">
              <StatusIcon status={pipelineState.status} />
              <div>
                <p className="font-medium">Run Nightly Pipeline</p>
                <p className="text-sm text-muted-foreground">
                  Ingest → Enrich → Score → Outreach → Followups → Alerts
                </p>
                {pipelineState.message && (
                  <p className="text-xs text-muted-foreground mt-1">{pipelineState.message}</p>
                )}
              </div>
            </div>
            <Button
              onClick={handleRunPipeline}
              disabled={pipelineState.status === 'running'}
            >
              {pipelineState.status === 'running' ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Run Pipeline
                </>
              )}
            </Button>
          </div>

          <Separator />

          {/* Individual Jobs */}
          <div className="space-y-3">
            <p className="text-sm font-medium text-muted-foreground">Individual Jobs</p>

            {/* Scoring */}
            <div className="p-4 border rounded-lg space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <StatusIcon status={scoringState.status} />
                  <div>
                    <p className="font-medium">Score Leads</p>
                    <p className="text-sm text-muted-foreground">
                      Recalculate motivation scores for all leads
                    </p>
                    {scoringState.message && (
                      <p className="text-xs text-muted-foreground mt-1">{scoringState.message}</p>
                    )}
                  </div>
                </div>
                <Button
                  variant="outline"
                  onClick={handleRunScoring}
                  disabled={scoringState.status === 'running'}
                >
                  {scoringState.status === 'running' ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    'Run'
                  )}
                </Button>
              </div>
              {scoringState.status === 'running' && scoringState.progress !== undefined && (
                <div className="space-y-1">
                  <Progress value={scoringState.progress} className="h-2" />
                  <p className="text-xs text-muted-foreground text-right">
                    {scoringState.progress.toFixed(1)}%
                  </p>
                </div>
              )}
            </div>

            {/* Followups */}
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div className="flex items-center gap-4">
                <StatusIcon status={followupState.status} />
                <div>
                  <p className="font-medium">Process Followups</p>
                  <p className="text-sm text-muted-foreground">
                    Send scheduled follow-up messages
                  </p>
                  {followupState.message && (
                    <p className="text-xs text-muted-foreground mt-1">{followupState.message}</p>
                  )}
                </div>
              </div>
              <Button
                variant="outline"
                onClick={handleRunFollowups}
                disabled={followupState.status === 'running'}
              >
                {followupState.status === 'running' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  'Run'
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Multi-Source Ingestion */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Multi-Source Ingestion
          </CardTitle>
          <CardDescription>
            Import data from various sources. Supports CSV, XLSX, and ZIP files.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Universal Parish Ingestion */}
          <div className="p-4 border rounded-lg space-y-4">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-blue-500" />
              <div>
                <p className="font-medium">Universal Parish Tax Roll</p>
                <p className="text-sm text-muted-foreground">
                  Auto-detects columns for any Louisiana parish
                </p>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="md:col-span-2">
                <Label htmlFor="universal-path">File Path</Label>
                <Input
                  id="universal-path"
                  placeholder="C:\path\to\taxroll.csv"
                  value={universalFilePath}
                  onChange={(e) => setUniversalFilePath(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="parish-override">Parish (optional)</Label>
                <Input
                  id="parish-override"
                  placeholder="Auto-detect"
                  value={universalParish}
                  onChange={(e) => setUniversalParish(e.target.value)}
                />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusIcon status={ingestionStates.universal.status} />
                {ingestionStates.universal.message && (
                  <span className="text-sm text-muted-foreground">
                    {ingestionStates.universal.message}
                  </span>
                )}
              </div>
              <Button
                onClick={handleUniversalIngest}
                disabled={ingestionStates.universal.status === 'running' || !universalFilePath}
              >
                {ingestionStates.universal.status === 'running' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  'Ingest'
                )}
              </Button>
            </div>
          </div>

          <Separator />

          {/* Other Sources */}
          <div className="grid gap-4 md:grid-cols-2">
            {/* Auctions */}
            <SourceIngestionCard
              icon={<Gavel className="h-5 w-5 text-amber-500" />}
              title="Public Auctions"
              description="Auction property listings"
              status={ingestionStates.auctions}
              onIngest={(path) => handleSourceIngest('auctions', path)}
            />

            {/* Expired Listings */}
            <SourceIngestionCard
              icon={<FileWarning className="h-5 w-5 text-orange-500" />}
              title="Expired Listings"
              description="Expired MLS listings"
              status={ingestionStates.expired}
              onIngest={(path) => handleSourceIngest('expired', path)}
            />

            {/* Tax Delinquent */}
            <SourceIngestionCard
              icon={<Scale className="h-5 w-5 text-red-500" />}
              title="Tax Delinquent"
              description="Tax delinquent property lists"
              status={ingestionStates.taxDelinquent}
              onIngest={(path) => handleSourceIngest('taxDelinquent', path)}
            />

            {/* Absentee Owners */}
            <SourceIngestionCard
              icon={<Users className="h-5 w-5 text-purple-500" />}
              title="Absentee Owners"
              description="Absentee owner lists"
              status={ingestionStates.absentee}
              onIngest={(path) => handleSourceIngest('absentee', path)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Last Run Info */}
      {summary?.timestamp && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              Last ingestion: {new Date(summary.timestamp).toLocaleString()}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// Helper component for source ingestion cards
function SourceIngestionCard({
  icon,
  title,
  description,
  status,
  onIngest,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  status: JobState;
  onIngest: (path: string) => void;
}) {
  const [filePath, setFilePath] = useState('');

  return (
    <div className="p-4 border rounded-lg space-y-3">
      <div className="flex items-center gap-2">
        {icon}
        <div>
          <p className="font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <Input
        placeholder="File path..."
        value={filePath}
        onChange={(e) => setFilePath(e.target.value)}
        className="text-sm"
      />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {status.status !== 'idle' && (
            <>
              {status.status === 'running' && <Loader2 className="h-3 w-3 animate-spin text-blue-500" />}
              {status.status === 'success' && <CheckCircle className="h-3 w-3 text-green-500" />}
              {status.status === 'error' && <XCircle className="h-3 w-3 text-red-500" />}
            </>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onIngest(filePath)}
          disabled={status.status === 'running' || !filePath}
        >
          {status.status === 'running' ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Ingest'}
        </Button>
      </div>
    </div>
  );
}

export default Ingestion;