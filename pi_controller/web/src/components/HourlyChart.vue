<script setup lang="ts">
import { ref, computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
} from 'chart.js'
import type { HourlyUsage } from '../api'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip)

const props = defineProps<{
  data: HourlyUsage[]
  allTimeData?: HourlyUsage[] | null
}>()

const showAllTime = ref(false)

const displayData = computed(() => {
  if (showAllTime.value && props.allTimeData) {
    return props.allTimeData
  }
  return props.data
})

const chartData = computed(() => ({
  labels: displayData.value.map(d => {
    const hour = d.hour
    if (hour === 0) return '12am'
    if (hour === 12) return '12pm'
    return hour > 12 ? `${hour - 12}pm` : `${hour}am`
  }),
  datasets: [{
    label: 'Usage (minutes)',
    data: displayData.value.map(d => d.total_minutes),
    backgroundColor: 'rgba(16, 185, 129, 0.5)',
    borderColor: 'rgb(16, 185, 129)',
    borderWidth: 1,
  }]
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
  },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.1)' },
      ticks: { color: 'rgba(255,255,255,0.6)', maxRotation: 45 },
    },
    y: {
      grid: { color: 'rgba(255,255,255,0.1)' },
      ticks: { color: 'rgba(255,255,255,0.6)' },
    },
  },
}
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-sm font-medium text-gray-400">
        Peak Usage Hours {{ showAllTime ? '(All Time)' : '(Last 7 Days)' }}
      </h2>
      <button
        v-if="allTimeData"
        @click="showAllTime = !showAllTime"
        class="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
      >
        {{ showAllTime ? 'Last 7 Days' : 'All Time' }}
      </button>
    </div>
    <div class="h-64">
      <Bar :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
