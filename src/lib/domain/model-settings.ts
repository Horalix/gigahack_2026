export type ModelMetadata = {
  id: string;
  name: string;
  runtime: string;
  language?: string | null;
  path: string;
  checksumSha256?: string | null;
  executablePath?: string | null;
  fileSizeBytes?: number | null;
  isInstalled: boolean;
  isDefault: boolean;
  supportsTranslation: boolean;
};

export type ModelSettingsStore = {
  activeModelId: string;
  modelsDir: string;
  models: ModelMetadata[];
};

export type ModelStatus = {
  downloadProgress: number | null;
  activeModel?: ModelMetadata | null;
  modelsDir: string;
  isReady: boolean;
  message: string;
};

export type AsrDiagnosticResult = {
  text: string;
};

export function formatModelSize(bytes: number | null | undefined): string {
  if (!bytes) {
    return "Missing";
  }

  const megabytes = bytes / 1024 / 1024;
  if (megabytes < 1024) {
    return `${megabytes.toFixed(1)} MB`;
  }

  return `${(megabytes / 1024).toFixed(2)} GB`;
}
