import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layers, ArrowRight, Users, DollarSign, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { getBuyerPipeline } from '@/api/buyers';
import type { BuyerDealStage, BuyerPipelineResponse } from '@/lib/types';

const STAGES: BuyerDealStage[] = [
  'NEW',
  'DEAL_SENT',
  'VIEWED',
  'INTERESTED',
  'NEGOTIATING',
  'OFFERED',
  'CLOSED',
  'PASSED',
];

const STAGE_COLORS: Record<BuyerDealStage, string> = {
  NEW: 'bg-gray-500',
  DEAL_SENT: 'bg-blue-500',
  VIEWED: 'bg-cyan-500',
  INTERESTED: 'bg-green-500',
  NEGOTIATING: 'bg-yellow-500',
  OFFERED: 'bg-orange-500',
  CLOSED: 'bg-purple-500',
  PASSED: 'bg-red-500',
};

const STAGE_LABELS: Record<BuyerDealStage, string> = {
  NEW: 'New',
  DEAL_SENT: 'Deal Sent',
  VIEWED: 'Viewed',
  INTERESTED: 'Interested',
  NEGOTIATING: 'Negotiating',
  OFFERED: 'Offered',
  CLOSED: 'Closed',
  PASSED: 'Passed',
};

export function BuyerPipeline() {
  const navigate = useNavigate();
  
  const [data, setData] = useState<BuyerPipelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState<string>('all');

  useEffect(() => {
    fetchPipeline();
  }, [stageFilter]);

  async function fetchPipeline() {
    setLoading(true);
    try {
      const result = await getBuyerPipeline(
        stageFilter !== 'all' ? (stageFilter as BuyerDealStage) : undefined
      );
      setData(result);
    } catch (error) {
      console.error('Failed to fetch pipeline:', error);
    } finally {
      setLoading(false);
    }
  }

  // Calculate pipeline stats
  const totalDeals = data?.total_deals || 0;
  const activeDeals = data
    ? (data.stage_counts.INTERESTED || 0) +
      (data.stage_counts.NEGOTIATING || 0) +
      (data.stage_counts.OFFERED || 0)
    : 0;
  const closedDeals = data?.stage_counts.CLOSED || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold">Buyer Pipeline</h2>
        <p className="text-muted-foreground">Track deals through the disposition process</p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Deals</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalDeals}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Deals</CardTitle>
            <Users className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{activeDeals}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Closed Deals</CardTitle>
            <CheckCircle className="h-4 w-4 text-purple-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-purple-600">{closedDeals}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Close Rate</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {totalDeals > 0 ? ((closedDeals / totalDeals) * 100).toFixed(1) : 0}%
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Pipeline Visual */}
      <Card>
        <CardHeader>
          <CardTitle>Pipeline Stages</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 overflow-x-auto pb-4">
            {STAGES.map((stage, index) => {
              const count = data?.stage_counts[stage] || 0;
              return (
                <div key={stage} className="flex items-center">
                  <div
                    className={`px-4 py-3 rounded-lg min-w-[120px] text-center cursor-pointer transition-all hover:scale-105 ${
                      stageFilter === stage ? 'ring-2 ring-primary' : ''
                    }`}
                    style={{
                      backgroundColor: `hsl(var(--${STAGE_COLORS[stage].replace('bg-', '')}))`,
                    }}
                    onClick={() => setStageFilter(stage === stageFilter ? 'all' : stage)}
                  >
                    <Badge className={`${STAGE_COLORS[stage]} mb-1`}>{STAGE_LABELS[stage]}</Badge>
                    <div className="text-2xl font-bold text-white">{count}</div>
                  </div>
                  {index < STAGES.length - 1 && (
                    <ArrowRight className="h-5 w-5 mx-2 text-muted-foreground flex-shrink-0" />
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Deals Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Deals</CardTitle>
          <Select value={stageFilter} onValueChange={setStageFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by stage" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Stages</SelectItem>
              {STAGES.map((stage) => (
                <SelectItem key={stage} value={stage}>
                  {STAGE_LABELS[stage]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
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
                  <TableHead>Buyer</TableHead>
                  <TableHead>Lead</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead>Match Score</TableHead>
                  <TableHead>Offer</TableHead>
                  <TableHead>Assignment Fee</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.deals.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      No deals found
                    </TableCell>
                  </TableRow>
                ) : (
                  data?.deals.map((deal) => (
                    <TableRow
                      key={deal.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/leads/${deal.lead_id}`)}
                    >
                      <TableCell>
                        <span
                          className="font-medium hover:underline"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/buyers/${deal.buyer_id}`);
                          }}
                        >
                          {deal.buyer_name || `Buyer #${deal.buyer_id}`}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono">#{deal.lead_id}</TableCell>
                      <TableCell>
                        <Badge className={STAGE_COLORS[deal.stage as BuyerDealStage]}>
                          {STAGE_LABELS[deal.stage as BuyerDealStage] || deal.stage}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {deal.match_score ? `${deal.match_score.toFixed(0)}%` : '-'}
                      </TableCell>
                      <TableCell>
                        {deal.offer_amount ? `$${deal.offer_amount.toLocaleString()}` : '-'}
                      </TableCell>
                      <TableCell>
                        {deal.assignment_fee ? `$${deal.assignment_fee.toLocaleString()}` : '-'}
                      </TableCell>
                      <TableCell>
                        {deal.created_at
                          ? new Date(deal.created_at).toLocaleDateString()
                          : '-'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default BuyerPipeline;
