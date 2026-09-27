<script lang="ts">
  // Port of features/Settings.tsx, plus one card that is not in the original:
  // "Demo backend", which explains and resets the in-browser demo data.
  import { api, resetDemo } from "../api";
  import { createQuery, invalidateQueries } from "../query.svelte";
  import { tr } from "../translations.svelte";
  import GroupEditor from "./GroupEditor.svelte";

  let { role }: { role: string } = $props();

  const q = createQuery({ key: () => ["proof"], fn: () => api<any>("/system/proof") });
  const groups = createQuery({ key: () => ["groups"], fn: () => api<any[]>("/recipient-groups") });
  const glossary = createQuery({ key: () => ["glossary"], fn: () => api<any>("/settings/glossary"), enabled: () => role === "admin" });

  let status = $state("");
  let busy = $state(false);

  async function save(fn: () => Promise<unknown>) {
    busy = true;
    status = "";
    try {
      await fn();
      await invalidateQueries();
      status = tr("Saved on this computer.");
    } catch (e) {
      status = e instanceof Error ? e.message : tr("The request failed. Check the form, refresh, and try again.");
    } finally {
      busy = false;
    }
  }

  function createGroup(e: SubmitEvent) {
    e.preventDefault();
    const f = new FormData(e.currentTarget as HTMLFormElement);
    void save(() => api("/recipient-groups", "POST", { name: f.get("name"), addresses: String(f.get("addresses")).split("\n").filter(Boolean) }));
  }

  function saveGlossary(e: SubmitEvent) {
    e.preventDefault();
    const f = new FormData(e.currentTarget as HTMLFormElement);
    void save(() => api("/settings/glossary", "PUT", { version: glossary.data.version, terms: String(f.get("terms")).split("\n").filter(Boolean) }));
  }

  function createAccount(e: SubmitEvent) {
    e.preventDefault();
    const f = new FormData(e.currentTarget as HTMLFormElement);
    void save(() => api("/accounts", "POST", { name: f.get("name"), password: f.get("password"), role: f.get("role") }));
  }
</script>

<p class="eyebrow">{tr("WORKSPACE SETTINGS")}</p>
<h1>{tr("Settings")}</h1>
{#if status}<p role="status" class="notice">{status}</p>{/if}
<section class="card">
  <h2>{tr("Local processing")}</h2>
  <p>{tr("Inference runs locally. Network monitoring: ")}<strong>{tr(q.data?.network_observation || "Not measured")}</strong></p>
  <p>{tr("Model files present: ")}{JSON.stringify(q.data?.models || {})}</p>
  <h3>{tr("Optional capabilities")}</h3>
  {#each Object.entries(q.data?.capabilities || {}) as [name, c] (name)}
    {@const cap = c as any}
    <p>
      <strong>{tr(name)}</strong> — {tr(cap.available ? "Available" : "Unavailable")} · {tr(cap.qualification)}<br />{#if cap.prerequisite}{tr(
          cap.prerequisite,
        )}{/if}
    </p>
  {/each}
  <p class="notice">{tr("Romanian and Russian translations need native review. Target 8 GB laptop qualification remains separate from this host.")}</p>
  <a href="http://127.0.0.1:8025" target="_blank" rel="noreferrer">{tr("Open local Mailpit inbox ↗")}</a>
</section>
<section class="card">
  <h2>{tr("Allowed recipient groups")}</h2>
  {#each groups.data ?? [] as g (g.id)}
    <article>
      <p>{g.name}{tr(" · version ")}{g.version}: {g.addresses.join(", ")}</p>
      {#if role === "admin"}<GroupEditor group={g} {busy} {save} />{/if}
    </article>
  {/each}
  {#if role === "admin"}
    <form onsubmit={createGroup}>
      <label>{tr("New group name")}<input name="name" required /></label>
      <label>{tr("Addresses, one per line")}<textarea name="addresses" required placeholder="secretary@secure-mom.test"></textarea></label>
      <p class="caption">{tr("Admin only. Domains must match the operator's configured allowlist. A model cannot add recipients.")}</p>
      <button disabled={busy}>{tr("Save recipient group")}</button>
    </form>
  {/if}
</section>
<section class="card">
  <h2>{tr("Glossary candidates")}</h2>
  {#if glossary.data}
    {#key glossary.data.version}
      <form onsubmit={saveGlossary}>
        <label>{tr("Terms, one per line")}<textarea name="terms" value={glossary.data.terms.join("\n")} rows="5"></textarea></label>
        <p class="caption">{tr("Reference candidates only. Unknown names are never automatically replaced.")}</p>
        <button disabled={busy}>{tr("Save glossary")}</button>
      </form>
    {/key}
  {:else}
    <p>{tr("Admin access required to edit glossary.")}</p>
  {/if}
</section>
{#if role === "admin"}
  <section class="card">
    <h2>{tr("Create local account")}</h2>
    <form onsubmit={createAccount}>
      <label>{tr("Username")}<input name="name" required minlength="3" /></label>
      <label>{tr("Password")}<input name="password" type="password" required minlength="12" autocomplete="new-password" /></label>
      <label
        >{tr("Role")}<select name="role" aria-label={tr("Role")}
          ><option value="secretary">{tr("secretary")}</option><option value="viewer">{tr("viewer")}</option><option value="admin">{tr("admin")}</option></select
        ></label
      >
      <p class="caption">{tr("Admin role does not grant access to other people's meetings.")}</p>
      <button disabled={busy}>{tr("Create account")}</button>
    </form>
  </section>
{/if}
<section class="card">
  <h2>Demo backend</h2>
  <p>
    No local service is connected. Meetings, reviews and accounts are kept in this browser tab only; uploaded or recorded audio is kept in memory
    and is lost on reload. Nothing is sent anywhere, including email.
  </p>
  <button
    class="secondary"
    onclick={() => {
      resetDemo();
      location.reload();
    }}>Reset demo data</button
  >
</section>
