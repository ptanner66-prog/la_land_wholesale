import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Settings,
  Database,
  ChevronDown,
  ChevronRight,
  MessageSquare,
  Send,
  UserCheck,
  MapPin,
  LogOut,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { LogoWithText } from '@/components/ui/logo';
import { useAuth } from '@/contexts/AuthContext';

interface NavItem {
  path: string;
  label: string;
  icon: React.ElementType;
  highlight?: boolean;
}

interface NavGroup {
  label: string;
  icon: React.ElementType;
  items: NavItem[];
  defaultOpen?: boolean;
}

const navGroups: NavGroup[] = [
  {
    label: 'Home',
    icon: LayoutDashboard,
    defaultOpen: true,
    items: [
      { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, highlight: true },
    ],
  },
  {
    label: 'Conversations',
    icon: MessageSquare,
    defaultOpen: true,
    items: [
      { path: '/inbox', label: 'Inbox', icon: MessageSquare },
      { path: '/outreach', label: 'Send SMS', icon: Send },
    ],
  },
  {
    label: 'Leads',
    icon: Users,
    defaultOpen: true,
    items: [
      { path: '/leads', label: 'All Leads', icon: Users },
    ],
  },
  {
    label: 'Buyers',
    icon: UserCheck,
    defaultOpen: false,
    items: [
      { path: '/buyers', label: 'Buyer List', icon: UserCheck },
    ],
  },
  {
    label: 'Tools',
    icon: MapPin,
    defaultOpen: false,
    items: [
      { path: '/comps', label: 'Comps', icon: MapPin },
    ],
  },
  {
    label: 'System',
    icon: Settings,
    defaultOpen: false,
    items: [
      { path: '/ingestion', label: 'Ingestion', icon: Database },
      { path: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [openGroups, setOpenGroups] = useState<string[]>(
    navGroups.filter((g) => g.defaultOpen).map((g) => g.label)
  );

  function toggleGroup(label: string) {
    setOpenGroups((prev) =>
      prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]
    );
  }

  function isItemActive(path: string): boolean {
    // Dashboard is the default landing page
    if (path === '/dashboard') {
      return location.pathname === '/' || location.pathname === '/dashboard';
    }
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

  return (
    <aside className="hidden lg:flex h-screen w-64 flex-col fixed left-0 top-0 border-r border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-border/40 px-4">
        <Link to="/" className="flex items-center gap-2">
          <LogoWithText />
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-4 space-y-2">
        {navGroups.map((group) => {
          const isOpen = openGroups.includes(group.label);
          const hasActiveItem = group.items.some((item) => isItemActive(item.path));

          return (
            <div key={group.label}>
              {/* Group Header */}
              <button
                onClick={() => toggleGroup(group.label)}
                className={cn(
                  'flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  hasActiveItem
                    ? 'text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <div className="flex items-center gap-2">
                  <group.icon className="h-4 w-4" />
                  <span>{group.label}</span>
                </div>
                {isOpen ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </button>

              {/* Group Items */}
              {isOpen && (
                <div className="ml-4 mt-1 space-y-1 border-l border-border/40 pl-3">
                  {group.items.map((item) => {
                    const isActive = isItemActive(item.path);

                    return (
                      <Link
                        key={`${group.label}-${item.path}-${item.label}`}
                        to={item.path}
                        className={cn(
                          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                          isActive
                            ? 'bg-primary text-primary-foreground font-medium'
                            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                        )}
                      >
                        <item.icon className="h-4 w-4" />
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-border/40 p-4 space-y-2">
        {user && (
          <div className="text-xs text-muted-foreground truncate">{user.email}</div>
        )}
        <button
          onClick={async () => {
            await logout();
            navigate('/login');
          }}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign Out
        </button>
        <div className="text-xs text-muted-foreground">LA Land Wholesale v2.0</div>
      </div>
    </aside>
  );
}
