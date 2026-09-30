<script setup>
import { useData } from 'vitepress';
const { frontmatter, theme, lang } = useData();
const formatDate = value => new Intl.DateTimeFormat(lang.value, { dateStyle: 'medium' }).format(new Date(value));
</script>
<template>
  <aside v-if="frontmatter.source" class="source-info" :aria-label="theme.sourceInfo.label">
    <p v-if="frontmatter.archive">{{ theme.sourceInfo.archive }}</p>
    <a :href="frontmatter.source" target="_blank" rel="noopener noreferrer">{{ theme.sourceInfo.link }}</a>
    <span v-if="frontmatter.sourceModified">{{ theme.sourceInfo.modified }}</span>
    <span v-else-if="frontmatter.sourceUpdated">{{ theme.sourceInfo.updated }} {{ formatDate(frontmatter.sourceUpdated) }}</span>
  </aside>
</template>
