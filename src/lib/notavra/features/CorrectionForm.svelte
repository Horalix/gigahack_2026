<script lang="ts">
  // Port of CorrectionForm from features/Workspace.tsx.
  import { initialValue } from "../actions";
  import { api } from "../api";
  import { tr } from "../translations.svelte";

  let {
    candidate,
    revision,
    act,
    corrected,
    subjects,
  }: {
    candidate: any;
    revision: number;
    act: (fn: () => Promise<unknown>) => void;
    corrected: (id: string) => void;
    subjects: string[];
  } = $props();

  function submit(e: SubmitEvent) {
    e.preventDefault();
    const f = new FormData(e.currentTarget as HTMLFormElement);
    act(async () => {
      const result = await api(`/items/${candidate.id}/corrections`, "POST", {
        revision,
        subject: f.get("subject"),
        text: f.get("text"),
        owner: f.get("owner") || null,
        due: f.get("due") || null,
        condition: f.get("condition") || null,
        value: f.get("value") || null,
        resolved_issues: f.getAll("resolved_issues"),
        reason: f.get("reason"),
        category: f.get("category"),
        kind: f.get("kind"),
      });
      corrected(result.id);
    });
  }
</script>

<details>
  <summary>{tr("Secretary amendment")}</summary>
  <p class="notice">{tr("Changes are labeled as reviewer additions. No audio evidence is invented for edited fields.")}</p>
  <form onsubmit={submit}>
    <label>{tr("Topic / item key")}<input name="subject" list="known-topics" value={candidate.body.subject} required maxlength="160" /></label>
    <datalist id="known-topics">{#each subjects as subject (subject)}<option value={subject}></option>{/each}</datalist>
    <p class="caption">{tr("Use the same key only for the same task and scope. A new key separates unrelated items. Explain the link or split below.")}</p>
    <label>{tr("Text")}<textarea name="text" aria-label={tr("Text")} value={candidate.body.text} required></textarea></label>
    <label>{tr("Owner")}<input name="owner" value={candidate.body.owner || ""} /></label>
    <label>{tr("Due")}<input name="due" type="date" value={candidate.body.due || ""} /></label>
    <label>{tr("Condition")}<textarea name="condition" aria-label={tr("Condition")} value={candidate.body.condition || ""}></textarea></label>
    <label>{tr("Value")}<input name="value" value={candidate.body.value || ""} /></label>
    <label
      >{tr("Category")}<select name="category" use:initialValue={candidate.body.category}
        >{#each ["action", "decision", "information"] as v (v)}<option value={v}>{tr(v)}</option>{/each}</select
      ></label
    >
    <label
      >{tr("Speech act")}<select name="kind" use:initialValue={candidate.body.kind}
        >{#each ["propose", "confirm", "amend", "reject", "cancel", "reopen", "inform"] as v (v)}<option value={v}>{tr(v)}</option>{/each}</select
      ></label
    >
    {#if candidate.body.uncertainties.length > 0}
      <fieldset>
        <legend>{tr("Issues I have resolved")}</legend>
        <p class="caption">{tr("Only check an issue after reviewing its source. Your reason is retained in the amendment history.")}</p>
        {#each candidate.body.uncertainties as issue (issue)}
          <label><input type="checkbox" name="resolved_issues" value={issue} />{issue}</label>
        {/each}
      </fieldset>
    {/if}
    <label>{tr("Reason for amendment")}<input name="reason" required minlength="3" /></label>
    <button>{tr("Save reviewed amendment")}</button>
  </form>
</details>
