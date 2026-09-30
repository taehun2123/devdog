<script setup>
import { ref, onMounted, watch, useId } from 'vue';
import { useData } from 'vitepress';
const props = defineProps({ code: { type: String, required: true } });
const { isDark, theme } = useData();
const container = ref(null);
const error = ref('');
const ready = ref(false);
const id = 'diagram-' + useId().replace(/[^a-zA-Z0-9-]/g, '');
let revision = 0;
async function render() {
  const current = ++revision;
  try {
    const { default: mermaid } = await import('mermaid');
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: isDark.value ? 'dark' : 'default', suppressErrorRendering: true });
    const { svg } = await mermaid.render(`${id}-${current}`, decodeURIComponent(props.code));
    if (current === revision && container.value) { container.value.innerHTML = svg; ready.value = true; error.value = ''; }
  } catch {
    if (current === revision) error.value = theme.value.mermaid.error;
  }
}
onMounted(render);
watch([() => props.code, isDark], render);
</script>
<template>
  <figure class="mermaid-figure" :aria-label="theme.mermaid.label">
    <div ref="container" class="mermaid-output"></div>
    <p v-if="error" role="status">{{ error }}</p>
    <details :open="!ready"><summary>{{ theme.mermaid.source }}</summary><pre>{{ decodeURIComponent(code) }}</pre></details>
  </figure>
</template>
