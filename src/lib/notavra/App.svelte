<script lang="ts">
  // Port of App from main.tsx: sidebar, header, page switching and the
  // ?meeting=<id> address. One addition: a "Demo data" badge in the header,
  // because no real service is connected yet.
  import { replaceState } from "$app/navigation";
  import { page as current } from "$app/state";
  import { api, setCsrf, type Lang } from "./api";
  import brand from "./brand.json";
  import Meetings from "./features/Meetings.svelte";
  import Settings from "./features/Settings.svelte";
  import Templates from "./features/Templates.svelte";
  import Workspace from "./features/Workspace.svelte";
  import type { Intent } from "./features/flow";
  import { strings } from "./i18n";
  import Login from "./Login.svelte";
  import Other from "./Other.svelte";
  import { createQuery, invalidateQueries } from "./query.svelte";
  import { setUiLanguage, tr, ui } from "./translations.svelte";

  const PAGES = ["meetings", "actions", "templates", "settings"] as const;
  const ICONS = ["▤", "✓", "▧", "⚙"];

  let page = $state<string>("meetings");
  let meeting = $state<string | null>(current.url.searchParams.get("meeting"));
  let notice = $state("");
  // Handed to a newly started meeting: begin recording, or upload this file.
  let intent = $state.raw<Intent | undefined>(undefined);
  const t = $derived(strings[ui.lang]);

  const me = createQuery({
    key: () => ["me"],
    fn: async () => {
      const u = await api("/me");
      setCsrf(u.csrf);
      setUiLanguage(u.language);
      return u;
    },
  });
  const setup = createQuery({ key: () => ["setup"], fn: () => api("/setup") });

  function open(id: string | null, next?: Intent) {
    intent = next;
    meeting = id;
    replaceState(id ? "?meeting=" + id : current.url.pathname, {});
  }

  async function changeLanguage(l: Lang) {
    try {
      await api("/me", "PATCH", { language: l });
      setUiLanguage(l);
      notice = "";
    } catch (error) {
      notice = error instanceof Error ? error.message : tr("The request failed. Check the form, refresh, and try again.");
    }
  }

  async function logout() {
    await api("/sessions/current", "DELETE");
    location.reload();
  }
</script>

<svelte:head>
  <title>{brand.name} · Meeting workspace</title>
  <link rel="icon" type="image/svg+xml" href="/brand/symbol.svg" />
  <link rel="icon" type="image/png" sizes="32x32" href="/brand/favicon.png" />
</svelte:head>

{#if me.isPending || setup.isPending}
  <p role="status">{t.loading}</p>
{:else if !me.data}
  <Login {t} setup={!!setup.data?.required} done={() => invalidateQueries()} />
{:else}
  <div class="shell">
    <a class="skip" href="#content">{tr("Skip to content")}</a>
    <aside class="sidebar">
      <div class="brand">
        <img class="brandmark" src="/brand/symbol.svg" alt="" width="36" height="40" /><span>{brand.name}<small>{tr("MEETING WORKSPACE")}</small></span>
      </div>
      <nav>
        {#each PAGES as p, i (p)}
          <button
            class={page === p ? "active" : ""}
            onclick={() => {
              page = p;
              open(null);
            }}><span aria-hidden="true">{ICONS[i]}</span>{t[p]}</button
          >
        {/each}
      </nav>
      <div class="sidebarfoot">
        <span class="dot"></span>{t.local}
        <p>{tr("Evidence before approval.")}<br />{tr("Your recordings stay local.")}</p>
      </div>
    </aside>
    <div class="main">
      <header>
        <span>{tr("MEETING OPERATIONS")}</span>
        <div class="toolbar">
          <span class="badge" title="No local service is connected. See Settings › Demo backend.">Demo data</span>
          <label class="sr-only" for="language">{tr("Interface language")}</label>
          <select id="language" value={ui.lang} onchange={(e) => changeLanguage(e.currentTarget.value as Lang)}
            ><option value="en">English</option><option value="ro">Română</option><option value="ru">Русский</option></select
          >
          <button class="textbutton" onclick={logout}>{t.logout}</button>
        </div>
      </header>
      <main id="content">
        {#if notice}<p role="alert" class="error">{notice}</p>{/if}
        {#if page === "meetings"}
          {#if meeting}
            {#key meeting}
              <Workspace role={me.data.role} id={meeting} {t} back={() => open(null)} {intent} intentDone={() => (intent = undefined)} />
            {/key}
          {:else}
            <Meetings canCreate={me.data.role !== "viewer"} {t} {open} />
          {/if}
        {:else if page === "settings"}
          <Settings role={me.data.role} />
        {:else if page === "templates"}
          <Templates role={me.data.role} />
        {:else}
          <Other {page} {t} />
        {/if}
      </main>
    </div>
  </div>
{/if}
