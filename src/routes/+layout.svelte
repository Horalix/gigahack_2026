<script lang="ts">
  // No global stylesheet here: app.css (the dark caption theme) and the
  // Notavra stylesheet both style bare elements like :root, body and button,
  // so each page imports the one it needs.
  let { children } = $props();
</script>

{@render children()}
