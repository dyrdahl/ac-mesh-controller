<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api, type ACSettings, type LiveStatus } from '../api'

const props = defineProps<{
  settings: ACSettings
  live: LiveStatus | null
}>()

const emit = defineEmits<{
  refresh: []
}>()

const loading = ref<string | null>(null)
const error = ref<string | null>(null)
const showThresholdModal = ref(false)
const showBrightnessModal = ref(false)
const newMaxTemp = ref(78)
const newMinTemp = ref(72)
const brightness = ref(50)

// Optimistic state overrides (null = use props)
const optimisticAcState = ref<boolean | null>(null)
const optimisticAcAllowed = ref<boolean | null>(null)

// Use optimistic state if set, otherwise fall back to props
const acState = computed(() => optimisticAcState.value ?? props.live?.ac_state ?? false)
const acAllowed = computed(() => optimisticAcAllowed.value ?? props.live?.ac_allowed ?? false)

// Clear optimistic state when we get fresh data from server
// The server state is authoritative - optimistic is just for immediate feedback
watch(() => props.live?.ac_state, () => {
  optimisticAcState.value = null
})

watch(() => props.live?.ac_allowed, () => {
  optimisticAcAllowed.value = null
})

async function handleAction(action: string, fn: () => Promise<unknown>) {
  loading.value = action
  error.value = null
  try {
    await fn()
    // Don't emit refresh - let regular polling handle it
    // This avoids race conditions with stale data
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Action failed'
    // Reset optimistic state on error
    optimisticAcState.value = null
    optimisticAcAllowed.value = null
  } finally {
    loading.value = null
  }
}

function toggleAC() {
  const newState = !acState.value
  optimisticAcState.value = newState  // Immediately show new state
  handleAction('power', () => newState ? api.turnOn() : api.turnOff())
}

function togglePermission() {
  const newState = !acAllowed.value
  optimisticAcAllowed.value = newState  // Immediately show new state
  handleAction('permission', () => api.togglePermission())
}

function resetNode() {
  handleAction('reset', () => api.resetNode())
}

function openThresholdModal() {
  newMaxTemp.value = props.settings.max_temp
  newMinTemp.value = props.settings.min_temp
  showThresholdModal.value = true
}

function saveThresholds() {
  if (newMaxTemp.value <= newMinTemp.value) {
    error.value = 'Max must be greater than min'
    return
  }
  handleAction('thresholds', async () => {
    await api.setThresholds(newMaxTemp.value, newMinTemp.value)
    showThresholdModal.value = false
  })
}

function saveBrightness() {
  handleAction('brightness', async () => {
    await api.setBrightness(brightness.value)
    showBrightnessModal.value = false
  })
}
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-sm font-medium text-gray-400 mb-4">Controls</h2>

    <div v-if="error" class="bg-red-900/50 text-red-200 text-sm p-2 rounded mb-4">
      {{ error }}
    </div>

    <div class="grid grid-cols-2 gap-3">
      <!-- AC Power Toggle -->
      <button
        @click="toggleAC"
        :disabled="loading === 'power' || (!acAllowed && !acState)"
        :class="[
          'p-3 rounded-lg font-medium transition-colors',
          acState
            ? 'bg-green-600 hover:bg-green-700 text-white'
            : (!acAllowed ? 'bg-gray-600 text-gray-400 cursor-not-allowed' : 'bg-gray-700 hover:bg-gray-600 text-gray-200')
        ]"
      >
        {{ acState ? 'Turn OFF' : 'Turn ON' }}
      </button>

      <!-- AC Permission Toggle -->
      <button
        @click="togglePermission"
        :disabled="loading === 'permission'"
        :class="[
          'p-3 rounded-lg font-medium transition-colors',
          acAllowed
            ? 'bg-blue-600 hover:bg-blue-700 text-white'
            : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
        ]"
      >
        {{ acAllowed ? 'Disable AC' : 'Enable AC' }}
      </button>

      <!-- Thresholds -->
      <button
        @click="openThresholdModal"
        :disabled="loading !== null"
        class="p-3 rounded-lg font-medium bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors"
      >
        Set Temps
      </button>

      <!-- Brightness -->
      <button
        @click="showBrightnessModal = true"
        :disabled="loading !== null"
        class="p-3 rounded-lg font-medium bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors"
      >
        Brightness
      </button>

      <!-- Reset Node -->
      <button
        @click="resetNode"
        :disabled="loading !== null"
        class="col-span-2 p-3 rounded-lg font-medium bg-red-900/50 hover:bg-red-900 text-red-200 transition-colors"
      >
        {{ loading === 'reset' ? 'Resetting...' : 'Reset AC Node' }}
      </button>
    </div>

    <!-- Threshold Modal -->
    <div
      v-if="showThresholdModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="showThresholdModal = false"
    >
      <div class="bg-gray-800 rounded-lg p-6 w-80 border border-gray-600">
        <h3 class="text-lg font-medium text-white mb-4">Set Temperature Thresholds</h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Max Temp (AC turns on)</label>
            <input
              v-model.number="newMaxTemp"
              type="number"
              min="50"
              max="100"
              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white"
            />
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-1">Min Temp (AC turns off)</label>
            <input
              v-model.number="newMinTemp"
              type="number"
              min="50"
              max="100"
              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white"
            />
          </div>
        </div>

        <div class="flex gap-3 mt-6">
          <button
            @click="showThresholdModal = false"
            class="flex-1 p-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-200"
          >
            Cancel
          </button>
          <button
            @click="saveThresholds"
            :disabled="loading !== null"
            class="flex-1 p-2 rounded bg-blue-600 hover:bg-blue-700 text-white"
          >
            {{ loading === 'thresholds' ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Brightness Modal -->
    <div
      v-if="showBrightnessModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="showBrightnessModal = false"
    >
      <div class="bg-gray-800 rounded-lg p-6 w-80 border border-gray-600">
        <h3 class="text-lg font-medium text-white mb-4">LED Brightness</h3>

        <div class="space-y-4">
          <input
            v-model.number="brightness"
            type="range"
            min="0"
            max="100"
            class="w-full"
          />
          <div class="text-center text-2xl text-white">{{ brightness }}%</div>
        </div>

        <div class="flex gap-3 mt-6">
          <button
            @click="showBrightnessModal = false"
            class="flex-1 p-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-200"
          >
            Cancel
          </button>
          <button
            @click="saveBrightness"
            :disabled="loading !== null"
            class="flex-1 p-2 rounded bg-blue-600 hover:bg-blue-700 text-white"
          >
            {{ loading === 'brightness' ? 'Saving...' : 'Set' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
