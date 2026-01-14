import { useState, useEffect } from 'react';
import {
  Settings as SettingsIcon,
  Moon,
  Sun,
  Bell,
  Globe,
  Play,
  Loader2,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import { useTheme } from '@/components/theme-provider';
import { useMarket } from '@/components/market-provider';
import { getHealthStatus, getDetailedHealth, getExternalServicesHealth } from '@/api/health';
import {
  getAlertConfigs,
  updateAlertConfig,
  sendTestAlert,
  runNightlyPipeline,
} from '@/api/automation';
import { getMarkets } from '@/api/markets';
import type { AlertConfig, MarketConfig, MarketCode, HealthStatus } from '@/lib/types';

// Type for the checks object from detailed health
type ServiceChecks = Record<string, {
  status?: string;
  configured?: boolean;
  connected?: boolean;
  error?: string | null;
}>;

export function Settings() {
  const { toast } = useToast();
  const { theme, setTheme } = useTheme();
  const { market, setMarket } = useMarket();

  const [loading, setLoading] = useState(true);
  const [markets, setMarkets] = useState<MarketConfig[]>([]);
  const [alertConfigs, setAlertConfigs] = useState<AlertConfig[]>([]);
  const [_healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [servicesStatus, setServicesStatus] = useState<ServiceChecks | null>(null);

  // Alert config editing
  const [editingAlert, setEditingAlert] = useState<AlertConfig | null>(null);
  const [savingAlert, setSavingAlert] = useState(false);
  const [testingAlert, setTestingAlert] = useState<string | null>(null);

  // Pipeline
  const [runningPipeline, setRunningPipeline] = useState(false);

  // API URL
  const [apiUrl, setApiUrl] = useState(
    localStorage.getItem('api_base_url') || 'http://127.0.0.1:8001'
  );

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    setLoading(true);
    try {
      const [marketsData, alertsData, healthData, detailedHealth, externalHealth] = await Promise.all([
        getMarkets().catch(() => []),
        getAlertConfigs().catch(() => []),
        getHealthStatus().catch(() => null),
        getDetailedHealth().catch(() => null),
        getExternalServicesHealth().catch(() => null),
      ]);
      setMarkets(marketsData);
      setAlertConfigs(alertsData);
      setHealthStatus(healthData);
      // Merge detailed health checks with external services health for connected status
      const mergedChecks: ServiceChecks = detailedHealth?.checks || {};
      if (externalHealth?.services) {
        Object.keys(externalHealth.services).forEach(key => {
          const service = externalHealth.services[key];
          // Normalize error field from null to undefined
          const normalizedService = {
            ...service,
            error: service.error ?? undefined,
          };
          if (mergedChecks[key]) {
            mergedChecks[key] = { ...mergedChecks[key], ...normalizedService };
          } else {
            mergedChecks[key] = normalizedService;
          }
        });
      }
      setServicesStatus(mergedChecks);
    } catch (error) {
      console.error('Failed to fetch settings data:', error);
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveAlert() {
    if (!editingAlert) return;
    setSavingAlert(true);
    try {
      await updateAlertConfig(editingAlert.market_code, {
        enabled: editingAlert.enabled,
        hot_score_threshold: editingAlert.hot_score_threshold,
        alert_phone: editingAlert.alert_phone,
        slack_webhook_url: editingAlert.slack_webhook_url,
      });
      toast({ title: 'Success', description: 'Alert configuration saved' });
      setEditingAlert(null);
      fetchData();
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to save alert config', variant: 'destructive' });
    } finally {
      setSavingAlert(false);
    }
  }

  async function handleTestAlert(marketCode: MarketCode) {
    setTestingAlert(marketCode);
    try {
      const result = await sendTestAlert(marketCode);
      if (result.success) {
        toast({ title: 'Test Sent', description: 'Test alert was sent successfully' });
      } else {
        toast({ title: 'Failed', description: 'No alert channels configured', variant: 'destructive' });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to send test alert', variant: 'destructive' });
    } finally {
      setTestingAlert(null);
    }
  }

  async function handleRunPipeline() {
    setRunningPipeline(true);
    try {
      const result = await runNightlyPipeline([market], false);
      toast({
        title: 'Pipeline Complete',
        description: `Processed ${result.markets_processed.length} market(s)`,
      });
    } catch (error) {
      toast({ title: 'Error', description: 'Pipeline failed', variant: 'destructive' });
    } finally {
      setRunningPipeline(false);
    }
  }

  function handleSaveApiUrl() {
    localStorage.setItem('api_base_url', apiUrl);
    toast({ title: 'Saved', description: 'API URL saved. Refresh to apply.' });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
        <p className="text-muted-foreground">Manage your preferences and configuration</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Appearance */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {theme === 'dark' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
              Appearance
            </CardTitle>
            <CardDescription>Customize the look and feel</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Theme</Label>
                <p className="text-sm text-muted-foreground">Select your preferred theme</p>
              </div>
              <Select value={theme} onValueChange={(v) => setTheme(v as 'light' | 'dark' | 'system')}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="dark">Dark</SelectItem>
                  <SelectItem value="system">System</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Market Selection */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              Active Market
            </CardTitle>
            <CardDescription>Switch between markets</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Current Market</Label>
                <p className="text-sm text-muted-foreground">All data filtered by this market</p>
              </div>
              <Select value={market} onValueChange={(v) => setMarket(v as MarketCode)}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {markets.map((m) => (
                    <SelectItem key={m.code} value={m.code}>
                      {m.name} ({m.code})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* API Configuration */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <SettingsIcon className="h-5 w-5" />
              API Configuration
            </CardTitle>
            <CardDescription>Backend connection settings</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="api-url">API Base URL</Label>
              <div className="flex gap-2">
                <Input
                  id="api-url"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="http://localhost:8000"
                />
                <Button onClick={handleSaveApiUrl}>Save</Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* System Status */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              System Status
            </CardTitle>
            <CardDescription>Health of backend services</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span>Database</span>
                  <Badge variant={servicesStatus?.database?.status === 'healthy' ? 'default' : 'destructive'}>
                    {servicesStatus?.database?.status === 'healthy' ? 'Connected' : 'Error'}
                  </Badge>
                </div>
                {servicesStatus && (
                  <>
                    <div className="flex items-center justify-between">
                      <span>Twilio</span>
                      <Badge variant={
                        servicesStatus.twilio?.connected ? 'default' :
                        servicesStatus.twilio?.configured ? 'secondary' : 'destructive'
                      }>
                        {servicesStatus.twilio?.connected ? 'Connected' :
                         servicesStatus.twilio?.configured ? 'Configured (Not Connected)' : 'Not Configured'}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Google Maps</span>
                      <Badge variant={
                        servicesStatus.google_maps?.connected ? 'default' :
                        servicesStatus.google_maps?.configured ? 'secondary' : 'destructive'
                      }>
                        {servicesStatus.google_maps?.connected ? 'Connected' :
                         servicesStatus.google_maps?.configured ? 'Configured (Not Connected)' : 'Not Configured'}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>OpenAI</span>
                      <Badge variant={
                        servicesStatus.openai?.connected ? 'default' :
                        servicesStatus.openai?.configured ? 'secondary' : 'destructive'
                      }>
                        {servicesStatus.openai?.connected ? 'Connected' :
                         servicesStatus.openai?.configured ? 'Configured (Not Connected)' : 'Not Configured'}
                      </Badge>
                    </div>
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Alert Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Alert Configuration
          </CardTitle>
          <CardDescription>Configure hot lead alerts per market</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-4">
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </div>
          ) : (
            <div className="space-y-4">
              {alertConfigs.map((config) => (
                <div key={config.market_code} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <Badge>{config.market_code}</Badge>
                      <span className="font-medium">
                        {markets.find((m) => m.code === config.market_code)?.name || config.market_code}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={config.enabled ? 'default' : 'secondary'}>
                        {config.enabled ? 'Enabled' : 'Disabled'}
                      </Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingAlert({ ...config })}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleTestAlert(config.market_code)}
                        disabled={testingAlert === config.market_code}
                      >
                        {testingAlert === config.market_code ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          'Test'
                        )}
                      </Button>
                    </div>
                  </div>
                  <div className="grid gap-2 text-sm text-muted-foreground md:grid-cols-3">
                    <div>
                      <span className="font-medium">Threshold:</span> {config.hot_score_threshold}+
                    </div>
                    <div>
                      <span className="font-medium">Phone:</span>{' '}
                      {config.alert_phone || 'Not set'}
                    </div>
                    <div>
                      <span className="font-medium">Slack:</span>{' '}
                      {config.slack_webhook_url ? 'Configured' : 'Not set'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Edit Alert Dialog */}
          {editingAlert && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <Card className="w-full max-w-md">
                <CardHeader>
                  <CardTitle>Edit Alert Config: {editingAlert.market_code}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label>Enabled</Label>
                    <Switch
                      checked={editingAlert.enabled}
                      onCheckedChange={(v) => setEditingAlert({ ...editingAlert, enabled: v })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Hot Score Threshold</Label>
                    <Input
                      type="number"
                      value={editingAlert.hot_score_threshold}
                      onChange={(e) =>
                        setEditingAlert({
                          ...editingAlert,
                          hot_score_threshold: parseInt(e.target.value),
                        })
                      }
                      min={0}
                      max={100}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Alert Phone</Label>
                    <Input
                      value={editingAlert.alert_phone || ''}
                      onChange={(e) =>
                        setEditingAlert({ ...editingAlert, alert_phone: e.target.value || null })
                      }
                      placeholder="+15551234567"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Slack Webhook URL</Label>
                    <Input
                      value={editingAlert.slack_webhook_url || ''}
                      onChange={(e) =>
                        setEditingAlert({
                          ...editingAlert,
                          slack_webhook_url: e.target.value || null,
                        })
                      }
                      placeholder="https://hooks.slack.com/..."
                    />
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button variant="outline" onClick={() => setEditingAlert(null)}>
                      Cancel
                    </Button>
                    <Button onClick={handleSaveAlert} disabled={savingAlert}>
                      {savingAlert ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Automation */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Play className="h-5 w-5" />
            Automation
          </CardTitle>
          <CardDescription>Manual triggers for automated tasks</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Run Nightly Pipeline</p>
              <p className="text-sm text-muted-foreground">
                Ingest, enrich, score, and send outreach for {market}
              </p>
            </div>
            <Button onClick={handleRunPipeline} disabled={runningPipeline}>
              {runningPipeline ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Run Now
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default Settings;