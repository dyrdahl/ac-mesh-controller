<script setup lang="ts">
import { ref, computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import type { TemperaturePoint, WeatherPoint } from '../api'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

const props = defineProps<{
  data: TemperaturePoint[]
  weekData?: TemperaturePoint[] | null
  weatherData?: WeatherPoint[] | null
  weatherWeekData?: WeatherPoint[] | null
}>()

const showWeek = ref(false)

const displayData = computed(() => {
  if (showWeek.value && props.weekData) {
    return props.weekData
  }
  return props.data
})

const displayWeather = computed(() => {
  if (showWeek.value && props.weatherWeekData) {
    return props.weatherWeekData
  }
  return props.weatherData || []
})

// Merge indoor and outdoor data on common timestamps
const chartData = computed(() => {
  const indoorPoints = displayData.value
  const outdoorPoints = displayWeather.value

  // Create a map of outdoor temps by hour for matching
  const outdoorByHour: Record<string, number> = {}
  for (const p of outdoorPoints) {
    const date = new Date(p.timestamp)
    const hourKey = `${date.toDateString()}-${date.getHours()}`
    outdoorByHour[hourKey] = p.outdoor_temp
  }

  // Get labels from indoor data
  const labels = indoorPoints.map(p => {
    const date = new Date(p.timestamp)
    if (showWeek.value) {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric' })
    }
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  })

  // Match outdoor temps to indoor timestamps (nearest hour)
  const outdoorTemps = indoorPoints.map(p => {
    const date = new Date(p.timestamp)
    const hourKey = `${date.toDateString()}-${date.getHours()}`
    return outdoorByHour[hourKey] ?? null
  })

  return {
    labels,
    datasets: [
      {
        label: 'Indoor',
        data: indoorPoints.map(p => p.temperature),
        borderColor: 'rgb(251, 191, 36)',
        backgroundColor: 'rgba(251, 191, 36, 0.1)',
        borderWidth: 2,
        fill: false,
        tension: 0.3,
        pointRadius: indoorPoints.map(p => p.ac_state ? 4 : 2),
        pointBackgroundColor: indoorPoints.map(p =>
          p.ac_state ? 'rgb(59, 130, 246)' : 'rgb(251, 191, 36)'
        ),
        pointBorderColor: indoorPoints.map(p =>
          p.ac_state ? 'rgb(59, 130, 246)' : 'rgb(251, 191, 36)'
        ),
      },
      {
        label: 'Outdoor',
        data: outdoorTemps,
        borderColor: 'rgb(239, 68, 68)',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        borderWidth: 2,
        borderDash: [5, 5],
        fill: false,
        tension: 0.3,
        pointRadius: 3,
        pointBackgroundColor: 'rgb(239, 68, 68)',
        spanGaps: true,
      }
    ]
  }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: {
    intersect: false,
    mode: 'index' as const,
  },
  plugins: {
    legend: {
      display: true,
      position: 'top' as const,
      labels: {
        color: 'rgba(255,255,255,0.7)',
        usePointStyle: true,
        padding: 15,
      }
    },
    tooltip: {
      callbacks: {
        label: (context: any) => {
          const value = context.parsed.y
          if (value === null) return undefined
          if (context.datasetIndex === 0) {
            const point = displayData.value[context.dataIndex]
            const status = point?.ac_state ? ' (AC On)' : ' (AC Off)'
            return `Indoor: ${value.toFixed(1)}°F${status}`
          }
          return `Outdoor: ${value.toFixed(1)}°F`
        }
      }
    }
  },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.1)' },
      ticks: {
        color: 'rgba(255,255,255,0.6)',
        maxRotation: 45,
        maxTicksLimit: showWeek.value ? 14 : 12,
      },
    },
    y: {
      grid: { color: 'rgba(255,255,255,0.1)' },
      ticks: { color: 'rgba(255,255,255,0.6)' },
      suggestedMin: 50,
      suggestedMax: 100,
    },
  },
}))
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <div class="flex justify-between items-center mb-4">
      <div>
        <h2 class="text-sm font-medium text-gray-400">
          Temperature History {{ showWeek ? '(Last 7 Days)' : '(Today)' }}
        </h2>
        <div class="flex items-center gap-4 mt-1 text-xs text-gray-500">
          <span class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-blue-500"></span>
            AC On
          </span>
          <span class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-yellow-400"></span>
            AC Off
          </span>
          <span class="flex items-center gap-1">
            <span class="w-3 h-0.5 bg-red-500" style="border-style: dashed;"></span>
            Outdoor
          </span>
        </div>
      </div>
      <button
        v-if="weekData && weekData.length > 0"
        @click="showWeek = !showWeek"
        class="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
      >
        {{ showWeek ? 'Today' : 'Last 7 Days' }}
      </button>
    </div>
    <div class="h-64">
      <Line v-if="displayData.length > 0" :data="chartData" :options="chartOptions" />
      <div v-else class="h-full flex items-center justify-center text-gray-500">
        No temperature data available
      </div>
    </div>
  </div>
</template>
