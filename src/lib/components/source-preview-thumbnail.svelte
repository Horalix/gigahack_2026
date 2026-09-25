<script lang="ts">
  import type { SourcePreview } from "$lib/domain/source-selection";

  type Props = {
    fallbackInitials: string;
    preview: SourcePreview;
  };

  let { fallbackInitials, preview }: Props = $props();
</script>

<span class="preview-shell" aria-label={preview.title}>
  {#if preview.thumbnailUrl || preview.thumbnailData}
    <img
      alt=""
      src={preview.thumbnailUrl ?? preview.thumbnailData}
      draggable="false"
    />
  {/if}

  <span class="fallback-icon" aria-hidden="true">{fallbackInitials}</span>
</span>

<style>
  .preview-shell {
    position: relative;
    display: block;
    aspect-ratio: 16 / 10;
    overflow: hidden;
    border: 1px solid oklch(100% 0 0 / 0.08);
    border-radius: 7px;
    background: oklch(12% 0.008 240);
  }

  img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .fallback-icon {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--fgColor-muted);
    font-size: 1.5rem;
    font-weight: 700;
  }
</style>
