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
import type { DailyRuntime, MonthlyRuntime } from '../api'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip)

const props = defineProps<{
  data: DailyRuntime[]
  monthlyData?: MonthlyRuntime[] | null
}>()

const showMonthly = ref(false)

const chartData = computed(() => {
  if (showMonthly.value && props.monthlyData) {
    return {
      labels: props.monthlyData.map(d => {
        const [year = '2000', month = '1'] = d.month.split('-')
        const date = new Date(parseInt(year), parseInt(month) - 1)
        return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
      }),
      datasets: [{
        label: 'Runtime (minutes)',
        data: props.monthlyData.map(d => d.runtime_minutes),
        backgroundColor: 'rgba(59, 130, 246, 0.5)',
        borderColor: 'rgb(59, 130, 246)',
        borderWidth: 1,
      }]
    }
  }

  return {
    labels: props.data.map(d => {
      const date = new Date(d.date)
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    }),
    datasets: [{
      label: 'Runtime (minutes)',
      data: props.data.map(d => d.runtime_minutes),
      backgroundColor: 'rgba(59, 130, 246, 0.5)',
      borderColor: 'rgb(59, 130, 246)',
      borderWidth: 1,
    }]
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
  },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.1)' },
      ticks: { color: 'rgba(255,255,255,0.6)' },
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
        {{ showMonthly ? 'Monthly Runtime (All Time)' : 'Daily Runtime Trend' }}
      </h2>
      <button
        v-if="monthlyData && monthlyData.length > 0"
        @click="showMonthly = !showMonthly"
        class="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
      >
        {{ showMonthly ? 'Last 14 Days' : 'All Time' }}
      </button>
    </div>
    <div class="h-64">
      <Bar :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
