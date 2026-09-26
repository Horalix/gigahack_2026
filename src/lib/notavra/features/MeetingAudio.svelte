<script lang="ts">
  // Port of MeetingAudio from features/MeetingAudio.tsx: the recording surface
  // with the speaker-activity line, and the mini player shown once the surface
  // scrolls out of view.
  import { Pause, Play, Volume2, VolumeX } from "@lucide/svelte";
  import { tr } from "../translations.svelte";
  import type { MeetingAudioState } from "./meetingAudioState.svelte";
  import { activeSegment, speakerIndex, speakerPalette, timeLabel, type SpeechSegment } from "./transcriptModel";

  let { audio, segments }: { audio: MeetingAudioState; segments: SpeechSegment[] } = $props();

  let canvas: HTMLCanvasElement | undefined = $state();
  let surface: HTMLDivElement | undefined = $state();
  let mini = $state(false);
  let hover = $state<number | null>(null);

  $effect(() => {
    const element = surface;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => (mini = !entry.isIntersecting), { threshold: 0 });
    observer.observe(element);
    return () => observer.disconnect();
  });

  $effect(() => {
    const element = canvas;
    if (!element) return;
    const list = segments,
      total = audio.duration;
    const draw = () => {
      const width = element.clientWidth,
        height = 42,
        scale = window.devicePixelRatio || 1;
      element.width = width * scale;
      element.height = height * scale;
      const ctx = element.getContext("2d");
      if (!ctx) return;
      ctx.scale(scale, scale);
      ctx.clearRect(0, 0, width, height);
      if (!total) return;
      for (const segment of list) {
        const x = (segment.start / 16000 / total) * width,
          end = (segment.end / 16000 / total) * width;
        ctx.fillStyle = speakerPalette[speakerIndex(segment.speaker)];
        for (let pos = x; pos < Math.max(x + 2, end); pos += 5) ctx.fillRect(pos, 9, Math.min(2.5, Math.max(2, end - pos)), 24);
      }
    };
    const observer = new ResizeObserver(draw);
    observer.observe(element);
    draw();
    return () => observer.disconnect();
  });

  function pointerMove(e: PointerEvent) {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    hover = Math.max(0, Math.min(1, (e.clientX - box.left) / box.width)) * audio.duration;
  }
</script>

{#snippet range(compact: boolean)}
  <input
    class={compact ? "mini-seek" : "activity-seek"}
    type="range"
    aria-label={tr("Seek recording")}
    aria-valuetext={`${timeLabel(audio.current)} / ${timeLabel(audio.duration)}`}
    min={0}
    max={audio.duration || 1}
    step={0.1}
    disabled={!audio.duration}
    oninput={(e) => audio.seek(Number(e.currentTarget.value), audio.playing)}
    value={Math.min(audio.current, audio.duration)}
  />
{/snippet}

{#snippet playButton()}
  <button class="audio-play" aria-label={tr(audio.playing ? "Pause recording" : "Play recording")} disabled={!audio.asset} onclick={audio.toggle}
    >{#if audio.playing}<Pause size={25} fill="currentColor" strokeWidth={1} />{:else}<Play size={25} fill="currentColor" strokeWidth={1} />{/if}</button
  >
{/snippet}

<audio
  bind:this={audio.element}
  preload="none"
  hidden
  muted={audio.muted}
  onplay={audio.onplay}
  onpause={audio.onpause}
  ontimeupdate={audio.ontimeupdate}
  onended={audio.onended}
  onerror={audio.onerror}
></audio>
<div class="audio-experience" bind:this={surface}>
  {@render playButton()}
  <div class="audio-track">
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="activity-line"
      onpointermove={pointerMove}
      onpointerleave={() => (hover = null)}
      title={hover === null ? tr("Speaker activity") : timeLabel(hover)}
    >
      <canvas bind:this={canvas} aria-hidden="true"></canvas>
      <div
        class="audio-playhead"
        style:left={`${audio.duration ? (audio.current / audio.duration) * 100 : 0}%`}
        style:background={speakerPalette[speakerIndex(activeSegment(segments, audio.current)?.speaker || null)]}
        aria-hidden="true"
      ></div>
      {@render range(false)}
    </div>
    <div class="audio-times"><span>{timeLabel(audio.current)}</span><span>{timeLabel(audio.duration)}</span></div>
  </div>
</div>
{#if audio.error}<p class="error" role="alert">{audio.error}</p>{/if}
{#if mini && audio.loaded}
  <div class="mini-player">
    {@render playButton()}<span>{timeLabel(audio.current)}</span>{@render range(true)}<span>{timeLabel(audio.duration)}</span><button
      class="icon-button"
      aria-label={tr(audio.muted ? "Unmute" : "Mute")}
      onclick={() => audio.setMuted(!audio.muted)}>{#if audio.muted}<VolumeX size={18} />{:else}<Volume2 size={18} />{/if}</button
    >
  </div>
{/if}
