<script lang="ts">
  // Port of features/Templates.tsx.
  import { api } from "../api";
  import { createQuery } from "../query.svelte";
  import { tr } from "../translations.svelte";
  import TemplateEditor from "./TemplateEditor.svelte";

  let { role }: { role: string } = $props();

  const templates = createQuery({ key: () => ["templates"], fn: () => api<any[]>("/settings/templates") });
  const groups = createQuery({ key: () => ["groups"], fn: () => api<any[]>("/recipient-groups") });
</script>

<p class="eyebrow">{tr("DOCUMENT TEMPLATES")}</p>
<h1>{tr("Templates")}</h1>
<p>{tr("Meeting classification selects a template. Existing previews keep their saved template and content.")}</p>
<p class="notice">{tr("A suggested recipient group never authorizes sending. Review the exact addresses before delivery.")}</p>
{#if templates.isPending}<p role="status">{tr("Loading…")}</p>{/if}
{#if templates.isError || groups.isError}<p role="alert" class="error">{String(templates.error || groups.error)}</p>{/if}
{#each templates.data ?? [] as template (template.classification)}
  <TemplateEditor {template} groups={groups.data || []} editable={role === "admin"} />
{/each}
