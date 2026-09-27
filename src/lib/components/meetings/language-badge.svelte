<script lang="ts">
  import { LANGUAGE_LABEL } from "$lib/prototype/format";
  import type { Language } from "$lib/prototype/types";

  type Props = { language: Language };
  let { language }: Props = $props();

  const titles: Record<Language, string> = {
    ro: "Romanian",
    ru: "Russian",
    en: "English",
    mul: "Language switches inside this segment",
    und: "Language not determined",
  };
</script>

<span class="lang lang-{language}" title={titles[language]}>{LANGUAGE_LABEL[language]}</span>

<style>
  .lang {
    display: inline-block;
    min-width: 2.6em;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-align: center;
    border: 1px solid currentColor;
  }
  .lang-ro {
    color: oklch(78% 0.12 250);
  }
  .lang-ru {
    color: oklch(76% 0.13 25);
  }
  .lang-en {
    color: oklch(80% 0.12 150);
  }
  .lang-mul {
    color: oklch(84% 0.13 86);
  }
  .lang-und {
    color: var(--fgColor-subtle);
  }
</style>
