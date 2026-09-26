<script lang="ts">
  // Port of Snapshot from features/Workspace.tsx.
  import { errorMessage } from "../errors";
  import { api, snapshotExportUrl } from "../api";
  import type { Labels } from "../i18n";
  import { createQuery } from "../query.svelte";
  import { tr } from "../translations.svelte";

  let {
    snapshot: s,
    revision,
    t,
    groups,
    act,
    busy,
  }: { snapshot: any; revision: number; t: Labels; groups: any[]; act: (fn: () => Promise<unknown>) => void; busy: boolean } = $props();

  const delivery = createQuery({ key: () => ["delivery", s.id], fn: () => api<any[]>(`/snapshots/${s.id}/deliveries`), interval: 2000 });
  let groupId = $state("");
  let allowOlder = $state(false);
  const group = $derived(groups.find((g) => g.id === groupId) || groups.find((g) => g.id === s.suggested_group_id) || groups[0]);
  const stale = $derived(s.revision !== revision);
</script>

<article class="snapshot">
  <h3>{tr("Revision ")}{s.revision} <span class="badge">{tr(s.approved ? "Approved" : "Draft")}{stale ? " · " + tr("Older version") : ""}</span></h3>
  <details class="version-details">
    <summary>{tr("Version details")}</summary>
    <p>{tr("Template version")}: {s.template_revision ?? 0}</p>
    <p class="hash">SHA-256 {s.hash}</p>
  </details>
  <div class="toolbar">
    {#each ["html", "pdf", "json"] as f (f)}<a target="_blank" rel="noreferrer" href={snapshotExportUrl(s.id, f)}>{f.toUpperCase()} ↗</a>{/each}
  </div>
  <details class="delivery-options">
    <summary>{tr("Approval & delivery")}</summary>
    <label
      >{tr("Recipient group")}<select aria-label={tr("Recipient group")} value={group?.id || ""} onchange={(e) => (groupId = e.currentTarget.value)}
        >{#each groups as g (g.id)}<option value={g.id}>{g.name}</option>{/each}</select
      ></label
    >
    <p>
      {tr("Allowed recipients: ")}<strong>{group?.addresses.join(", ") || tr("No group configured")}</strong>{tr(" · group version ")}{group?.version}
    </p>
    <div class="toolbar">
      <button disabled={busy || !!s.approved || stale} onclick={() => act(() => api(`/snapshots/${s.id}/approve`, "POST", { revision }))}>{t.approve}</button><button
        disabled={busy || !s.approved || (stale && !allowOlder) || !group}
        onclick={() =>
          act(() =>
            api(`/snapshots/${s.id}/deliveries`, "POST", {
              group_id: group.id,
              group_version: group.version,
              explicitly_send_older: stale && allowOlder,
            }),
          )}>{stale ? tr("Send this older approved version") : t.send}</button
      >
    </div>
    {#if stale && s.approved}
      <label><input type="checkbox" bind:checked={allowOlder} />{tr("I choose this older approved version and the recipients shown above.")}</label>
    {/if}
    {#if stale}<p class="notice">{tr("This version is retained for history. Create a current preview to send.")}</p>{/if}
    {#each delivery.data ?? [] as d (d.id)}
      <div>
        <p role="status">{tr("Local delivery: ")}{tr(d.state.replaceAll("_", " "))} {d.error ? errorMessage(d.error) : ""}</p>
        <p class="caption">{tr("Recipients for this delivery")}: {JSON.parse(d.addresses).join(", ")}</p>
        {#if d.state === "failed"}
          <button
            disabled={busy || (stale && !allowOlder)}
            onclick={() => act(() => api(`/deliveries/${d.id}/retry`, "POST", { explicitly_send_older: stale && allowOlder }))}
            >{tr("Retry this failed delivery")}</button
          >
        {/if}
        {#if d.state === "uncertain"}<p class="notice">{tr("Delivery is uncertain. Check the mail server; this attempt cannot be retried automatically.")}</p>{/if}
      </div>
    {/each}
  </details>
</article>
