<script lang="ts">
  // Port of Login from main.tsx.
  import { api, setCsrf } from "./api";
  import brand from "./brand.json";
  import type { Labels } from "./i18n";
  import { tr } from "./translations.svelte";

  let { t, setup, done }: { t: Labels; setup: boolean; done: () => void } = $props();

  let error = $state("");
  let busy = $state(false);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    const f = new FormData(e.currentTarget as HTMLFormElement);
    try {
      const u = await api(setup ? "/setup" : "/sessions", "POST", { name: f.get("name"), password: f.get("password") });
      setCsrf(u.csrf);
      done();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : tr("The request failed. Check the form, refresh, and try again.");
    } finally {
      busy = false;
    }
  }
</script>

<div class="login">
  <div class="brand"><img class="brandmark" src="/brand/symbol.svg" alt="" width="36" height="40" />{brand.name}</div>
  <p class="eyebrow">{tr("PRIVATE MEETING WORKSPACE")}</p>
  <h1>{setup ? t.setup : t.login}</h1>
  <p>{tr("No default password. Your account is stored on this computer.")}</p>
  <form onsubmit={submit}>
    <label>{t.username}<input name="name" autocomplete="username" required minlength="3" /></label>
    <label
      >{t.password}<input name="password" type="password" autocomplete={setup ? "new-password" : "current-password"} required minlength="12" /></label
    >
    {#if error}<p role="alert" class="error">{error}</p>{/if}
    <button disabled={busy}>{busy ? t.loading : t.continue} →</button>
  </form>
  <p class="caption">{tr("Prepare local models before processing. Setup never downloads assets.")}</p>
</div>
