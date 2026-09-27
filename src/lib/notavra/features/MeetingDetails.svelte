<script lang="ts">
  // Port of MeetingDetails from features/MeetingDetails.tsx.
  import { initialValue } from "../actions";
  import { api, type Meeting } from "../api";
  import { createQuery } from "../query.svelte";
  import { tr } from "../translations.svelte";

  let {
    meeting: m,
    role,
    busy,
    act,
    back,
  }: { meeting: Meeting; role: string; busy: boolean; act: (fn: () => Promise<unknown>) => void; back: () => void } = $props();

  const accounts = createQuery({ key: () => ["accounts"], fn: () => api<any[]>("/accounts"), enabled: () => role === "admin" });
  let confirmation = $state("");
  const processing = $derived(m.jobs?.some((job) => ["queued", "running"].includes(job.state)));

  function saveDetails(e: SubmitEvent) {
    e.preventDefault();
    const f = new FormData(e.currentTarget as HTMLFormElement);
    act(() =>
      api(`/meetings/${m.id}`, "PATCH", {
        revision: m.revision,
        title: f.get("title"),
        date: f.get("date") || null,
        time: f.get("time"),
        notes: f.get("notes"),
        timezone: f.get("timezone"),
        language: f.get("language"),
        classification: f.get("classification"),
        participants: String(f.get("participants"))
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    );
  }

  function grant(e: SubmitEvent) {
    e.preventDefault();
    const f = new FormData(e.currentTarget as HTMLFormElement);
    act(() => api(`/meetings/${m.id}/members`, "POST", { user_id: f.get("account") }));
  }
</script>

{#if role !== "viewer"}
  <details class="card">
    <summary>{tr("Meeting details and access")}</summary>
    {#if processing}<p class="notice">{tr("Cancel or finish processing before changing meeting details.")}</p>{/if}
    {#key m.revision}
      <form onsubmit={saveDetails}>
        <fieldset disabled={busy || processing}>
          <label>{tr("Title")}<input name="title" value={m.title} required maxlength="200" /></label>
          <div class="formrow">
            <label>{tr("Date")}<input name="date" type="date" value={m.date} /></label><label
              >{tr("Timezone")}<input name="timezone" value={m.timezone} /></label
            >
          </div>
          <label>{tr("Time")}<input name="time" type="time" value={m.time} /></label><label
            >{tr("Meeting notes · draft")}<textarea name="notes" value={m.notes} rows="8" maxlength="20000"></textarea></label
          >
          <p class="caption">{tr("Leave date and timezone blank if unknown. Relative dates will need review.")}</p>
          <div class="formrow">
            <label
              >{tr("Minutes language")}<select name="language" use:initialValue={m.language}
                ><option value="en">English</option><option value="ro">Română</option><option value="ru">Русский</option></select
              ></label
            ><label
              >{tr("Classification")}<select name="classification" use:initialValue={m.classification}
                >{#each ["Administrative", "Executive", "Medical"] as v (v)}<option value={v}>{tr(v)}</option>{/each}</select
              ></label
            >
          </div>
          <label>{tr("Participants, one per line")}<textarea name="participants" value={m.participants?.map((p) => p.name).join("\n")} rows="3"></textarea></label>
          <p class="caption">{tr("Changing the date or timezone requires another review. Previous approved versions remain in history.")}</p>
          <button>{tr("Save meeting details")}</button>
        </fieldset>
      </form>
    {/key}
    {#if role === "admin"}
      <form onsubmit={grant}>
        <h3>{tr("Grant meeting access")}</h3>
        {#if accounts.isError}
          <p role="alert">{String(accounts.error)}</p>
        {:else}
          <label
            >{tr("Local account")}<select name="account" required aria-label={tr("Local account")}
              ><option value="">{tr("Choose an account")}</option>{#each accounts.data ?? [] as a (a.id)}<option value={a.id}>{a.name} · {tr(a.role)}</option>{/each}</select
            ></label
          >
        {/if}
        <p class="caption">{tr("Admin role does not grant access to other people's meetings.")}</p>
        <button disabled={busy || !accounts.data?.length}>{tr("Grant access")}</button>
      </form>
      <details>
        <summary>{tr("Delete this meeting")}</summary>
        <p class="notice">{tr("Deletes recordings, transcripts, reviews and exports. This cannot be undone. Type the exact meeting title to confirm.")}</p>
        <label>{tr("Confirm meeting title")}<input bind:value={confirmation} autocomplete="off" /></label>
        <button
          class="secondary"
          disabled={busy || processing || confirmation !== m.title}
          onclick={() =>
            act(async () => {
              await api(`/meetings/${m.id}`, "DELETE", { revision: m.revision, confirm_title: confirmation });
              back();
            })}>{tr("Delete this meeting")}</button
        >
      </details>
    {/if}
  </details>
{/if}
