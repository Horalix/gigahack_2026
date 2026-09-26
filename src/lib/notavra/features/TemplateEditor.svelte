<script lang="ts">
  // Port of TemplateEditor from features/Templates.tsx.
  import { api } from "../api";
  import { invalidateQueries } from "../query.svelte";
  import { tr } from "../translations.svelte";

  type Template = { classification: string; version: number; titles: Record<string, string>; introduction?: string; recipient_group_id?: string | null };
  type Group = { id: string; name: string; addresses: string[]; version: number };

  let { template, groups, editable }: { template: Template; groups: Group[]; editable: boolean } = $props();

  // Captured once, like the useState initialiser it replaces.
  const initial = () => JSON.parse(JSON.stringify(template)) as Template;
  let draft = $state(initial());
  let busy = $state(false);
  let error = $state("");
  let notice = $state("");

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = "";
    notice = "";
    try {
      const saved = await api<Template>("/settings/templates/" + encodeURIComponent(draft.classification), "PUT", {
        version: draft.version,
        titles: draft.titles,
        introduction: draft.introduction,
        recipient_group_id: draft.recipient_group_id,
      });
      draft = saved;
      await invalidateQueries();
      notice = tr("Saved on this computer.");
    } catch (failure) {
      error = failure instanceof Error ? failure.message : tr("The request failed. Check the form, refresh, and try again.");
    } finally {
      busy = false;
    }
  }

  const headings = ["English document heading", "Romanian document heading", "Russian document heading"];
</script>

<section class="card">
  <h2>{tr(template.classification)} <span class="badge">{tr("Version")} {draft.version}</span></h2>
  <p class="caption">{tr("Required decisions, actions, unresolved matters and amendment history are always included.")}</p>
  {#if error}<p role="alert" class="error">{error}</p>{/if}
  {#if notice}<p role="status">{notice}</p>{/if}
  {#if template.version !== draft.version}
    <p class="notice">
      {tr("A newer template is available. Your edits have been kept.")}
      <button
        class="secondary"
        onclick={() => {
          draft = initial();
          error = "";
        }}>{tr("Replace my edits with saved template")}</button
      >
    </p>
  {/if}
  <form onsubmit={save}>
    <fieldset disabled={busy} class="mutation-controls">
      {#each ["en", "ro", "ru"] as language, index (language)}
        <label
          >{tr(headings[index])}
          <input readonly={!editable} maxlength="120" bind:value={draft.titles[language]} placeholder={tr("Leave blank for the standard heading")} />
        </label>
      {/each}
      <label>{tr("Document introduction")}<textarea readonly={!editable} maxlength="1000" rows="3" bind:value={draft.introduction}></textarea></label>
      <p class="caption">{tr("Plain text only. Enter approved organizational wording; it is not translated automatically.")}</p>
      <label
        >{tr("Suggested recipient group")}<select
          aria-label={tr("Suggested recipient group")}
          disabled={!editable}
          value={draft.recipient_group_id || ""}
          onchange={(e) => (draft.recipient_group_id = e.currentTarget.value || null)}
          ><option value="">{tr("No suggested group")}</option>{#each groups as group (group.id)}<option value={group.id}>{group.name}</option>{/each}</select
        ></label
      >
      {#if editable}<button disabled={busy}>{tr(busy ? "Saving…" : "Save template")}</button>{:else}<p>{tr("Admin access required to edit templates.")}</p>{/if}
    </fieldset>
  </form>
</section>
