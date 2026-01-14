/**
 * Call Prep Pack - Everything needed to quote and close
 * 
 * This is the MOST IMPORTANT SCREEN in the system.
 * Contains everything needed to confidently talk price, no scrolling between tabs.
 * 
 * Sections (IN THIS ORDER):
 * 1. Property Location (situs address or fallback + map)
 * 2. Mailing Address (clearly labeled, separate)
 * 3. Parcel Snapshot (acres, value, flags)
 * 4. Offer Helper (range + justification)
 * 5. Call Script (live injection)
 * 6. Notes + Call Outcome
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Phone,
  Mail,
  MapPin,
  Home,
  DollarSign,
  FileText,
  AlertTriangle,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Send,
  Flame,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useToast } from '@/components/ui/use-toast';
import { getCallPrepPack, type CallPrepPack } from '@/api/callPrep';
import { updatePipelineStage } from '@/api/leads';
import { cn } from '@/lib/utils';
import { PropertyMap } from '@/components/PropertyMap';

// Call outcome options
const CALL_OUTCOMES = [
  { value: 'interested', label: 'Interested', color: 'bg-green-500' },
  { value: 'thinking', label: 'Thinking About It', color: 'bg-yellow-500' },
  { value: 'not_interested', label: 'Not Interested', color: 'bg-gray-500' },
  { value: 'no_answer', label: 'No Answer', color: 'bg-blue-500' },
  { value: 'wrong_number', label: 'Wrong Number', color: 'bg-red-500' },
  { value: 'callback', label: 'Call Back Later', color: 'bg-purple-500' },
];

export function CallPrepPackPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  
  const [prepPack, setPrepPack] = useState<CallPrepPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Offer params (live updates)
  const [discountLow, setDiscountLow] = useState(0.55);
  const [discountHigh, setDiscountHigh] = useState(0.70);
  
  // Notes
  const [notes, setNotes] = useState('');
  const [callOutcome, setCallOutcome] = useState<string>('');
  const [savingOutcome, setSavingOutcome] = useState(false);
  
  // Script sections expanded state
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    opening: true,
    discovery: false,
    price: false,
    objections: false,
    closing: false,
  });
  
  // Copied state
  const [copiedSection, setCopiedSection] = useState<string | null>(null);

  // Load prep pack
  useEffect(() => {
    loadPrepPack();
  }, [id, discountLow, discountHigh]);

  async function loadPrepPack() {
    if (!id) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await getCallPrepPack(parseInt(id), discountLow, discountHigh);
      setPrepPack(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load prep pack');
    } finally {
      setLoading(false);
    }
  }

  const copyToClipboard = (text: string, section: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSection(section);
    setTimeout(() => setCopiedSection(null), 2000);
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const handleSaveOutcome = async () => {
    if (!prepPack || !callOutcome) return;
    
    setSavingOutcome(true);
    try {
      // Update pipeline stage based on outcome
      let newStage = prepPack.pipeline_stage;
      if (callOutcome === 'interested') {
        newStage = 'OFFER';
      } else if (callOutcome === 'not_interested' || callOutcome === 'wrong_number') {
        newStage = 'REVIEW';
      } else if (callOutcome !== 'no_answer') {
        newStage = 'CONTACTED';
      }
      
      await updatePipelineStage(prepPack.lead_id, newStage as any);
      
      toast({
        title: 'Outcome Saved',
        description: `Lead moved to ${newStage} stage`,
      });
      
      // Reload to get updated state
      loadPrepPack();
    } catch (err) {
      toast({
        title: 'Error',
        description: 'Failed to save outcome',
        variant: 'destructive',
      });
    } finally {
      setSavingOutcome(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10" />
          <Skeleton className="h-8 w-64" />
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (error || !prepPack) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
        <h2 className="text-xl font-semibold mb-2">Failed to Load</h2>
        <p className="text-muted-foreground mb-4">{error || 'Lead not found'}</p>
        <Button onClick={() => navigate('/leads')}>Back to Leads</Button>
      </div>
    );
  }

  const { owner, location, parcel, offer, script, map } = prepPack;

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{owner.name}</h1>
              <Badge className={prepPack.motivation_score >= 65 ? 'bg-red-500' : 'bg-blue-500'}>
                {prepPack.motivation_score >= 65 && <Flame className="h-3 w-3 mr-1" />}
                Score: {prepPack.motivation_score}
              </Badge>
              <Badge variant="outline">{prepPack.pipeline_stage}</Badge>
            </div>
            <div className="flex items-center gap-4 mt-1 text-muted-foreground">
              {owner.phone && (
                <a href={`tel:${owner.phone}`} className="flex items-center gap-1 hover:text-primary">
                  <Phone className="h-4 w-4" />
                  {owner.phone}
                </a>
              )}
              {owner.email && (
                <a href={`mailto:${owner.email}`} className="flex items-center gap-1 hover:text-primary">
                  <Mail className="h-4 w-4" />
                  {owner.email}
                </a>
              )}
            </div>
          </div>
        </div>
        <Button onClick={() => navigate(`/buyers`)}>
          <Send className="h-4 w-4 mr-2" />
          Send to Buyers
        </Button>
      </div>

      {/* Main Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* LEFT COLUMN */}
        <div className="space-y-6">
          {/* 1. PROPERTY LOCATION - PARCEL DATA ONLY */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <MapPin className="h-5 w-5 text-primary" />
                  Property Location
                </CardTitle>
                {/* Data Trust Indicator */}
                {location.property_location.has_coordinates ? (
                  <Badge variant="outline" className="text-green-600 border-green-300">
                    <Check className="h-3 w-3 mr-1" />
                    Verified Coordinates
                  </Badge>
                ) : location.property_location.has_situs_address ? (
                  <Badge variant="outline" className="text-blue-600 border-blue-300">
                    Situs Address Only
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-yellow-600 border-yellow-300">
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    Parcel ID Only
                  </Badge>
                )}
              </div>
              <CardDescription>
                {location.property_location.has_situs_address 
                  ? "Where the land is located (from parcel records)"
                  : "⚠️ No situs address - use parcel ID for identification"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className={`p-4 rounded-lg ${location.property_location.has_situs_address ? 'bg-muted' : 'bg-yellow-50 border border-yellow-200'}`}>
                <p className="font-medium">{location.property_location.full_address}</p>
                {!location.property_location.has_situs_address && (
                  <div className="mt-2 space-y-1">
                    <p className="text-sm text-yellow-700">
                      ⚠️ No situs address on file for this parcel
                    </p>
                    <p className="text-xs text-yellow-600">
                      Verify property location using parish assessor records before making offer.
                    </p>
                  </div>
                )}
                {/* Data Source Label */}
                <p className="text-xs text-muted-foreground mt-2 italic">
                  Source: {location.property_location.data_trust === 'verified_gis' 
                    ? 'GIS/Parcel Records (High Trust)' 
                    : location.property_location.data_trust === 'parcel_record'
                    ? 'Tax Roll Records'
                    : 'Derived from parcel ID'}
                </p>
              </div>
              
              {/* Map - Leaflet/OpenStreetMap - No API keys required */}
              {/* PRODUCTION RULE: Only show map if we have verified coordinates or situs */}
              <PropertyMap
                latitude={map.latitude}
                longitude={map.longitude}
                parcelId={parcel.parcel_id || 'Unknown'}
                parish={parcel.parish || 'Unknown'}
                situsAddress={location.property_location.has_situs_address ? location.property_location.address_line1 : undefined}
                className="h-64"
              />
              
              {/* Map Trust Warning */}
              {!map.has_coordinates && !location.property_location.has_situs_address && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-sm text-yellow-700 font-medium">
                    ⚠️ Map location cannot be verified
                  </p>
                  <p className="text-xs text-yellow-600 mt-1">
                    No coordinates or situs address available. Use parish assessor GIS to verify parcel location.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 2. MAILING ADDRESS - OWNER CONTACT ONLY */}
          <Card className="border-dashed">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Mail className="h-5 w-5" />
                  Mailing Address
                </CardTitle>
                <Badge variant="secondary" className="text-xs">
                  Mail Only
                </Badge>
              </div>
              <CardDescription className="text-yellow-600">
                ⚠️ This is where the owner receives mail — NOT the property location
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="p-4 bg-muted rounded-lg border-l-4 border-l-yellow-400">
                <p className={location.mailing_address.is_available ? 'font-medium' : 'text-muted-foreground italic'}>
                  {location.mailing_address.display}
                </p>
                {!location.mailing_address.is_available && (
                  <p className="text-xs text-muted-foreground mt-1">
                    No mailing address on file
                  </p>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-2 italic">
                🚫 Never use this address for property identification or mapping
              </p>
            </CardContent>
          </Card>

          {/* 3. PARCEL SNAPSHOT */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Home className="h-5 w-5" />
                Parcel Snapshot
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground">Parcel ID</p>
                  <p className="font-mono text-sm">{parcel.parcel_id || 'Unknown'}</p>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground">Parish</p>
                  <p className="font-medium">{parcel.parish || 'Unknown'}</p>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground">Acreage</p>
                  <p className="font-medium">{parcel.acreage ? `${parcel.acreage.toFixed(2)} acres` : 'Unknown'}</p>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground">Land Value</p>
                  <p className="font-medium">{parcel.land_value ? `$${parcel.land_value.toLocaleString()}` : 'Unknown'}</p>
                </div>
              </div>
              
              {/* Flags */}
              <div className="flex gap-2 mt-4">
                {parcel.is_adjudicated && (
                  <Badge variant="destructive">Adjudicated</Badge>
                )}
                {parcel.years_tax_delinquent > 0 && (
                  <Badge variant="outline" className="border-yellow-500 text-yellow-600">
                    {parcel.years_tax_delinquent}yr Tax Delinquent
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT COLUMN */}
        <div className="space-y-6">
          {/* 4. OFFER HELPER */}
          <Card className={`border-2 ${offer.can_make_offer ? 'border-primary' : 'border-yellow-400'}`}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-lg">
                  <DollarSign className="h-5 w-5 text-primary" />
                  Offer Range
                </CardTitle>
                {/* Confidence Badge with color coding */}
                <Badge 
                  variant="outline" 
                  className={cn(
                    offer.confidence === 'high' && 'text-green-600 border-green-300',
                    offer.confidence === 'medium' && 'text-yellow-600 border-yellow-300',
                    offer.confidence === 'low' && 'text-orange-600 border-orange-300',
                    offer.confidence === 'cannot_compute' && 'text-red-600 border-red-300',
                  )}
                >
                  {offer.confidence === 'high' && <Check className="h-3 w-3 mr-1" />}
                  {(offer.confidence === 'low' || offer.confidence === 'cannot_compute') && <AlertTriangle className="h-3 w-3 mr-1" />}
                  {offer.confidence} confidence
                </Badge>
              </div>
              <CardDescription>
                {offer.can_make_offer 
                  ? "Adjust discounts to update range" 
                  : "⚠️ Cannot compute offer - missing data"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Cannot Compute Warning */}
              {!offer.can_make_offer && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-700 font-medium">
                    ⚠️ {offer.cannot_offer_reason || 'Missing required data'}
                  </p>
                  <p className="text-xs text-red-600 mt-1">
                    Check parcel records for assessed land value before making an offer.
                  </p>
                </div>
              )}
              
              {/* Range Display */}
              <div className={`text-center p-6 rounded-lg ${offer.can_make_offer ? 'bg-primary/10' : 'bg-muted'}`}>
                <p className="text-sm text-muted-foreground mb-1">Suggested Offer</p>
                <p className={`text-3xl font-bold ${offer.can_make_offer ? 'text-primary' : 'text-muted-foreground'}`}>
                  {offer.range_display}
                </p>
                {offer.can_make_offer && offer.price_per_acre_low && offer.price_per_acre_high ? (
                  <p className="text-sm text-muted-foreground mt-1">
                    ${offer.price_per_acre_low.toLocaleString()} - ${offer.price_per_acre_high.toLocaleString()} per acre
                  </p>
                ) : offer.can_make_offer && offer.per_acre_display ? (
                  <p className="text-sm text-yellow-600 mt-1">
                    {offer.per_acre_display}
                  </p>
                ) : null}
              </div>
              
              {/* Missing Data Summary */}
              {offer.missing_data_summary && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-sm text-yellow-700">
                    ⚠️ {offer.missing_data_summary}
                  </p>
                </div>
              )}
              
              {/* Discount Sliders */}
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span>Low Discount</span>
                    <span>{Math.round(discountLow * 100)}%</span>
                  </div>
                  <Slider
                    value={[discountLow * 100]}
                    onValueChange={([v]: number[]) => setDiscountLow(v / 100)}
                    min={30}
                    max={80}
                    step={5}
                  />
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span>High Discount</span>
                    <span>{Math.round(discountHigh * 100)}%</span>
                  </div>
                  <Slider
                    value={[discountHigh * 100]}
                    onValueChange={([v]: number[]) => setDiscountHigh(v / 100)}
                    min={40}
                    max={95}
                    step={5}
                  />
                </div>
              </div>
              
              {/* Justification */}
              <div className="space-y-2">
                <p className="text-sm font-medium">Justification</p>
                {offer.justifications.map((j, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className={cn(
                      'w-2 h-2 rounded-full',
                      j.impact === 'increase' && 'bg-green-500',
                      j.impact === 'decrease' && 'bg-red-500',
                      j.impact === 'neutral' && 'bg-gray-400'
                    )} />
                    <span>{j.description}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* 6. NOTES + CALL OUTCOME */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <FileText className="h-5 w-5" />
                Call Notes & Outcome
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                placeholder="Notes from the call..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={4}
              />
              
              <div className="flex items-center gap-4">
                <Select value={callOutcome} onValueChange={setCallOutcome}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Call outcome..." />
                  </SelectTrigger>
                  <SelectContent>
                    {CALL_OUTCOMES.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        <div className="flex items-center gap-2">
                          <span className={cn('w-2 h-2 rounded-full', o.color)} />
                          {o.label}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                
                <Button 
                  onClick={handleSaveOutcome} 
                  disabled={!callOutcome || savingOutcome}
                >
                  {savingOutcome ? 'Saving...' : 'Save Outcome'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 5. CALL SCRIPT - Full Width */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Phone className="h-5 w-5" />
            Call Script
          </CardTitle>
          <CardDescription>
            Click sections to expand • Values update live with offer changes
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {/* Opening */}
          <Collapsible open={expandedSections.opening} onOpenChange={() => toggleSection('opening')}>
            <CollapsibleTrigger className="flex items-center justify-between w-full p-3 bg-muted rounded-lg hover:bg-muted/80">
              <span className="font-medium">Opening</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(script.opening, 'opening');
                  }}
                >
                  {copiedSection === 'opening' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
                {expandedSections.opening ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="p-4 border rounded-lg mt-2">
              <pre className="whitespace-pre-wrap text-sm font-sans">{script.opening}</pre>
            </CollapsibleContent>
          </Collapsible>

          {/* Discovery */}
          <Collapsible open={expandedSections.discovery} onOpenChange={() => toggleSection('discovery')}>
            <CollapsibleTrigger className="flex items-center justify-between w-full p-3 bg-muted rounded-lg hover:bg-muted/80">
              <span className="font-medium">Discovery Questions</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(script.discovery, 'discovery');
                  }}
                >
                  {copiedSection === 'discovery' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
                {expandedSections.discovery ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="p-4 border rounded-lg mt-2">
              <pre className="whitespace-pre-wrap text-sm font-sans">{script.discovery}</pre>
            </CollapsibleContent>
          </Collapsible>

          {/* Price Discussion */}
          <Collapsible open={expandedSections.price} onOpenChange={() => toggleSection('price')}>
            <CollapsibleTrigger className="flex items-center justify-between w-full p-3 bg-primary/10 rounded-lg hover:bg-primary/20">
              <span className="font-medium text-primary">Price Discussion</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(script.price_discussion, 'price');
                  }}
                >
                  {copiedSection === 'price' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
                {expandedSections.price ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="p-4 border border-primary/20 rounded-lg mt-2">
              <pre className="whitespace-pre-wrap text-sm font-sans">{script.price_discussion}</pre>
            </CollapsibleContent>
          </Collapsible>

          {/* Objection Handlers */}
          <Collapsible open={expandedSections.objections} onOpenChange={() => toggleSection('objections')}>
            <CollapsibleTrigger className="flex items-center justify-between w-full p-3 bg-muted rounded-lg hover:bg-muted/80">
              <span className="font-medium">Objection Handlers</span>
              {expandedSections.objections ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </CollapsibleTrigger>
            <CollapsibleContent className="p-4 border rounded-lg mt-2 space-y-4">
              {script.objection_handlers.map((obj, i) => (
                <div key={i} className="space-y-2">
                  <p className="font-medium text-red-600">"{obj.objection}"</p>
                  <p className="text-sm pl-4 border-l-2 border-green-500">{obj.response}</p>
                </div>
              ))}
            </CollapsibleContent>
          </Collapsible>

          {/* Closing */}
          <Collapsible open={expandedSections.closing} onOpenChange={() => toggleSection('closing')}>
            <CollapsibleTrigger className="flex items-center justify-between w-full p-3 bg-muted rounded-lg hover:bg-muted/80">
              <span className="font-medium">Closing</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(script.closing, 'closing');
                  }}
                >
                  {copiedSection === 'closing' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
                {expandedSections.closing ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="p-4 border rounded-lg mt-2">
              <pre className="whitespace-pre-wrap text-sm font-sans">{script.closing}</pre>
            </CollapsibleContent>
          </Collapsible>
        </CardContent>
      </Card>
    </div>
  );
}

export default CallPrepPackPage;

