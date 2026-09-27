// Browser-side audio helpers for the demo backend: probe an uploaded file's
// duration, turn recorded PCM chunks into a playable WAV, and synthesise a
// quiet placeholder for demo meetings that have no real audio.

export async function probeDuration(file: Blob): Promise<number> {
  const url = URL.createObjectURL(file);
  try {
    return await new Promise<number>((resolve, reject) => {
      const audio = new Audio();
      audio.preload = "metadata";
      audio.onloadedmetadata = () => (Number.isFinite(audio.duration) ? resolve(audio.duration) : reject(new Error("no duration")));
      audio.onerror = () => reject(new Error("decode failed"));
      audio.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function pcm16ToWav(chunks: ArrayBuffer[], sampleRate: number): Blob {
  const dataBytes = chunks.reduce((n, c) => n + c.byteLength, 0);
  const header = new DataView(new ArrayBuffer(44));
  const text = (offset: number, s: string) => [...s].forEach((ch, i) => header.setUint8(offset + i, ch.charCodeAt(0)));
  text(0, "RIFF");
  header.setUint32(4, 36 + dataBytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  header.setUint32(16, 16, true);
  header.setUint16(20, 1, true); // PCM
  header.setUint16(22, 1, true); // mono
  header.setUint32(24, sampleRate, true);
  header.setUint32(28, sampleRate * 2, true);
  header.setUint16(32, 2, true);
  header.setUint16(34, 16, true);
  text(36, "data");
  header.setUint32(40, dataBytes, true);
  return new Blob([header.buffer, ...chunks], { type: "audio/wav" });
}

/** A soft pulsing tone standing in for audio the demo does not have. */
export function placeholderWav(seconds: number): Blob {
  const rate = 8000;
  const samples = new Int16Array(Math.max(1, Math.round(Math.min(seconds, 900) * rate)));
  for (let i = 0; i < samples.length; i++) {
    const t = i / rate;
    const envelope = 0.5 + 0.5 * Math.sin(2 * Math.PI * 0.5 * t);
    samples[i] = Math.round(Math.sin(2 * Math.PI * 220 * t) * envelope * 0.06 * 32767);
  }
  return pcm16ToWav([samples.buffer], rate);
}

export async function sha256Hex(data: ArrayBuffer | string): Promise<string> {
  const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data;
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
