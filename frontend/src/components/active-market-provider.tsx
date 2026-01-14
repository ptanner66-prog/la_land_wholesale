/**
 * Active Market Provider - Enforces area locking for all operations
 * 
 * The Active Market is the single source of truth for area-scoped operations.
 * If no market is selected, a modal blocks access to the application.
 */
import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { 
  getActiveMarket, 
  setActiveMarket as apiSetActiveMarket, 
  getAvailableParishes,
  type ActiveMarket,
  type ParishesByState,
  type ParishSummary,
} from '@/api/activeMarket';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { MapPin, Flame, Users } from 'lucide-react';

interface ActiveMarketContextType {
  activeMarket: ActiveMarket | null;
  isLoading: boolean;
  setActiveMarket: (state: string, parish: string) => Promise<void>;
  clearActiveMarket: () => void;
  parishesByState: ParishesByState;
  summary: ParishSummary | null;
}

const ActiveMarketContext = createContext<ActiveMarketContextType | undefined>(undefined);

interface ActiveMarketProviderProps {
  children: ReactNode;
}

export function ActiveMarketProvider({ children }: ActiveMarketProviderProps) {
  const [activeMarket, setActiveMarketState] = useState<ActiveMarket | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [parishesByState, setParishesByState] = useState<ParishesByState>({});
  const [summary, setSummary] = useState<ParishSummary | null>(null);
  const [showSelector, setShowSelector] = useState(false);
  
  // Selector state
  const [selectedState, setSelectedState] = useState<string>('');
  const [selectedParish, setSelectedParish] = useState<string>('');

  // Load active market and available parishes on mount
  useEffect(() => {
    async function init() {
      try {
        const [market, parishes] = await Promise.all([
          getActiveMarket(),
          getAvailableParishes(),
        ]);

        setParishesByState(parishes.parishes_by_state);

        // Auto-select LA/East Baton Rouge if no market active
        if (!market.active) {
          console.log('No active market, auto-selecting LA/East Baton Rouge');
          try {
            await apiSetActiveMarket('LA', 'East Baton Rouge');
            const updatedMarket = await getActiveMarket();
            setActiveMarketState(updatedMarket.active ? updatedMarket : null);
          } catch (e) {
            console.error('Failed to auto-select market:', e);
            setActiveMarketState(null);
          }
        } else {
          setActiveMarketState(market);
        }
      } catch (error) {
        console.error('Failed to load active market:', error);
      } finally {
        setIsLoading(false);
      }
    }
    init();
  }, []);

  const setActiveMarket = useCallback(async (state: string, parish: string) => {
    try {
      const result = await apiSetActiveMarket(state, parish);
      setActiveMarketState({
        active: true,
        state: result.active_market.state,
        parish: result.active_market.parish,
        display_name: result.active_market.display_name,
        market_code: result.active_market.market_code,
      });
      setSummary(result.summary);
      setShowSelector(false);
    } catch (error) {
      console.error('Failed to set active market:', error);
      throw error;
    }
  }, []);

  const clearActiveMarket = useCallback(() => {
    setActiveMarketState(null);
    setSummary(null);
    setShowSelector(true);
  }, []);

  const handleConfirmSelection = async () => {
    if (selectedState && selectedParish) {
      await setActiveMarket(selectedState, selectedParish);
    }
  };

  // Get parishes for selected state
  const availableParishes = selectedState ? parishesByState[selectedState] || [] : [];
  const states = Object.keys(parishesByState);

  return (
    <ActiveMarketContext.Provider
      value={{
        activeMarket,
        isLoading,
        setActiveMarket,
        clearActiveMarket,
        parishesByState,
        summary,
      }}
    >
      {/* Market Selection Modal - Optional */}
      <Dialog open={showSelector && !isLoading} onOpenChange={setShowSelector}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <MapPin className="h-5 w-5 text-primary" />
              Select Working Area
            </DialogTitle>
            <DialogDescription>
              Choose a state and parish to begin. All operations will be scoped to this area.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {/* State Selector */}
            <div className="space-y-2">
              <label className="text-sm font-medium">State</label>
              <Select value={selectedState} onValueChange={(v) => {
                setSelectedState(v);
                setSelectedParish('');
              }}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a state" />
                </SelectTrigger>
                <SelectContent>
                  {states.map((state) => (
                    <SelectItem key={state} value={state}>
                      {state} ({parishesByState[state]?.length || 0} parishes)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {/* Parish Selector */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Parish / County</label>
              <Select 
                value={selectedParish} 
                onValueChange={setSelectedParish}
                disabled={!selectedState}
              >
                <SelectTrigger>
                  <SelectValue placeholder={selectedState ? "Select a parish" : "Select a state first"} />
                </SelectTrigger>
                <SelectContent>
                  {availableParishes.map((p) => (
                    <SelectItem key={p.parish} value={p.parish}>
                      <div className="flex items-center justify-between w-full">
                        <span>{p.parish}</span>
                        <Badge variant="secondary" className="ml-2">
                          {p.lead_count.toLocaleString()} leads
                        </Badge>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {/* Preview */}
            {selectedState && selectedParish && (
              <div className="rounded-lg border bg-muted/50 p-4">
                <div className="text-sm font-medium text-muted-foreground mb-2">
                  Working Area Preview
                </div>
                <div className="text-lg font-semibold">
                  {selectedParish} Parish, {selectedState}
                </div>
                <div className="text-sm text-muted-foreground mt-1">
                  {availableParishes.find(p => p.parish === selectedParish)?.lead_count.toLocaleString() || 0} leads available
                </div>
              </div>
            )}
          </div>
          
          <div className="flex justify-end gap-2">
            <Button
              onClick={handleConfirmSelection}
              disabled={!selectedState || !selectedParish}
            >
              <MapPin className="h-4 w-4 mr-2" />
              Set Working Area
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      
      {children}
    </ActiveMarketContext.Provider>
  );
}

export function useActiveMarket() {
  const context = useContext(ActiveMarketContext);
  if (context === undefined) {
    throw new Error('useActiveMarket must be used within an ActiveMarketProvider');
  }
  return context;
}

/**
 * Component that displays the current active market in the header
 */
export function ActiveMarketBadge() {
  const { activeMarket, clearActiveMarket, summary } = useActiveMarket();
  
  if (!activeMarket?.active) {
    return null;
  }
  
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20">
      <MapPin className="h-4 w-4 text-primary" />
      <div className="flex flex-col">
        <span className="text-sm font-medium">{activeMarket.display_name}</span>
        {summary && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Flame className="h-3 w-3 text-red-500" />
              {summary.hot_leads} hot
            </span>
            <span className="flex items-center gap-1">
              <Users className="h-3 w-3 text-blue-500" />
              {summary.contact_leads} contact
            </span>
          </div>
        )}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs"
        onClick={clearActiveMarket}
      >
        Change
      </Button>
    </div>
  );
}

export { ActiveMarketContext };

