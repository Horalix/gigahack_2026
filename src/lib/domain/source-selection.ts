export type SourceMode = "applications" | "system" | "microphone";

export type SourceKind =
  | "application"
  | "window"
  | "system_audio"
  | "output_device"
  | "microphone";

export type AudioEndpointFlow = "capture" | "render";

export type SourceMetadata = {
  appName?: string | null;
  processName?: string | null;
  processId?: number | null;
  processPath?: string | null;
  windowTitle?: string | null;
  endpointId?: string | null;
  endpointFlow?: AudioEndpointFlow | null;
  isDefault?: boolean | null;
};

export type MockPreviewTemplate =
  | "browser"
  | "chat"
  | "meeting"
  | "video"
  | "game";

export type AudioSource = {
  id: string;
  displayName: string;
  kind: SourceKind;
  isAvailable: boolean;
  platform: string;
  metadata?: SourceMetadata | null;
};

export type CssPreviewMetadata = {
  label: string;
  accentColor: string;
  background: string;
};

export type SourcePreview = {
  sourceId: string;
  title: string;
  kind: SourceKind;
  thumbnailUrl?: string | null;
  thumbnailData?: string | null;
  isLivePreviewAvailable: boolean;
  cssPreview?: CssPreviewMetadata | null;
  mockTemplate?: MockPreviewTemplate | null;
};

export type PlatformCapabilities = {
  platform: string;
  sourceEnumerationAvailable: boolean;
  windowCaptureAvailable: boolean;
  systemAudioCaptureAvailable: boolean;
  microphoneCaptureAvailable: boolean;
  livePreviewAvailable: boolean;
  supportsSystemAudio: boolean;
  supportsApplicationAudio: boolean;
  supportsMicrophone: boolean;
  supportsLivePreview: boolean;
  supportsLoopbackCapture: boolean;
};

export type SourceSelection = {
  mode: SourceMode;
  selectedApplications: string[];
  selectedSourceId?: string;
  selectedDeviceId?: string;
  displayLabel: string;
};

export function createApplicationSelection(
  sources: AudioSource[],
  applicationIds: string[],
): SourceSelection | null {
  const selectedApplications = sources
    .filter(
      (source) =>
        source.isAvailable &&
        (source.kind === "application" || source.kind === "window"),
    )
    .map((source) => source.id)
    .filter((sourceId) => applicationIds.includes(sourceId));

  if (selectedApplications.length === 0) {
    return null;
  }

  return {
    mode: "applications",
    selectedApplications,
    displayLabel: formatApplicationLabel(sources, selectedApplications),
  };
}

export function createSystemSelection(
  source: AudioSource | undefined,
): SourceSelection | null {
  if (!source) {
    return null;
  }

  return {
    mode: "system",
    selectedApplications: [],
    selectedSourceId: source.id,
    displayLabel: source.displayName,
  };
}

export function createMicrophoneSelection(
  sources: AudioSource[],
  deviceId: string,
): SourceSelection | null {
  const source = sources.find(
    (candidate) =>
      (candidate.kind === "microphone" || candidate.kind === "output_device") &&
      candidate.id === deviceId,
  );

  if (!source) {
    return null;
  }

  return {
    mode: "microphone",
    selectedApplications: [],
    selectedDeviceId: source.id,
    displayLabel: source.displayName,
  };
}

export function getSourceModeLabel(mode: SourceMode): string {
  if (mode === "applications") {
    return "Applications";
  }

  if (mode === "system") {
    return "Entire System";
  }

  return "Microphone";
}

export function sourceModeForKind(kind: SourceKind): SourceMode {
  if (kind === "application" || kind === "window") {
    return "applications";
  }

  if (kind === "system_audio") {
    return "system";
  }

  return "microphone";
}

export function sourceInitials(displayName: string): string {
  const words = displayName
    .split(/\s+/)
    .map((word) => word.trim())
    .filter(Boolean);

  if (words.length === 0) {
    return "?";
  }

  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

function formatApplicationLabel(
  sources: AudioSource[],
  applicationIds: string[],
): string {
  const names = applicationIds
    .map((sourceId) => sources.find((source) => source.id === sourceId))
    .filter((source): source is AudioSource => source !== undefined)
    .map((source) => source.displayName);

  if (names.length <= 2) {
    return names.join(" + ");
  }

  return `${names.slice(0, 2).join(" + ")} + ${names.length - 2} more`;
}
