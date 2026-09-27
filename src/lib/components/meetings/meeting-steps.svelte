<script lang="ts">
  import type { Meeting } from "$lib/prototype/types";

  type Step = "processing" | "transcript" | "minutes" | "sent";
  type Props = { meeting: Meeting; current: Step };
  let { meeting, current }: Props = $props();

  const processed = $derived(meeting.job.stage === "complete");

  const steps = $derived([
    { key: "processing", label: "Processing", href: `/meetings/${meeting.id}`, open: true },
    { key: "transcript", label: "Transcript", href: `/meetings/${meeting.id}/review`, open: processed },
    { key: "minutes", label: "Minutes", href: `/meetings/${meeting.id}/minutes`, open: processed },
    { key: "sent", label: "Sent", href: `/meetings/${meeting.id}/sent`, open: meeting.delivery !== null },
  ]);

  const currentIndex = $derived(steps.findIndex((s) => s.key === current));
</script>

<nav aria-label="Meeting progress">
  <ol>
    {#each steps as step, i (step.key)}
      <li class:done={i < currentIndex} class:current={i === currentIndex}>
        {#if step.open && i !== currentIndex}
          <a href={step.href}><span class="dot">{i < currentIndex ? "✓" : i + 1}</span>{step.label}</a>
        {:else}
          <span class="step" aria-current={i === currentIndex ? "step" : undefined}>
            <span class="dot">{i < currentIndex ? "✓" : i + 1}</span>{step.label}
          </span>
        {/if}
      </li>
    {/each}
  </ol>
</nav>

<style>
  ol {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  li {
    display: flex;
    align-items: center;
  }
  li + li::before {
    content: "";
    width: 24px;
    height: 1px;
    margin-right: 6px;
    background: var(--borderColor-emphasis);
  }
  a,
  .step {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 10px 4px 4px;
    border-radius: 999px;
    color: var(--fgColor-subtle);
    text-decoration: none;
    font-size: 0.9rem;
  }
  a:hover {
    background: var(--bgColor-muted);
    color: var(--fgColor-default);
  }
  .dot {
    display: inline-grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 1px solid var(--borderColor-emphasis);
    font-size: 0.75rem;
    font-weight: 700;
  }
  .done a,
  .done .step {
    color: var(--fgColor-muted);
  }
  .done .dot {
    background: var(--bgColor-success-muted);
    border-color: transparent;
    color: var(--fgColor-success);
  }
  .current .step {
    color: var(--fgColor-default);
    font-weight: 600;
    background: var(--bgColor-accent-muted);
  }
  .current .dot {
    border-color: var(--borderColor-accent);
    color: var(--fgColor-accent);
  }
</style>
