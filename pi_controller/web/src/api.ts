/**
 * API client for AC Dashboard
 */

const API_BASE = import.meta.env.VITE_API_URL ?? '';

async function fetchJson<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  return response.json();
}

async function postJson<T>(endpoint: string, body?: object): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  return response.json();
}

// Response types for control actions
export interface ControlResponse {
  success: boolean;
  message?: string;
}

// Types
export interface ACStatus {
  ac_state: boolean;
  temperature: number | null;
  timestamp: string | null;
}

export interface ACSettings {
  max_temp: number;
  min_temp: number;
  ac_allowed: boolean;
}

export interface NodeStatus {
  node_id: number;
  name: string;
  status: string;
  last_seen: string | null;
  last_message: string | null;
}

export interface RuntimeStats {
  total_runtime_minutes: number;
  cycle_count: number;
  avg_cycle_minutes: number;
}

export interface DailyRuntime {
  date: string;
  runtime_minutes: number;
}

export interface MonthlyRuntime {
  month: string;
  runtime_minutes: number;
}

export interface TemperaturePoint {
  timestamp: string;
  temperature: number;
  ac_state: boolean;
}

export interface WeatherPoint {
  timestamp: string;
  outdoor_temp: number;
  humidity: number | null;
  conditions: string | null;
}

export interface CurrentWeather {
  timestamp: string | null;
  outdoor_temp: number | null;
  humidity: number | null;
  conditions: string | null;
}

export interface HourlyUsage {
  hour: number;
  total_minutes: number;
}

export interface EfficiencyStats {
  avg_cooling_rate: number | null;
  avg_heat_buildup_rate: number | null;
  cooling_samples: number;
  heating_samples: number;
}

export interface CostByPeriod {
  on_peak: { cost: number; minutes: number };
  off_peak: { cost: number; minutes: number };
  super_off_peak: { cost: number; minutes: number };
}

export interface CostStats {
  total_cost: number;
  total_runtime_minutes: number;
  cost_by_period: CostByPeriod;
}

export interface RateSchedule {
  on_peak: string;
  off_peak: string;
  super_off_peak: string;
}

export interface CurrentRate {
  season: string;
  period: string;
  rate: number;
  cost_per_hour: number;
  is_weekend_or_holiday: boolean;
  schedule: RateSchedule;
}

export interface AnalyticsSummary {
  today: RuntimeStats;
  week: RuntimeStats;
  month: RuntimeStats;
  daily_trend: DailyRuntime[];
  monthly_all_time: MonthlyRuntime[];
  hourly: HourlyUsage[];
  hourly_all_time: HourlyUsage[];
  efficiency: EfficiencyStats;
  cost_today: CostStats;
  cost_week: CostStats;
  cost_month: CostStats;
  cost_all_time: CostStats;
  current_rate: CurrentRate;
  temperature_history: TemperaturePoint[];
  temperature_history_week: TemperaturePoint[];
  weather_history: WeatherPoint[];
  weather_history_week: WeatherPoint[];
  current_weather: CurrentWeather | null;
}

export interface DashboardData {
  status: ACStatus;
  settings: ACSettings;
  nodes: NodeStatus[];
}

export interface LiveStatus {
  temperature: string | null;
  ac_state: boolean | null;
  ac_allowed: boolean | null;
}

// API functions
export const api = {
  // AC status endpoints
  getStatus: () => fetchJson<ACStatus>('/ac/status'),
  getLive: () => fetchJson<LiveStatus>('/ac/live'),
  getSettings: () => fetchJson<ACSettings>('/ac/settings'),
  getNodes: () => fetchJson<NodeStatus[]>('/ac/nodes'),
  getDashboard: () => fetchJson<DashboardData>('/ac/dashboard'),

  // AC control endpoints
  turnOn: () => postJson<ControlResponse>('/ac/power/on'),
  turnOff: () => postJson<ControlResponse>('/ac/power/off'),
  setThresholds: (max_temp: number, min_temp: number) =>
    postJson<ControlResponse>('/ac/thresholds', { max_temp, min_temp }),
  togglePermission: () => postJson<ControlResponse>('/ac/permission/toggle'),
  resetNode: () => postJson<ControlResponse>('/ac/reset'),
  setBrightness: (level: number) =>
    postJson<ControlResponse>('/ac/brightness', { level }),

  // Analytics endpoints
  getRuntime: (period: 'day' | 'week' | 'month') =>
    fetchJson<RuntimeStats>(`/analytics/runtime?period=${period}`),
  getDailyRuntime: (days: number = 14) =>
    fetchJson<DailyRuntime[]>(`/analytics/daily?days=${days}`),
  getHourlyUsage: (days: number = 7) =>
    fetchJson<HourlyUsage[]>(`/analytics/hourly?days=${days}`),
  getEfficiency: (days: number = 7) =>
    fetchJson<EfficiencyStats>(`/analytics/efficiency?days=${days}`),
  getAnalyticsSummary: () => fetchJson<AnalyticsSummary>('/analytics/summary'),
};
