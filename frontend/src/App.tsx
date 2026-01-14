import { Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from '@/components/layout/MainLayout';
import { Toaster } from '@/components/ui/toaster';
import { MarketProvider } from '@/components/market-provider';
import { ActiveMarketProvider } from '@/components/active-market-provider';
import {
  Dashboard,
  Leads,
  Outreach,
  Parcels,
  Ingestion,
  Settings,
  Comps,
  Inbox,
} from '@/pages';
import { Buyers } from '@/pages/Buyers';
import { BuyerDetail } from '@/pages/BuyerDetail';
import CallPrepPack from '@/pages/CallPrepPack';

function App() {
  return (
    <MarketProvider defaultMarket="LA">
      <ActiveMarketProvider>
        <MainLayout>
          <Routes>
            {/* Default to Dashboard (mission control) */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/dashboard" element={<Dashboard />} />
            
            {/* Leads */}
            <Route path="/leads" element={<Leads />} />
            <Route path="/leads/:id" element={<CallPrepPack />} />
            <Route path="/parcels" element={<Parcels />} />
            
            {/* Outreach */}
            <Route path="/outreach" element={<Outreach />} />
            
            {/* Buyers */}
            <Route path="/buyers" element={<Buyers />} />
            <Route path="/buyers/:id" element={<BuyerDetail />} />
            
            {/* Tools */}
            <Route path="/comps" element={<Comps />} />
            
            {/* System */}
            <Route path="/ingestion" element={<Ingestion />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </MainLayout>
        <Toaster />
      </ActiveMarketProvider>
    </MarketProvider>
  );
}

export default App;
