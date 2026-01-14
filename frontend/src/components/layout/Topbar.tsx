import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search, Bell, User, ChevronDown, Menu, Flame, TrendingUp, Clock } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTheme } from '@/components/theme-provider';
import { ActiveMarketBadge } from '@/components/active-market-provider';
import { getAlerts, type Alert } from '@/api/alerts';

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/dashboard': 'Dashboard',
  '/leads': 'Leads',
  '/outreach': 'Outreach',
  '/owners': 'Owners',
  '/parcels': 'Parcels',
  '/ingestion': 'Ingestion',
  '/settings': 'Settings',
};

export function Topbar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const { theme, toggleTheme } = useTheme();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertCount, setAlertCount] = useState(0);

  // Fetch alerts on mount
  useEffect(() => {
    async function fetchAlerts() {
      try {
        const data = await getAlerts('LA', 10);
        setAlerts(data.alerts);
        setAlertCount(data.total);
      } catch (error) {
        console.error('Failed to fetch alerts:', error);
        setAlerts([]);
        setAlertCount(0);
      }
    }
    fetchAlerts();
    // Refresh alerts every 60 seconds
    const interval = setInterval(fetchAlerts, 60000);
    return () => clearInterval(interval);
  }, []);

  // Get page title from path
  const pathKey = location.pathname.split('/').slice(0, 2).join('/') || '/';
  const pageTitle = PAGE_TITLES[pathKey] || 'Dashboard';

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      window.location.href = `/leads?q=${encodeURIComponent(searchQuery)}`;
    }
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-14 items-center gap-4 px-4 lg:px-6">
        {/* Mobile menu button */}
        <Button variant="ghost" size="icon" className="lg:hidden">
          <Menu className="h-5 w-5" />
        </Button>

        {/* Page title */}
        <div className="flex-1">
          <h1 className="text-lg font-semibold">{pageTitle}</h1>
        </div>

        {/* Active Market Badge - Shows current working area */}
        <ActiveMarketBadge />

        {/* Search bar */}
        <form onSubmit={handleSearch} className="hidden md:flex">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search leads..."
              className="w-[200px] pl-8 lg:w-[280px]"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </form>

        {/* Notifications/Alerts */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative">
              <Bell className="h-5 w-5" />
              {alertCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-medium text-white">
                  {alertCount > 9 ? '9+' : alertCount}
                </span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <DropdownMenuLabel className="flex items-center justify-between">
              <span>Alerts</span>
              <span className="text-xs text-muted-foreground">{alertCount} total</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {alerts.length === 0 ? (
              <div className="py-4 text-center text-sm text-muted-foreground">
                No alerts at this time
              </div>
            ) : (
              alerts.slice(0, 5).map((alert, idx) => (
                <DropdownMenuItem
                  key={`${alert.type}-${alert.lead_id}-${idx}`}
                  className="flex items-start gap-2 cursor-pointer"
                  onClick={() => navigate(`/leads/${alert.lead_id}`)}
                >
                  <div className="mt-0.5">
                    {alert.type === 'hot_lead' && <Flame className="h-4 w-4 text-red-500" />}
                    {alert.type === 'high_score' && <TrendingUp className="h-4 w-4 text-green-500" />}
                    {alert.type === 'followup_due' && <Clock className="h-4 w-4 text-yellow-500" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{alert.title}</p>
                    <p className="text-xs text-muted-foreground truncate">{alert.description}</p>
                  </div>
                </DropdownMenuItem>
              ))
            )}
            {alerts.length > 5 && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="justify-center text-sm text-muted-foreground"
                  onClick={() => navigate('/leads?pipeline_stage=HOT')}
                >
                  View all alerts
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <User className="h-4 w-4" />
              </div>
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>My Account</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={toggleTheme}>
              {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
            </DropdownMenuItem>
            <DropdownMenuItem>Settings</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive">Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
