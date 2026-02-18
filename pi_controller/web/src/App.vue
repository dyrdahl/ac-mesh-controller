<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, type DashboardData, type AnalyticsSummary, type LiveStatus } from './api'
import StatusCard from './components/StatusCard.vue'
import ControlPanel from './components/ControlPanel.vue'
import RuntimeStats from './components/RuntimeStats.vue'
import CostStats from './components/CostStats.vue'
import DailyChart from './components/DailyChart.vue'
import HourlyChart from './components/HourlyChart.vue'
import EfficiencyStats from './components/EfficiencyStats.vue'
import NodeStatus from './components/NodeStatus.vue'
import TemperatureChart from './components/TemperatureChart.vue'

const dashboard = ref<DashboardData | null>(null)
const analytics = ref<AnalyticsSummary | null>(null)
const live = ref<LiveStatus | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

let refreshInterval: number | null = null
let liveInterval: number | null = null

async function fetchData() {
  try {
    const [dashData, analyticsData, liveData] = await Promise.all([
      api.getDashboard(),
      api.getAnalyticsSummary(),
      api.getLive(),
    ])
    dashboard.value = dashData
    analytics.value = analyticsData
    live.value = liveData
    error.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to fetch data'
  } finally {
    loading.value = false
  }
}

async function fetchLive() {
  try {
    live.value = await api.getLive()
  } catch (e) {
    // Silently fail on live updates
  }
}

function handleRefresh() {
  fetchData()
}

onMounted(() => {
  fetchData()
  // Full refresh every 30 seconds
  refreshInterval = window.setInterval(fetchData, 30000)
  // Live status every 5 seconds
  liveInterval = window.setInterval(fetchLive, 5000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
  if (liveInterval) clearInterval(liveInterval)
})
</script>

<template>
  <div class="min-h-screen bg-gray-900 p-4 md:p-8">
    <header class="mb-8">
      <h1 class="text-3xl font-bold text-white">AC Dashboard</h1>
      <p class="text-gray-400">Home Climate Control Analytics</p>
    </header>

    <div v-if="loading" class="text-center py-12">
      <div class="text-gray-400">Loading...</div>
    </div>

    <div v-else-if="error" class="bg-red-900/50 border border-red-500 rounded-lg p-4 mb-4">
      <p class="text-red-200">{{ error }}</p>
      <button @click="fetchData" class="mt-2 text-red-400 hover:text-red-300">
        Retry
      </button>
    </div>

    <template v-else-if="dashboard && analytics">
      <!-- Status & Controls Row -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <StatusCard
          :ac-state="live?.ac_state ?? dashboard.status.ac_state"
          :temperature="live?.temperature ?? dashboard.status.temperature"
          :settings="dashboard.settings"
          :ac-allowed="live?.ac_allowed ?? dashboard.settings.ac_allowed"
          :weather="analytics.current_weather"
        />
        <ControlPanel
          :settings="dashboard.settings"
          :live="live"
          @refresh="handleRefresh"
        />
        <CostStats
          title="Cost Today"
          :stats="analytics.cost_today"
          :current-rate="analytics.current_rate"
        />
      </div>

      <!-- Runtime Stats Row -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <RuntimeStats
          title="Today"
          :stats="analytics.today"
        />
        <RuntimeStats
          title="This Week"
          :stats="analytics.week"
        />
        <RuntimeStats
          title="This Month"
          :stats="analytics.month"
        />
      </div>

      <!-- Cost Stats Row -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <CostStats
          title="Cost This Week"
          :stats="analytics.cost_week"
        />
        <CostStats
          title="Cost This Month"
          :stats="analytics.cost_month"
          :all-time-stats="analytics.cost_all_time"
          :toggleable="true"
        />
      </div>

      <!-- Charts Row -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <DailyChart :data="analytics.daily_trend" :monthly-data="analytics.monthly_all_time" />
        <HourlyChart :data="analytics.hourly" :all-time-data="analytics.hourly_all_time" />
      </div>

      <!-- Temperature History -->
      <div class="mb-6">
        <TemperatureChart
          :data="analytics.temperature_history"
          :week-data="analytics.temperature_history_week"
          :weather-data="analytics.weather_history"
          :weather-week-data="analytics.weather_history_week"
        />
      </div>

      <!-- Bottom Row -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <EfficiencyStats :stats="analytics.efficiency" />
        <NodeStatus :nodes="dashboard.nodes" />
      </div>
    </template>
  </div>
</template>
