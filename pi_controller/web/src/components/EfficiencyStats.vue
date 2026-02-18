<script setup lang="ts">
import type { EfficiencyStats } from '../api'

defineProps<{
  stats: EfficiencyStats
}>()
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-sm font-medium text-gray-400 mb-4">Efficiency Stats (Last 7 Days)</h2>

    <div class="grid grid-cols-2 gap-6">
      <div>
        <div class="text-xs text-gray-500 uppercase mb-1">Cooling Rate</div>
        <div class="text-2xl font-light text-blue-400">
          <template v-if="stats.avg_cooling_rate !== null">
            {{ stats.avg_cooling_rate }}°/hr
          </template>
          <template v-else>
            <span class="text-gray-500">--</span>
          </template>
        </div>
        <div class="text-xs text-gray-500 mt-1">
          {{ stats.cooling_samples }} samples
        </div>
      </div>

      <div>
        <div class="text-xs text-gray-500 uppercase mb-1">Heat Buildup</div>
        <div class="text-2xl font-light text-orange-400">
          <template v-if="stats.avg_heat_buildup_rate !== null">
            {{ stats.avg_heat_buildup_rate }}°/hr
          </template>
          <template v-else>
            <span class="text-gray-500">--</span>
          </template>
        </div>
        <div class="text-xs text-gray-500 mt-1">
          {{ stats.heating_samples }} samples
        </div>
      </div>
    </div>

    <p class="text-xs text-gray-500 mt-4">
      Cooling rate: how fast temp drops when AC is on.
      Heat buildup: how fast temp rises when AC is off.
    </p>
  </div>
</template>
