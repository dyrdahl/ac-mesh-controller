<script setup lang="ts">
import { ref, computed } from 'vue'
import type { CostStats, CurrentRate } from '../api'

const props = defineProps<{
  title: string
  stats: CostStats
  allTimeStats?: CostStats | null
  currentRate?: CurrentRate
  toggleable?: boolean
}>()

const showAllTime = ref(false)

const displayStats = computed(() => {
  if (showAllTime.value && props.allTimeStats) {
    return props.allTimeStats
  }
  return props.stats
})

const displayTitle = computed(() => {
  if (showAllTime.value && props.toggleable) {
    return props.title.replace('This Month', 'All Time').replace('This Week', 'All Time')
  }
  return props.title
})

function formatCost(cost: number): string {
  return `$${cost.toFixed(2)}`
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) {
    return `${Math.round(minutes)}m`
  }
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}

function formatPeriodName(period: string): string {
  return {
    on_peak: 'On-Peak',
    off_peak: 'Off-Peak',
    super_off_peak: 'Super Off-Peak',
  }[period] || period
}
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-sm font-medium text-gray-400">{{ displayTitle }}</h2>
      <button
        v-if="toggleable && allTimeStats"
        @click="showAllTime = !showAllTime"
        class="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
      >
        {{ showAllTime ? 'This Month' : 'All Time' }}
      </button>
    </div>

    <div class="text-center mb-4">
      <span class="text-4xl font-light text-green-400">
        {{ formatCost(displayStats.total_cost) }}
      </span>
    </div>

    <div class="text-center text-sm text-gray-400 mb-4">
      {{ formatMinutes(displayStats.total_runtime_minutes) }} runtime
    </div>

    <!-- Cost by period breakdown -->
    <div class="space-y-2 text-sm">
      <div
        v-for="(data, period) in displayStats.cost_by_period"
        :key="period"
        class="flex justify-between items-center"
      >
        <span class="text-gray-400">{{ formatPeriodName(period) }}</span>
        <span class="text-gray-200">
          {{ formatCost(data.cost) }}
          <span class="text-gray-500 text-xs">({{ formatMinutes(data.minutes) }})</span>
        </span>
      </div>
    </div>

    <!-- Current rate info (only shown if provided) -->
    <div v-if="currentRate" class="mt-4 pt-4 border-t border-gray-700">
      <div class="text-xs text-gray-500 mb-1">Current Rate</div>
      <div class="flex justify-between items-center">
        <span
          :class="[
            'text-sm font-medium',
            currentRate.period === 'On-Peak' ? 'text-red-400' :
            currentRate.period === 'Off-Peak' ? 'text-yellow-400' :
            'text-green-400'
          ]"
        >
          {{ currentRate.period }}
        </span>
        <span class="text-gray-200">
          ${{ currentRate.cost_per_hour.toFixed(2) }}/hr
        </span>
      </div>
      <div class="text-xs text-gray-500 mt-1">
        {{ currentRate.season === 'summer' ? 'Summer' : 'Winter' }} rates
        <span v-if="currentRate.is_weekend_or_holiday"> (weekend/holiday)</span>
      </div>

      <!-- Rate schedule times -->
      <div v-if="currentRate.schedule" class="mt-3 pt-3 border-t border-gray-700 space-y-1 text-xs">
        <div class="flex justify-between">
          <span class="text-red-400">On-Peak</span>
          <span class="text-gray-400">{{ currentRate.schedule.on_peak }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-yellow-400">Off-Peak</span>
          <span class="text-gray-400">{{ currentRate.schedule.off_peak }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-green-400">Super Off-Peak</span>
          <span class="text-gray-400">{{ currentRate.schedule.super_off_peak }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
