import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Star,
  FileCheck,
  Phone,
  Mail,
  MapPin,
  Edit,
  Save,
  X,
  Upload,
  ExternalLink,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { getBuyer, updateBuyer, updateBuyerPOF, getBuyerDeals, deleteBuyer } from '@/api/buyers';
import type { Buyer, BuyerCreate, BuyerDeal, MarketCode, PropertyType } from '@/lib/types';

const MARKET_OPTIONS: MarketCode[] = ['LA', 'TX', 'MS', 'AR', 'AL'];
const PROPERTY_TYPE_OPTIONS: PropertyType[] = [
  'infill',
  'rural',
  'wooded',
  'lot',
  'agricultural',
  'recreational',
  'waterfront',
];

const BUYER_DEAL_STAGE_COLORS: Record<string, string> = {
  NEW: 'bg-gray-500',
  DEAL_SENT: 'bg-blue-500',
  VIEWED: 'bg-cyan-500',
  INTERESTED: 'bg-green-500',
  NEGOTIATING: 'bg-yellow-500',
  OFFERED: 'bg-orange-500',
  CLOSED: 'bg-purple-500',
  PASSED: 'bg-red-500',
};

export function BuyerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [buyer, setBuyer] = useState<Buyer | null>(null);
  const [deals, setDeals] = useState<BuyerDeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editData, setEditData] = useState<Partial<Buyer>>({});

  // POF dialog
  const [pofDialogOpen, setPofDialogOpen] = useState(false);
  const [pofUrl, setPofUrl] = useState('');
  const [pofVerified, setPofVerified] = useState(false);

  // Delete dialog
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (id) {
      fetchBuyer();
      fetchDeals();
    }
  }, [id]);

  async function fetchBuyer() {
    setLoading(true);
    try {
      const data = await getBuyer(parseInt(id!));
      setBuyer(data);
      setEditData(data);
    } catch (error) {
      console.error('Failed to fetch buyer:', error);
      toast({ title: 'Error', description: 'Failed to load buyer', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }

  async function fetchDeals() {
    try {
      const data = await getBuyerDeals(parseInt(id!));
      setDeals(data);
    } catch (error) {
      console.error('Failed to fetch deals:', error);
    }
  }

  async function handleSave() {
    if (!buyer) return;
    setSaving(true);
    try {
      // Convert null to undefined for all nullable fields to match BuyerCreate type
      const cleanedData: Partial<BuyerCreate> = {
        name: editData.name,
        phone: editData.phone ?? undefined,
        email: editData.email ?? undefined,
        market_codes: editData.market_codes,
        counties: editData.counties,
        min_acres: editData.min_acres ?? undefined,
        max_acres: editData.max_acres ?? undefined,
        property_types: editData.property_types,
        price_min: editData.price_min ?? undefined,
        price_max: editData.price_max ?? undefined,
        target_spread: editData.target_spread ?? undefined,
        closing_speed_days: editData.closing_speed_days ?? undefined,
        vip: editData.vip,
        notes: editData.notes ?? undefined,
        pof_url: editData.pof_url ?? undefined,
      };
      const updated = await updateBuyer(buyer.id, cleanedData);
      setBuyer(updated);
      setEditing(false);
      toast({ title: 'Success', description: 'Buyer updated' });
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to update buyer', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdatePOF() {
    if (!buyer || !pofUrl) return;
    try {
      const updated = await updateBuyerPOF(buyer.id, pofUrl, pofVerified);
      setBuyer(updated);
      setPofDialogOpen(false);
      toast({ title: 'Success', description: 'POF updated' });
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to update POF', variant: 'destructive' });
    }
  }

  async function handleDelete() {
    if (!buyer) return;
    setDeleting(true);
    try {
      await deleteBuyer(buyer.id);
      toast({ title: 'Success', description: 'Buyer deleted' });
      navigate('/buyers');
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to delete buyer', variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!buyer) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-muted-foreground">Buyer not found</p>
        <Button variant="link" onClick={() => navigate('/buyers')}>
          Back to Buyers
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/buyers')}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold">{buyer.name}</h2>
              {buyer.vip && <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />}
              {buyer.pof_verified && (
                <Badge className="bg-green-500">POF Verified</Badge>
              )}
            </div>
            <p className="text-muted-foreground">
              {buyer.deals_count} deals • Member since {new Date(buyer.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <Button variant="outline" onClick={() => setEditing(false)}>
                <X className="mr-2 h-4 w-4" />
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                <Save className="mr-2 h-4 w-4" />
                {saving ? 'Saving...' : 'Save'}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setEditing(true)}>
                <Edit className="mr-2 h-4 w-4" />
                Edit
              </Button>
              <Button
                variant="outline"
                className="text-destructive"
                onClick={() => setDeleteDialogOpen(true)}
              >
                Delete
              </Button>
            </>
          )}
        </div>
      </div>

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
          <TabsTrigger value="deals">Deals ({deals.length})</TabsTrigger>
          <TabsTrigger value="pof">POF</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Contact Information</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Name</Label>
                {editing ? (
                  <Input
                    value={editData.name || ''}
                    onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                  />
                ) : (
                  <p className="font-medium">{buyer.name}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label>Phone</Label>
                {editing ? (
                  <Input
                    value={editData.phone || ''}
                    onChange={(e) => setEditData({ ...editData, phone: e.target.value })}
                  />
                ) : (
                  <div className="flex items-center gap-2">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <p className="font-medium">{buyer.phone || 'Not set'}</p>
                  </div>
                )}
              </div>
              <div className="space-y-2">
                <Label>Email</Label>
                {editing ? (
                  <Input
                    value={editData.email || ''}
                    onChange={(e) => setEditData({ ...editData, email: e.target.value })}
                  />
                ) : (
                  <div className="flex items-center gap-2">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                    <p className="font-medium">{buyer.email || 'Not set'}</p>
                  </div>
                )}
              </div>
              <div className="space-y-2">
                <Label>VIP Status</Label>
                {editing ? (
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={editData.vip}
                      onCheckedChange={(c) => setEditData({ ...editData, vip: c as boolean })}
                    />
                    <span>VIP Buyer</span>
                  </div>
                ) : (
                  <p className="font-medium">{buyer.vip ? 'Yes' : 'No'}</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Notes</CardTitle>
            </CardHeader>
            <CardContent>
              {editing ? (
                <Textarea
                  value={editData.notes || ''}
                  onChange={(e) => setEditData({ ...editData, notes: e.target.value })}
                  rows={4}
                />
              ) : (
                <p className="text-muted-foreground">{buyer.notes || 'No notes'}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preferences" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Target Markets</CardTitle>
            </CardHeader>
            <CardContent>
              {editing ? (
                <div className="flex flex-wrap gap-3">
                  {MARKET_OPTIONS.map((m) => (
                    <label key={m} className="flex items-center gap-2">
                      <Checkbox
                        checked={editData.market_codes?.includes(m)}
                        onCheckedChange={(checked) => {
                          const codes = editData.market_codes || [];
                          setEditData({
                            ...editData,
                            market_codes: checked
                              ? [...codes, m]
                              : codes.filter((c) => c !== m),
                          });
                        }}
                      />
                      <span>{m}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {buyer.market_codes?.length > 0 ? (
                    buyer.market_codes.map((m) => (
                      <Badge key={m} variant="outline">
                        <MapPin className="mr-1 h-3 w-3" />
                        {m}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-muted-foreground">All markets</span>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Budget Range</CardTitle>
              </CardHeader>
              <CardContent>
                {editing ? (
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Min Price</Label>
                      <Input
                        type="number"
                        value={editData.price_min || ''}
                        onChange={(e) =>
                          setEditData({
                            ...editData,
                            price_min: parseFloat(e.target.value) || undefined,
                          })
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Max Price</Label>
                      <Input
                        type="number"
                        value={editData.price_max || ''}
                        onChange={(e) =>
                          setEditData({
                            ...editData,
                            price_max: parseFloat(e.target.value) || undefined,
                          })
                        }
                      />
                    </div>
                  </div>
                ) : (
                  <p className="text-2xl font-bold">
                    ${(buyer.price_min || 0).toLocaleString()} - $
                    {buyer.price_max ? buyer.price_max.toLocaleString() : '∞'}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Acreage Range</CardTitle>
              </CardHeader>
              <CardContent>
                {editing ? (
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Min Acres</Label>
                      <Input
                        type="number"
                        value={editData.min_acres || ''}
                        onChange={(e) =>
                          setEditData({
                            ...editData,
                            min_acres: parseFloat(e.target.value) || undefined,
                          })
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Max Acres</Label>
                      <Input
                        type="number"
                        value={editData.max_acres || ''}
                        onChange={(e) =>
                          setEditData({
                            ...editData,
                            max_acres: parseFloat(e.target.value) || undefined,
                          })
                        }
                      />
                    </div>
                  </div>
                ) : (
                  <p className="text-2xl font-bold">
                    {buyer.min_acres || 0} - {buyer.max_acres || '∞'} acres
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Property Types</CardTitle>
            </CardHeader>
            <CardContent>
              {editing ? (
                <div className="flex flex-wrap gap-3">
                  {PROPERTY_TYPE_OPTIONS.map((pt) => (
                    <label key={pt} className="flex items-center gap-2">
                      <Checkbox
                        checked={editData.property_types?.includes(pt)}
                        onCheckedChange={(checked) => {
                          const types = editData.property_types || [];
                          setEditData({
                            ...editData,
                            property_types: checked
                              ? [...types, pt]
                              : types.filter((t) => t !== pt),
                          });
                        }}
                      />
                      <span className="capitalize">{pt}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {buyer.property_types?.length > 0 ? (
                    buyer.property_types.map((pt) => (
                      <Badge key={pt} variant="secondary" className="capitalize">
                        {pt}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-muted-foreground">All types</span>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Target Spread</CardTitle>
                <CardDescription>Desired assignment fee</CardDescription>
              </CardHeader>
              <CardContent>
                {editing ? (
                  <Input
                    type="number"
                    value={editData.target_spread || ''}
                    onChange={(e) =>
                      setEditData({
                        ...editData,
                        target_spread: parseFloat(e.target.value) || undefined,
                      })
                    }
                  />
                ) : (
                  <p className="text-2xl font-bold">
                    {buyer.target_spread ? `$${buyer.target_spread.toLocaleString()}` : 'Not set'}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Closing Speed</CardTitle>
                <CardDescription>Days to close</CardDescription>
              </CardHeader>
              <CardContent>
                {editing ? (
                  <Input
                    type="number"
                    value={editData.closing_speed_days || ''}
                    onChange={(e) =>
                      setEditData({
                        ...editData,
                        closing_speed_days: parseInt(e.target.value) || undefined,
                      })
                    }
                  />
                ) : (
                  <p className="text-2xl font-bold">
                    {buyer.closing_speed_days ? `${buyer.closing_speed_days} days` : 'Not set'}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="deals">
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Lead ID</TableHead>
                    <TableHead>Stage</TableHead>
                    <TableHead>Match Score</TableHead>
                    <TableHead>Offer</TableHead>
                    <TableHead>Sent</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deals.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                        No deals yet
                      </TableCell>
                    </TableRow>
                  ) : (
                    deals.map((deal) => (
                      <TableRow
                        key={deal.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => navigate(`/leads/${deal.lead_id}`)}
                      >
                        <TableCell className="font-mono">#{deal.lead_id}</TableCell>
                        <TableCell>
                          <Badge className={BUYER_DEAL_STAGE_COLORS[deal.stage] || 'bg-gray-500'}>
                            {deal.stage}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {deal.match_score ? `${deal.match_score.toFixed(0)}%` : '-'}
                        </TableCell>
                        <TableCell>
                          {deal.offer_amount ? `$${deal.offer_amount.toLocaleString()}` : '-'}
                        </TableCell>
                        <TableCell>
                          {deal.blast_sent_at
                            ? new Date(deal.blast_sent_at).toLocaleDateString()
                            : '-'}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pof" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileCheck className="h-5 w-5" />
                Proof of Funds
              </CardTitle>
              <CardDescription>
                Upload and verify buyer's proof of funds documentation
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <p className="font-medium">Status</p>
                  <div className="flex items-center gap-2 mt-1">
                    {buyer.pof_verified ? (
                      <Badge className="bg-green-500">Verified</Badge>
                    ) : buyer.pof_url ? (
                      <Badge variant="outline">Pending Review</Badge>
                    ) : (
                      <Badge variant="secondary">Not Uploaded</Badge>
                    )}
                  </div>
                </div>
                <Button onClick={() => setPofDialogOpen(true)}>
                  <Upload className="mr-2 h-4 w-4" />
                  {buyer.pof_url ? 'Update POF' : 'Upload POF'}
                </Button>
              </div>

              {buyer.pof_url && (
                <div className="p-4 border rounded-lg">
                  <p className="text-sm text-muted-foreground mb-2">Current POF Document</p>
                  <a
                    href={buyer.pof_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-primary hover:underline"
                  >
                    <ExternalLink className="h-4 w-4" />
                    View Document
                  </a>
                  {buyer.pof_last_updated && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Last updated: {new Date(buyer.pof_last_updated).toLocaleDateString()}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* POF Dialog */}
      <Dialog open={pofDialogOpen} onOpenChange={setPofDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Update Proof of Funds</DialogTitle>
            <DialogDescription>Enter the URL to the POF document</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>POF Document URL</Label>
              <Input
                value={pofUrl}
                onChange={(e) => setPofUrl(e.target.value)}
                placeholder="https://drive.google.com/..."
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="pof-verified"
                checked={pofVerified}
                onCheckedChange={(c) => setPofVerified(c as boolean)}
              />
              <Label htmlFor="pof-verified">Mark as Verified</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPofDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpdatePOF}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Buyer</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete {buyer.name}? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default BuyerDetail;
