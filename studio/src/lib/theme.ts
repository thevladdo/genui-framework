/**
 * Theme model for the Playground.
 *
 * The studio's theme state is a strict subset of the library's GenUITheme
 * using the SAME canonical token names: URL serialization, TS/CSS/JSON
 * exports and the <GenUISection theme> prop share one vocabulary, so a
 * shared link IS a valid config and vice versa.
 *
 * Every token in this model has a control in the sidebar. That is the
 * contract: a token without a control "exists only on paper".
 *
 * URL parsing is whitelist-based: every key has its own validator and
 * anything unrecognized is silently dropped.
 *
 * Brand-color keys (surface1/2/3, textOnAccent) use '' = "unset": nothing
 * is emitted, the library defaults (or the mode block) win.
 */

import type { GenUITheme } from "genui-framework";

export type SpacingScale = "sm" | "base" | "lg";
export type ThemeMode = "dark" | "light";

export interface StudioTheme {
  mode: ThemeMode;
  borderRadius: string;
  radiusSm: string;
  radiusLg: string;
  radiusFull: string;
  glassBlur: string;
  spacingScale: SpacingScale;
  accentColor: string;
  fontFamily: string;
  fontWeightHeading: string;
  surface1: string;
  surface2: string;
  surface3: string;
  textOnAccent: string;
}

export const RADIUS_PRESETS = ["0px", "12px", "24px", "32px", "64px"] as const;
export const RADIUS_SM_PRESETS = ["0px", "8px", "12px", "16px"] as const;
export const RADIUS_LG_PRESETS = ["16px", "24px", "32px", "48px"] as const;
export const RADIUS_FULL_PRESETS = ["999px", "12px", "0px"] as const;
export const SPACING_SCALES: SpacingScale[] = ["sm", "base", "lg"];
export const MODES: ThemeMode[] = ["dark", "light"];
export const HEADING_WEIGHTS = ["400", "600", "700", "800"] as const;

/** Selectable UI fonts: label shown in the select -> CSS font stack */
const SYSTEM_FONT =
  "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

export const FONT_OPTIONS: ReadonlyArray<{ label: string; stack: string }> = [
  // 'inherit' emits --genui-font-family: inherit -> components take the
  // HOST page's typography (enterprise brand guidelines win)
  { label: "Inherit (host font)", stack: "inherit" },
  { label: "System UI", stack: SYSTEM_FONT },
  { label: "Inter", stack: "'Inter', system-ui, sans-serif" },
  { label: "Geist", stack: "'Geist Sans', system-ui, sans-serif" },
  {
    label: "JetBrains Mono",
    stack: "'JetBrains Mono', ui-monospace, monospace",
  },
];

export const DEFAULT_STUDIO_THEME: StudioTheme = {
  mode: "dark",
  borderRadius: "24px",
  radiusSm: "12px",
  radiusLg: "32px",
  radiusFull: "999px",
  glassBlur: "20px",
  spacingScale: "base",
  accentColor: "#3b82f6",
  fontFamily: SYSTEM_FONT,
  fontWeightHeading: "700",
  surface1: "",
  surface2: "",
  surface3: "",
  textOnAccent: "",
};

// Mirrors the spacing math in the library's GenUISection so the CSS
// export matches exactly what the live preview renders
const SPACING_BASE: Record<string, number> = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  "2xl": 48,
};
const SPACING_FACTORS: Record<SpacingScale, number> = {
  sm: 0.75,
  base: 1,
  lg: 1.25,
};

// Validation
const isPx = (value: string, max: number): boolean => {
  const match = /^(\d{1,3})px$/.exec(value);
  return match !== null && Number(match[1]) <= max;
};

const isHex = (value: string): boolean => /^#[0-9a-fA-F]{6}$/.test(value);

// '' is valid for optional brand colors
const isOptionalHex = (value: string): boolean => value === "" || isHex(value);

const VALIDATORS: { [K in keyof StudioTheme]: (v: string) => boolean } = {
  mode: (v) => (MODES as string[]).includes(v),
  borderRadius: (v) => isPx(v, 128),
  radiusSm: (v) => isPx(v, 64),
  radiusLg: (v) => isPx(v, 128),
  radiusFull: (v) => isPx(v, 999),
  glassBlur: (v) => isPx(v, 60),
  spacingScale: (v) => (SPACING_SCALES as string[]).includes(v),
  accentColor: isHex,
  fontFamily: (v) => FONT_OPTIONS.some((f) => f.stack === v),
  fontWeightHeading: (v) => (HEADING_WEIGHTS as readonly string[]).includes(v),
  surface1: isOptionalHex,
  surface2: isOptionalHex,
  surface3: isOptionalHex,
  textOnAccent: isOptionalHex,
};

// URL share link serialization
export const themeToQuery = (theme: StudioTheme): string => {
  const params = new URLSearchParams();
  (Object.keys(VALIDATORS) as Array<keyof StudioTheme>).forEach((key) => {
    if (theme[key] !== DEFAULT_STUDIO_THEME[key]) {
      params.set(key, theme[key]);
    }
  });
  return params.toString();
};

export const themeFromQuery = (query: string): StudioTheme => {
  const params = new URLSearchParams(query);
  const theme: StudioTheme = { ...DEFAULT_STUDIO_THEME };

  (Object.keys(VALIDATORS) as Array<keyof StudioTheme>).forEach((key) => {
    const raw = params.get(key);
    if (raw !== null && VALIDATORS[key](raw)) {
      (theme as unknown as Record<string, string>)[key] = raw;
    }
  });

  return theme;
};

// Bridges
export const toGenUITheme = (theme: StudioTheme): GenUITheme => {
  const result: GenUITheme = {
    mode: theme.mode,
    borderRadius: theme.borderRadius,
    radiusSm: theme.radiusSm,
    radiusLg: theme.radiusLg,
    radiusFull: theme.radiusFull,
    glassBlur: theme.glassBlur,
    spacingScale: theme.spacingScale,
    accentColor: theme.accentColor,
    fontFamily: theme.fontFamily,
    fontWeightHeading: theme.fontWeightHeading,
  };
  if (theme.surface1) result.surface1 = theme.surface1;
  if (theme.surface2) result.surface2 = theme.surface2;
  if (theme.surface3) result.surface3 = theme.surface3;
  if (theme.textOnAccent) result.textOnAccent = theme.textOnAccent;
  return result;
};

// Exports
export const exportAsTS = (theme: StudioTheme): string => {
  const entries = Object.entries(toGenUITheme(theme)).map(
    ([key, value]) => `  ${key}: ${JSON.stringify(value)},`,
  );
  return [
    "import type { GenUITheme } from 'genui-framework';",
    "",
    "export const genuiTheme: GenUITheme = {",
    ...entries,
    "};",
    "",
  ].join("\n");
};

export const exportAsCSS = (theme: StudioTheme): string => {
  const factor = SPACING_FACTORS[theme.spacingScale];
  const lines = [
    `  --genui-border-radius: ${theme.borderRadius};`,
    `  --genui-border-radius-sm: ${theme.radiusSm};`,
    `  --genui-border-radius-lg: ${theme.radiusLg};`,
    `  --genui-radius-full: ${theme.radiusFull};`,
    `  --genui-glass-blur: ${theme.glassBlur};`,
    `  --genui-accent-color: ${theme.accentColor};`,
    `  --genui-font-family: ${theme.fontFamily};`,
    `  --genui-font-weight-heading: ${theme.fontWeightHeading};`,
    ...Object.entries(SPACING_BASE).map(
      ([step, px]) =>
        `  --genui-spacing-${step}: ${Math.round(px * factor)}px;`,
    ),
  ];
  if (theme.surface1) lines.push(`  --genui-surface-1: ${theme.surface1};`);
  if (theme.surface2) lines.push(`  --genui-surface-2: ${theme.surface2};`);
  if (theme.surface3) lines.push(`  --genui-surface-3: ${theme.surface3};`);
  if (theme.textOnAccent)
    lines.push(`  --genui-text-on-accent: ${theme.textOnAccent};`);

  const hint =
    theme.mode === "light"
      ? '/* Light mode: add data-theme="light" to your GenUISection wrapper (or pass mode: "light" in the theme prop) */\n'
      : "";

  return `${hint}:root {\n${lines.join("\n")}\n}\n`;
};

export const exportAsJSON = (theme: StudioTheme): string =>
  JSON.stringify(toGenUITheme(theme), null, 2) + "\n";

export const isLightColor = (hex: string): boolean => {
  const match = /^#([0-9a-fA-F]{6})$/.exec(hex);
  if (!match) return false;
  const n = parseInt(match[1], 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const luminance =
    0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  return luminance > 0.55;
};
