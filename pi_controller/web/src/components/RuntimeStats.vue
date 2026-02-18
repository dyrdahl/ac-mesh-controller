<script setup lang="ts">
import type { RuntimeStats } from '../api'

defineProps<{
  title: string
  stats: RuntimeStats
}>()

function formatRuntime(minutes: number): string {
  if (minutes < 60) {
    return `${Math.round(minutes)}m`
  }
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-sm font-medium text-gray-400 mb-4">{{ title }}</h2>

    <div class="text-3xl font-light text-white mb-2">
      {{ formatRuntime(stats.total_runtime_minutes) }}
    </div>

    <div class="space-y-2 text-sm">
      <div class="flex justify-between">
        <span class="text-gray-400">Cycles</span>
        <span class="text-gray-200">{{ stats.cycle_count }}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-400">Avg Cycle</span>
        <span class="text-gray-200">{{ formatRuntime(stats.avg_cycle_minutes) }}</span>
      </div>
    </div>
  </div>
</template>
