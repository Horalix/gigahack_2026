<script lang="ts">
  // Port of GroupEditor from features/Settings.tsx.
  import { api } from "../api";
  import { tr } from "../translations.svelte";

  let { group: g, busy, save }: { group: any; busy: boolean; save: (fn: () => Promise<unknown>) => void } = $props();

  function submit(e: SubmitEvent) {
    e.preventDefault();
    const f = new FormData(e.currentTarget as HTMLFormElement);
    save(() =>
      api("/recipient-groups", "POST", {
        id: g.id,
        version: g.version,
        name: f.get("edit_name"),
        addresses: String(f.get("edit_addresses"))
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    );
  }
</script>

<details>
  <summary>{tr("Edit recipient group")}: {g.name}</summary>
  {#key g.version}
    <form onsubmit={submit}>
      <label>{tr("Group name")}<input name="edit_name" value={g.name} required /></label>
      <label
        >{tr("Updated addresses, one per line")}<textarea
          name="edit_addresses"
          aria-label={tr("Updated addresses, one per line")}
          value={g.addresses.join("\n")}
          required
        ></textarea></label
      >
      <p class="caption">{tr("Changes apply to new deliveries. Previously queued deliveries keep their original recipients.")}</p>
      <button disabled={busy}>{tr("Save group changes")}</button>
    </form>
  {/key}
</details>
