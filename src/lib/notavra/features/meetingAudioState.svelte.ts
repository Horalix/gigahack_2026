// Port of useMeetingAudio from features/MeetingAudio.tsx. Call during component
// setup. The hidden <audio> element is rendered by MeetingAudio.svelte and
// attached through `element`, where the React hook returned it as JSX.
//
// Demo-backend adaptation: the real service serves ten-minute windows from
// /api/v1/assets/{id}/clip?start&end. The demo holds each recording as one
// in-memory file, so the whole recording is a single window. Seeking, the
// loading guard and continuous playback follow the original logic unchanged.

import { assetAudioUrl, type Meeting } from "../api";
import { tr } from "../translations.svelte";
import { audioWindow } from "./transcriptModel";

export type MeetingAudioState = ReturnType<typeof createMeetingAudio>;

export function createMeetingAudio(assets: () => Meeting["assets"]) {
  let audio: HTMLAudioElement | null = null;
  let windowRef = { asset: "", start: 0, end: 0 };
  let pending = { time: 0, play: false };
  let generation = 0;

  const s = $state({ assetId: "", current: 0, playing: false, loaded: false, error: "", muted: false });
  const asset = $derived(assets()?.find((a) => a.id === s.assetId) || assets()?.[0]);
  const duration = $derived(asset ? asset.samples / asset.sample_rate : 0);

  function play(element: HTMLAudioElement) {
    void element.play().catch(() => (s.error = tr("Audio playback failed. Try again.")));
  }

  function seek(seconds: number, shouldPlay = false, id?: string) {
    const target = assets()?.find((a) => a.id === (id || asset?.id));
    const element = audio;
    if (!target || !element) return;
    const total = target.samples / target.sample_rate,
      position = audioWindow(seconds, total),
      cached = windowRef;
    s.error = "";
    s.assetId = target.id;
    s.current = position.target;
    if (cached.asset === target.id && position.target >= cached.start && position.target < cached.end && element.readyState >= 1) {
      element.currentTime = position.target - cached.start;
      if (shouldPlay) play(element);
      return;
    }
    const request = ++generation;
    const span = { start: 0, end: total }; // one window per recording in the demo
    pending = { time: position.target - span.start, play: shouldPlay };
    windowRef = { asset: target.id, ...span };
    element.pause();
    s.loaded = false;
    element.onloadedmetadata = () => {
      if (request !== generation) return;
      element.currentTime = pending.time;
      s.loaded = true;
      if (pending.play) play(element);
    };
    element.src = assetAudioUrl(target.id) ?? "";
    element.load();
  }

  function toggle() {
    const element = audio;
    if (!element || !asset) return;
    if (!element.paused) {
      element.pause();
      pending.play = false;
    } else seek(s.current >= duration - 0.01 ? 0 : s.current, true);
  }

  $effect(() => {
    if (!s.playing) return;
    let frame = 0,
      last = 0;
    const tick = (now: number) => {
      if (now - last > 80 && audio && !audio.paused) {
        s.current = windowRef.start + audio.currentTime;
        last = now;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  });

  return {
    get element() {
      return audio;
    },
    set element(node: HTMLAudioElement | null) {
      audio = node;
    },
    get asset() {
      return asset;
    },
    get duration() {
      return duration;
    },
    get current() {
      return s.current;
    },
    get playing() {
      return s.playing;
    },
    get loaded() {
      return s.loaded;
    },
    get error() {
      return s.error;
    },
    get muted() {
      return s.muted;
    },
    toggle,
    seek,
    setMuted(value: boolean) {
      s.muted = value;
    },
    // Event handlers for the <audio> element.
    onplay() {
      s.playing = true;
    },
    onpause() {
      s.playing = false;
    },
    ontimeupdate() {
      if (audio?.readyState) s.current = windowRef.start + audio.currentTime;
    },
    onended() {
      if (windowRef.end < duration) seek(windowRef.end, true);
      else {
        s.current = duration;
        s.playing = false;
      }
    },
    onerror() {
      s.error = tr("Audio playback failed. Try again.");
      s.playing = false;
    },
  };
}
