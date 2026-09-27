<script lang="ts">
  // Port of features/Recorder.tsx. Real microphone capture through
  // /pcm-worklet.js; every 2 s chunk must be acknowledged before it counts.
  import { onMount } from "svelte";
  import { api } from "../api";
  import { CaptureQueue } from "../captureQueue";
  import type { Labels } from "../i18n";
  import { tr } from "../translations.svelte";

  type Capture = {
    ctx: AudioContext;
    stream: MediaStream;
    node: AudioWorkletNode;
    id: string;
    queue: CaptureQueue;
    gaps: unknown[];
    pausedAt?: number;
    flushed?: () => void;
  };

  let { meeting, t, done }: { meeting: string; t: Labels; done: () => void } = $props();

  let recState = $state<"idle" | "recording" | "paused" | "saving" | "error">("idle");
  let saved = $state(0);
  let level = $state(0);
  let error = $state("");
  // Raw recState: AudioContext and friends must not be wrapped in reactive proxies.
  let control = $state.raw<Capture | undefined>(undefined);

  onMount(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (control) {
        e.preventDefault();
        e.returnValue = "Unacknowledged audio may be lost";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      control?.stream.getTracks().forEach((track) => track.stop());
      void control?.ctx.close();
    };
  });

  function failure(e: Error) {
    const message =
      e.name === "NotAllowedError"
        ? "Microphone access was denied. Allow microphone access in your browser."
        : e.name === "NotFoundError"
          ? "No microphone was found. Connect a microphone and try again."
          : e.name === "NotReadableError"
            ? "The microphone is busy or unavailable. Check the device and try again."
            : e.message;
    error = tr(message);
    recState = "error";
    control?.node.port.postMessage("pause");
  }

  async function start() {
    let stream: MediaStream | undefined, ctx: AudioContext | undefined;
    try {
      error = "";
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      ctx = new AudioContext();
      await ctx.audioWorklet.addModule("/pcm-worklet.js");
      const r = await api<{ id: string }>(`/meetings/${meeting}/recordings`, "POST", { sample_rate: ctx.sampleRate });
      const node = new AudioWorkletNode(ctx, "pcm-capture");
      const queue = new CaptureQueue(
        ctx.sampleRate,
        (seq, pcm) => api(`/recordings/${r.id}/chunks/${seq}`, "PUT", pcm),
        (ack) => (saved = ack.acknowledged_samples / ack.sample_rate),
        failure,
      );
      const c: Capture = { ctx, stream, node, id: r.id, queue, gaps: [] };
      control = c;
      node.port.onmessage = (e) => {
        if (e.data instanceof ArrayBuffer) {
          try {
            queue.enqueue(e.data);
          } catch (err) {
            failure(err as Error);
            stream?.getTracks().forEach((track) => track.stop());
          }
        } else if (e.data.kind === "flushed") {
          c.flushed?.();
        } else if (e.data.kind === "level") {
          level = e.data.value;
        }
      };
      stream.getTracks().forEach((track) => (track.onended = () => failure(new Error(tr("Microphone disconnected. Saved audio is retained.")))));
      ctx.createMediaStreamSource(stream).connect(node);
      const mute = ctx.createGain();
      mute.gain.value = 0;
      node.connect(mute).connect(ctx.destination);
      recState = "recording";
    } catch (e) {
      stream?.getTracks().forEach((track) => track.stop());
      void ctx?.close();
      failure(e as Error);
    }
  }

  async function stop() {
    const c = control;
    if (!c) return;
    recState = "saving";
    try {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(tr("Microphone flush timed out."))), 5000);
        c.flushed = () => {
          clearTimeout(timer);
          resolve();
        };
        c.node.port.postMessage("stop");
      });
      c.stream.getTracks().forEach((track) => {
        track.onended = null;
        track.stop();
      });
      await c.queue.finish();
      if (!c.queue.nextSequence) throw new Error(tr("No audio was recorded."));
      await api(`/recordings/${c.id}/finish`, "POST", { count: c.queue.nextSequence, gaps: c.gaps });
      await c.ctx.close();
      control = undefined;
      recState = "idle";
      level = 0;
      done();
    } catch (e) {
      failure(e as Error);
    }
  }

  function pause() {
    const c = control;
    if (!c) return;
    if (recState === "paused") {
      c.gaps.push({ after_sequence: c.queue.nextSequence - 1, wall_duration_ms: Date.now() - (c.pausedAt || Date.now()) });
      c.node.port.postMessage("resume");
      recState = "recording";
    } else {
      c.pausedAt = Date.now();
      c.node.port.postMessage("pause");
      recState = "paused";
    }
  }

  function bookmark() {
    const c = control;
    c?.gaps.push({ bookmark_after_sequence: c.queue.nextSequence - 1, acknowledged_seconds: saved });
  }

  async function retry() {
    try {
      await control?.queue.retry();
      error = "";
      recState = "paused";
    } catch (e) {
      failure(e as Error);
    }
  }
</script>

<section class="capture">
  <div>
    <strong>{t.saved}: {saved.toFixed(1)} s</strong>
    <p>{tr("Confirmed local storage")}</p>
    {#if recState !== "idle"}
      <meter min="0" max="1" value={level} aria-label={tr("Microphone level")}></meter>
      <span class="caption">{tr(level > 0.95 ? "Clipping" : level < 0.01 ? "Silence" : "Microphone active")}</span>
    {/if}
  </div>
  {#if recState === "idle"}
    <button class="secondary" onclick={start}>{t.record}</button>
  {:else}
    <span role="status">{tr(recState)}</span>
    <button class="secondary" onclick={pause} disabled={recState === "saving" || recState === "error"}>{recState === "paused" ? t.resume : t.pause}</button>
    <button onclick={stop} disabled={recState === "saving"}>{t.stop}</button>
    <button class="secondary" onclick={bookmark}>{tr("Bookmark")}</button>
  {/if}
  {#if error}
    <div role="alert" class="error">
      {error}{#if control}<button class="secondary" onclick={retry}>{tr("Retry unsaved chunks")}</button>{/if}
    </div>
  {/if}
</section>
