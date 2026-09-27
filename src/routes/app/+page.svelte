<script lang="ts">
  // The Notavra meeting workspace, ported from the teammate's React app.
  // Fonts and stylesheet are the same ones that app loads; all are bundled
  // locally, so nothing is fetched from the internet at runtime.
  import "@fontsource/noto-sans/latin.css";
  import "@fontsource/noto-sans/latin-ext.css";
  import "@fontsource/noto-sans/cyrillic.css";
  import "$lib/notavra/notavra.css";
  import "$lib/notavra/experience.css";
  import LocalWorkbench from "$lib/notavra/LocalWorkbench.svelte";
</script>

<LocalWorkbench />
