import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import type { MarketCode } from '@/lib/types';

interface MarketContextType {
  market: MarketCode;
  setMarket: (market: MarketCode) => void;
}

const MarketContext = createContext<MarketContextType | undefined>(undefined);

const MARKET_STORAGE_KEY = 'la-land-wholesale-market';

interface MarketProviderProps {
  children: ReactNode;
  defaultMarket?: MarketCode;
}

export function MarketProvider({
  children,
  defaultMarket = 'LA',
}: MarketProviderProps) {
  const [market, setMarketState] = useState<MarketCode>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(MARKET_STORAGE_KEY);
      if (stored && ['LA', 'TX', 'MS', 'AR', 'AL'].includes(stored)) {
        return stored as MarketCode;
      }
    }
    return defaultMarket;
  });

  const setMarket = (newMarket: MarketCode) => {
    setMarketState(newMarket);
    if (typeof window !== 'undefined') {
      localStorage.setItem(MARKET_STORAGE_KEY, newMarket);
    }
  };

  useEffect(() => {
    // Sync with localStorage on mount
    const stored = localStorage.getItem(MARKET_STORAGE_KEY);
    if (stored && ['LA', 'TX', 'MS', 'AR', 'AL'].includes(stored)) {
      setMarketState(stored as MarketCode);
    }
  }, []);

  return (
    <MarketContext.Provider value={{ market, setMarket }}>
      {children}
    </MarketContext.Provider>
  );
}

export function useMarket() {
  const context = useContext(MarketContext);
  if (context === undefined) {
    throw new Error('useMarket must be used within a MarketProvider');
  }
  return context;
}

export { MarketContext };

