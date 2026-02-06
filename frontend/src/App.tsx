import { Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from '@/components/layout/MainLayout';
import { Toaster } from '@/components/ui/toaster';
import { MarketProvider } from '@/components/market-provider';
import { ActiveMarketProvider } from '@/components/active-market-provider';
import { AuthProvider } from '@/contexts/AuthContext';
import { AuthGuard } from '@/components/AuthGuard';
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
import { Login } from '@/pages/Login';
import { Register } from '@/pages/Register';

function App() {
  return (
    <AuthProvider>
      <MarketProvider defaultMarket="LA">
        <ActiveMarketProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Protected routes */}
            <Route
              path="/*"
              element={
                <AuthGuard>
                  <MainLayout>
                    <Routes>
                      <Route path="/" element={<Navigate to="/dashboard" replace />} />
                      <Route path="/inbox" element={<Inbox />} />
                      <Route path="/dashboard" element={<Dashboard />} />
                      <Route path="/leads" element={<Leads />} />
                      <Route path="/leads/:id" element={<CallPrepPack />} />
                      <Route path="/parcels" element={<Parcels />} />
                      <Route path="/outreach" element={<Outreach />} />
                      <Route path="/buyers" element={<Buyers />} />
                      <Route path="/buyers/:id" element={<BuyerDetail />} />
                      <Route path="/comps" element={<Comps />} />
                      <Route path="/ingestion" element={<Ingestion />} />
                      <Route path="/settings" element={<Settings />} />
                    </Routes>
                  </MainLayout>
                </AuthGuard>
              }
            />
          </Routes>
          <Toaster />
        </ActiveMarketProvider>
      </MarketProvider>
    </AuthProvider>
  );
}

export default App;
