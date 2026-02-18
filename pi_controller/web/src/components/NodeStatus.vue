<script setup lang="ts">
import type { NodeStatus } from '../api'

defineProps<{
  nodes: NodeStatus[]
}>()

function formatLastSeen(timestamp: string | null): string {
  if (!timestamp) return 'Never'
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleDateString()
}
</script>

<template>
  <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
    <h2 class="text-sm font-medium text-gray-400 mb-4">Mesh Network Nodes</h2>

    <div class="space-y-3">
      <div
        v-for="node in nodes"
        :key="node.node_id"
        class="flex items-center justify-between py-2 border-b border-gray-700 last:border-0"
      >
        <div class="flex items-center gap-3">
          <div
            :class="[
              'w-2 h-2 rounded-full',
              node.status === 'online' ? 'bg-green-500' : 'bg-gray-500'
            ]"
          />
          <div>
            <div class="text-gray-200">{{ node.name }}</div>
            <div class="text-xs text-gray-500">Node {{ node.node_id }}</div>
          </div>
        </div>
        <div class="text-right">
          <div
            :class="[
              'text-sm',
              node.status === 'online' ? 'text-green-400' : 'text-gray-500'
            ]"
          >
            {{ node.status }}
          </div>
          <div class="text-xs text-gray-500">
            {{ formatLastSeen(node.last_seen) }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="nodes.length === 0" class="text-gray-500 text-center py-4">
      No nodes configured
    </div>
  </div>
</template>
