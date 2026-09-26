<script lang="ts">
  import "../../app.css";
  import "$lib/prototype/prototype.css";
  import { page } from "$app/state";

  let { children } = $props();

  const nav = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/meetings/new", label: "New meeting" },
  ];

  function active(href: string): boolean {
    return page.url.pathname === href || (href === "/dashboard" && page.url.pathname.startsWith("/patients"));
  }
</script>

<div class="doctor">
  <header class="shell">
    <a class="brand" href="/dashboard">
      <span class="mark" aria-hidden="true">M</span>
      Secure MOM
    </a>
    <nav aria-label="Main">
      {#each nav as item (item.href)}
        <a href={item.href} aria-current={active(item.href) ? "page" : undefined}>{item.label}</a>
      {/each}
    </nav>
  </header>

  <div class="banner" role="note">
    <strong>Prototype</strong> · fictional patients and meetings · nothing is uploaded, processed or emailed · resets on reload
  </div>

  <main>
    {@render children()}
  </main>
</div>

<style>
  .shell {
    display: flex;
    align-items: center;
    gap: 28px;
    padding: 12px 20px;
    border-bottom: 1px solid var(--borderColor-default);
    background: var(--bgColor-raised);
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    font-weight: 700;
    font-size: 1.05rem;
    color: var(--fgColor-default);
    text-decoration: none;
  }
  .mark {
    display: inline-grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border-radius: 7px;
    background: var(--button-primary-bgColor-rest);
    color: oklch(20% 0.02 265);
    font-weight: 800;
  }
  nav {
    display: flex;
    gap: 4px;
  }
  nav a {
    padding: 6px 12px;
    border-radius: var(--radius-default);
    color: var(--fgColor-muted);
    text-decoration: none;
    font-weight: 500;
  }
  nav a:hover {
    color: var(--fgColor-default);
    background: var(--bgColor-muted);
  }
  nav a[aria-current="page"] {
    color: var(--fgColor-default);
    background: var(--bgColor-muted);
  }
  .banner {
    padding: 6px 20px;
    font-size: 0.85rem;
    background: var(--bgColor-attention-muted);
    color: var(--fgColor-attention);
    border-bottom: 1px solid var(--borderColor-default);
  }
  main {
    flex: 1;
  }
</style>
