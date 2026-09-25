export type FontWeight = "normal" | "bold";
export type OverlayProfileId =
  | "profile1"
  | "profile2"
  | "profile3"
  | "profile4"
  | "profile5";

export type OverlaySettings = {
  alwaysOnTop: boolean;
  fontFamily: string;
  fontSize: number;
  fontWeight: FontWeight;
  originalLineScale: number;
  textColor: string;
  backgroundColor: string;
  backgroundOpacity: number;
  outlineColor: string;
  outlineWidth: number;
  startWidth: number;
  startHeight: number;
  startX?: number | null;
  startY?: number | null;
  clickThrough: boolean;
};

export type OverlaySettingsProfile = {
  id: OverlayProfileId;
  name: string;
  settings: OverlaySettings;
};

export type OverlaySettingsStore = {
  activeProfileId: OverlayProfileId;
  profiles: OverlaySettingsProfile[];
};

export type OverlayPlacement = {
  x: number;
  y: number;
  width: number;
  height: number;
  isAccepted: boolean;
};

const HEX_COLOR = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
const RGB_COLOR = /^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$/i;

export function normalizeCssColor(value: string, fallback: string): string {
  return parseColor(value)?.css ?? fallback;
}

export function colorPickerValue(value: string, fallback = "#ffffff"): string {
  return parseColor(value)?.hex ?? fallback;
}

export function rgbaPreviewColor(color: string, opacity: number): string {
  const parsed = parseColor(color) ?? parseColor("#000000");
  const alpha = Math.min(Math.max(opacity, 0), 1);

  if (!parsed) {
    return `rgb(0 0 0 / ${alpha})`;
  }

  return `rgb(${parsed.red} ${parsed.green} ${parsed.blue} / ${alpha})`;
}

export function hasValidOverlaySettingsColors(
  settings: OverlaySettings,
): boolean {
  return (
    parseColor(settings.textColor) !== undefined &&
    parseColor(settings.outlineColor) !== undefined &&
    parseColor(settings.backgroundColor) !== undefined
  );
}

function parseColor(value: string):
  | {
      css: string;
      hex: string;
      red: number;
      green: number;
      blue: number;
    }
  | undefined {
  const trimmed = value.trim();

  if (HEX_COLOR.test(trimmed)) {
    const hex = expandHex(trimmed);
    return {
      css: hex,
      hex,
      ...hexToRgb(hex),
    };
  }

  const rgbMatch = trimmed.match(RGB_COLOR);
  if (!rgbMatch) {
    return undefined;
  }

  const red = Number(rgbMatch[1]);
  const green = Number(rgbMatch[2]);
  const blue = Number(rgbMatch[3]);

  if ([red, green, blue].some((channel) => channel < 0 || channel > 255)) {
    return undefined;
  }

  return {
    css: `rgb(${red}, ${green}, ${blue})`,
    hex: rgbToHex(red, green, blue),
    red,
    green,
    blue,
  };
}

function expandHex(value: string): string {
  const hex = value.toLowerCase();

  if (hex.length === 7) {
    return hex;
  }

  return `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}`;
}

function hexToRgb(hex: string) {
  return {
    red: Number.parseInt(hex.slice(1, 3), 16),
    green: Number.parseInt(hex.slice(3, 5), 16),
    blue: Number.parseInt(hex.slice(5, 7), 16),
  };
}

function rgbToHex(red: number, green: number, blue: number): string {
  return `#${toHex(red)}${toHex(green)}${toHex(blue)}`;
}

function toHex(value: number): string {
  return value.toString(16).padStart(2, "0");
}
