<script lang="ts">
  // Start a meeting in one action: pick the type, then record or upload.
  // Title, date, time, timezone and language are filled in; the optional
  // details only need opening when the defaults are wrong.
  import { api, type Lang, type Meeting } from "../api";
  import type { Labels } from "../i18n";
  import { createQuery, invalidateQueries } from "../query.svelte";
  import { tr, ui } from "../translations.svelte";
  import AudioStart from "./AudioStart.svelte";
  import {
    CLASSIFICATIONS,
    browserTimezone,
    localDate,
    localTime,
    readableDateTime,
    rememberType,
    rememberedType,
    type Classification,
    type Intent,
  } from "./flow";

  let { t, open }: { t: Labels; open: (id: string, intent: Intent) => void } = $props();

  let kind = $state<Classification>(rememberedType());
  let title = $state("");
  let date = $state("");
  let time = $state("");
  let timezone = $state(browserTimezone());
  let language = $state<Lang | "">("");
  let participants = $state("");
  let busy = $state(false);
  let error = $state("");

  const templates = createQuery({ key: () => ["templates"], fn: () => api<any[]>("/settings/templates") });
  const groups = createQuery({ key: () => ["groups"], fn: () => api<any[]>("/recipient-groups") });
  const group = $derived.by(() => {
    const template = templates.data?.find((x) => x.classification === kind);
    return groups.data?.find((g) => g.id === template?.recipient_group_id);
  });

  async function start(intent: Intent) {
    busy = true;
    error = "";
    rememberType(kind);
    // A live recording happens now; an uploaded file most likely dates from when it was saved.
    const at = intent.kind === "upload" ? new Date(intent.file.lastModified) : new Date();
    const day = date || localDate(at);
    const clock = time || (date ? "" : localTime(at));
    try {
      const m = await api<Meeting>("/meetings", "POST", {
        title: title.trim() || `${tr(`${kind} meeting`)} · ${readableDateTime(day, clock, ui.lang)}`,
        date: day,
        time: clock,
        timezone: timezone.trim(),
        language: language || ui.lang,
        classification: kind,
        participants: participants
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      await invalidateQueries();
      open(m.id, intent);
    } catch (failure) {
      error = failure instanceof Error ? failure.message : tr("The request failed. Check the form, refresh, and try again.");
      busy = false;
    }
  }
</script>

<section class="card start-panel" aria-labelledby="start-title">
  <div class="start-heading">
    <h2 id="start-title">{tr("Start a meeting")}</h2>
    <p>{tr("Record or upload. The transcript and draft minutes are prepared automatically.")}</p>
  </div>
  <fieldset class="type-picker" disabled={busy}>
    <legend>{tr("Meeting type")}</legend>
    {#each CLASSIFICATIONS as value (value)}
      <label><input type="radio" name="meeting-type" {value} bind:group={kind} />{tr(value)}</label>
    {/each}
  </fieldset>
  <AudioStart record={() => start({ kind: "record" })} file={(f) => start({ kind: "upload", file: f })} {busy} />
  {#if group}
    <p class="start-route">
      {tr("Approved minutes go to")} <strong>{group.name}</strong>: {group.addresses.slice(0, 3).join(", ")}{group.addresses.length > 3
        ? ` +${group.addresses.length - 3}`
        : ""}
    </p>
  {:else if templates.data && groups.data}
    <p class="start-route">{tr("No recipient group is set for this meeting type yet. An admin can choose one in Templates.")}</p>
  {/if}
  <details class="start-details">
    <summary>{tr("Title, date and participants (optional)")}</summary>
    <label>{t.title}<input bind:value={title} maxlength="200" placeholder={tr("Filled in automatically")} /></label>
    <div class="formrow">
      <label>{t.date}<input type="date" bind:value={date} /></label>
      <label>{tr("Time")}<input type="time" bind:value={time} /></label>
    </div>
    <p class="caption">{tr("Leave the date empty to use the time you start recording, or the file's date for an upload.")}</p>
    <div class="formrow">
      <label>{tr("Timezone")}<input bind:value={timezone} /></label>
      <label
        >{tr("Minutes language")}<select bind:value={language}
          ><option value="">{tr("Same as the interface")}</option><option value="en">English</option><option value="ro">Română</option><option value="ru"
            >Русский</option
          ></select
        ></label
      >
    </div>
    <label>{t.participants}<textarea bind:value={participants} rows="3"></textarea></label>
  </details>
  {#if busy}<p role="status" class="caption">{tr("Starting…")}</p>{/if}
  {#if error}<p role="alert" class="error">{error}</p>{/if}
</section>
