<script lang="ts">
  import type { Tone } from "$lib/prototype/format";

  type Props = { label: string; tone: Tone };
  let { label, tone }: Props = $props();
</script>

<span class="chip tone-{tone}">{label}</span>
