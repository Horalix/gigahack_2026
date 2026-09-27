// Ported from the Notavra web app's api.ts. Same signature and error handling;
// requests go to the in-browser demo backend instead of /api/v1 over fetch.
// To use a real service, restore the fetch() version here; nothing else in the
// UI needs to change.

import { errorMessage } from "./errors";
import { handle, MockError } from "./mock/backend";
import { tr } from "./translations.svelte";

export { assetAudioUrl, assetHasRealAudio, resetDemo, snapshotExportUrl } from "./mock/backend";

/** True while the UI runs on the in-browser demo backend: nothing is really emailed. */
export const DEMO_BACKEND = true;

export let csrf = "";
export const setCsrf = (token: string) => {
  csrf = token;
};

export async function api<T = any>(path: string, method = "GET", body?: unknown): Promise<T> {
  // A short delay so loading states behave as they do against a real service.
  await new Promise((resolve) => setTimeout(resolve, 60 + Math.random() * 120));
  try {
    return (await handle(path, method, body)) as T;
  } catch (error) {
    if (error instanceof MockError) throw new Error(errorMessage(error.code));
    console.error("[notavra demo backend]", error);
    throw new Error(tr("Cannot reach the local service. Check that Secure MOM is running."));
  }
}

// Shapes from the Notavra OpenAPI contract (contracts/openapi.json in their repo).
export type Lang = "en" | "ro" | "ru";

export interface Progress {
  stage: string;
  phase: "loading_model" | "transcribing" | "extracting" | "checking" | "diarizing" | "stage_complete";
  completed: number;
  total: number | null;
  unit: "seconds" | "segments" | "items" | "clips";
  elapsed_seconds: number;
  eta_seconds: number | null;
  eta_scope: string;
  updated_at: number;
}

export interface Job {
  id: string;
  meeting_id: string;
  asset_id: string;
  state: string;
  stage: string;
  error: string | null;
  attempt: number;
  cancel: number;
  created: number;
  progress?: Progress | null;
  transcript_only?: boolean;
}

export interface Asset {
  id: string;
  meeting_id: string;
  hash: string;
  sample_rate: number;
  samples: number;
  channels: number;
  original: string;
}

export interface Recording {
  id: string;
  meeting_id: string;
  rate: number;
  state: string;
  gaps: string;
  acknowledged_chunks: number;
  acknowledged_samples: number;
  last_sequence: number | null;
}

export interface Meeting {
  id: string;
  title: string;
  date: string;
  timezone: string;
  language: Lang;
  classification: "Medical" | "Executive" | "Administrative";
  revision: number;
  status: string;
  created: number;
  time?: string;
  notes?: string;
  participants?: { id: string; meeting_id: string; name: string }[];
  assets?: Asset[];
  jobs?: Job[];
  recordings?: Recording[];
  transcript_pending_assets?: string[];
}
