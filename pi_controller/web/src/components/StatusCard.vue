<script setup lang="ts">
import type { ACSettings, CurrentWeather } from '../api'

defineProps<{
  acState: boolean
  temperature: number | string | null
  settings: ACSettings
  acAllowed?: boolean
  weather?: CurrentWeather | null
}>()

function formatCondition(condition: string | null): string {
  if (!condition) return ''
  return condition.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-sm font-medium text-gray-400 mb-4">Current Status</h2>

    <div class="flex items-center justify-between mb-4">
      <span class="text-gray-300">AC</span>
      <span
        :class="[
          'px-3 py-1 rounded-full text-sm font-medium',
          acState
            ? 'bg-green-500/20 text-green-400'
            : 'bg-gray-600/20 text-gray-400'
        ]"
      >
        {{ acState ? 'ON' : 'OFF' }}
      </span>
    </div>

    <div class="flex justify-between items-end mb-4">
      <div class="text-center flex-1">
        <div class="text-xs text-gray-500 mb-1">Indoor</div>
        <span class="text-4xl font-light text-white">
          {{ temperature ?? '--' }}
        </span>
        <span class="text-xl text-gray-400">°F</span>
      </div>
      <div v-if="weather?.outdoor_temp" class="text-center flex-1">
        <div class="text-xs text-gray-500 mb-1">Outdoor</div>
        <span class="text-4xl font-light text-red-400">
          {{ Math.round(weather.outdoor_temp) }}
        </span>
        <span class="text-xl text-gray-400">°F</span>
      </div>
    </div>

    <div v-if="weather?.conditions" class="text-center text-xs text-gray-500 mb-3">
      {{ formatCondition(weather.conditions) }}
      <span v-if="weather.humidity"> · {{ weather.humidity }}% humidity</span>
    </div>

    <div class="flex justify-between text-sm text-gray-400">
      <span>Min: {{ settings.min_temp }}°</span>
      <span>Max: {{ settings.max_temp }}°</span>
    </div>

    <div class="mt-3 pt-3 border-t border-gray-700">
      <span
        :class="[
          'text-xs',
          (acAllowed ?? settings.ac_allowed) ? 'text-green-400' : 'text-red-400'
        ]"
      >
        {{ (acAllowed ?? settings.ac_allowed) ? 'AC Enabled' : 'AC Disabled' }}
      </span>
    </div>
  </div>
</template>
