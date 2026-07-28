/**
 * Sidebar controls: one control per theme token, plus the tenant bar.
 */

import { lazy, Suspense, useId, useRef, useState } from 'react';
import styles from './Playground.module.css';
import {
  DISCLOSURE_MAX_FONT_PX,
  DISCLOSURE_MIN_FONT_PX,
  DISCLOSURE_MIN_OPACITY,
  DISCLOSURE_POSITIONS,
  DISCLOSURE_STATES,
  DISCLOSURE_TEXT_MAX,
  FONT_OPTIONS,
  HEADING_WEIGHTS,
  MODES,
  RADIUS_FULL_PRESETS,
  RADIUS_LG_PRESETS,
  RADIUS_PRESETS,
  RADIUS_SM_PRESETS,
  SPACING_SCALES,
  type DisclosureEnabled,
  type DisclosurePosition,
  type SpacingScale,
  type StudioTheme,
  type ThemeMode,
} from '../../lib/theme';

const TenantThemePanel = import.meta.env.DEV
  ? lazy(() => import('./TenantThemePanel'))
  : null;

interface ToggleGroupProps {
  label: string;
  options: readonly string[];
  value: string;
  onChange: (value: string) => void;
  format?: (option: string) => string;
}

const ToggleGroup = ({ label, options, value, onChange, format }: ToggleGroupProps) => {
  const labelId = useId();
  const buttonsRef = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const delta =
      event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1
          : 0;
    if (delta === 0) return;
    event.preventDefault();
    const next = (index + delta + options.length) % options.length;
    onChange(options[next]);
    buttonsRef.current[next]?.focus();
  };

  return (
    <div className={styles.control}>
      <span id={labelId} className={styles.controlLabel}>{label}</span>
      <div role="radiogroup" aria-labelledby={labelId} className={styles.toggleGroup}>
        {options.map((option, index) => {
          const checked = option === value;
          return (
            <button
              key={option}
              ref={(el) => { buttonsRef.current[index] = el; }}
              type="button"
              role="radio"
              aria-checked={checked}
              tabIndex={checked ? 0 : -1}
              className={checked ? styles.toggleOn : styles.toggle}
              onClick={() => onChange(option)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              {format ? format(option) : option}
            </button>
          );
        })}
      </div>
    </div>
  );
};

interface BrandColorProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
}

const BrandColor = ({ label, value, onChange }: BrandColorProps) => {
  const id = useId();
  const [draft, setDraft] = useState<string | null>(null);

  const onHex = (raw: string) => {
    const v = raw.startsWith('#') || raw === '' ? raw : `#${raw}`;
    setDraft(v);
    if (/^#[0-9a-fA-F]{6}$/.test(v)) {
      onChange(v.toLowerCase());
      setDraft(null);
    }
  };

  return (
    <div className={styles.control}>
      <label htmlFor={id} className={styles.controlLabel}>
        {label}
        {value === '' && <span className={styles.unsetHint}>default</span>}
      </label>
      <div className={styles.colorRow}>
        <input
          id={id}
          type="color"
          value={value || '#16161a'}
          onChange={(e) => onChange(e.target.value)}
          className={styles.colorSwatch}
        />
        <input
          type="text"
          spellCheck={false}
          placeholder="unset"
          value={draft ?? value}
          onChange={(e) => onHex(e.target.value)}
          onBlur={() => setDraft(null)}
          aria-label={`${label} hex value`}
          className={styles.hexInput}
        />
        {value !== '' && (
          <button
            type="button"
            className={styles.resetButton}
            aria-label={`Reset ${label} to default`}
            onClick={() => { onChange(''); setDraft(null); }}
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
};

interface ControlsProps {
  theme: StudioTheme;
  onChange: (patch: Partial<StudioTheme>) => void;
  onSave: () => void;
  onLoad: (theme: StudioTheme) => void;
}

export const Controls = ({ theme, onChange, onSave, onLoad }: ControlsProps) => {
  const blurId = useId();
  const colorId = useId();
  const hexId = useId();
  const fontId = useId();
  const noticeId = useId();
  const noticePositionId = useId();
  const noticeSizeId = useId();
  const noticeOpacityId = useId();

  // The hex field tolerates partial typing; the theme only updates on
  // valid 6-digit values so the preview never receives garbage
  const [hexDraft, setHexDraft] = useState<string | null>(null);

  const onHexChange = (raw: string) => {
    const value = raw.startsWith('#') ? raw : `#${raw}`;
    setHexDraft(value);
    if (/^#[0-9a-fA-F]{6}$/.test(value)) {
      onChange({ accentColor: value.toLowerCase() });
      setHexDraft(null);
    }
  };

  return (
    <aside className={styles.sidebar} aria-label="Theme controls">
      <div className={styles.sidebarScroll}>
        <ToggleGroup
          label="Mode"
          options={MODES}
          value={theme.mode}
          onChange={(mode) => onChange({ mode: mode as ThemeMode })}
        />

        <ToggleGroup
          label="Corner radius"
          options={RADIUS_PRESETS}
          value={theme.borderRadius}
          onChange={(borderRadius) => onChange({ borderRadius })}
          format={(option) => option.replace('px', '')}
        />

        <details className={styles.detailsGroup}>
          <summary className={styles.detailsSummary}>Radius scale</summary>
          <ToggleGroup
            label="Small (chips, inputs)"
            options={RADIUS_SM_PRESETS}
            value={theme.radiusSm}
            onChange={(radiusSm) => onChange({ radiusSm })}
            format={(option) => option.replace('px', '')}
          />
          <ToggleGroup
            label="Large (panels, heroes)"
            options={RADIUS_LG_PRESETS}
            value={theme.radiusLg}
            onChange={(radiusLg) => onChange({ radiusLg })}
            format={(option) => option.replace('px', '')}
          />
          <ToggleGroup
            label="Pills & avatars"
            options={RADIUS_FULL_PRESETS}
            value={theme.radiusFull}
            onChange={(radiusFull) => onChange({ radiusFull })}
            format={(option) =>
              option === '999px' ? 'Pill' : option === '12px' ? 'Soft' : 'Square'
            }
          />
        </details>

        <div className={styles.control}>
          <label htmlFor={blurId} className={styles.controlLabel}>
            Blur amount
            <span className={styles.controlValue}>{theme.glassBlur}</span>
          </label>
          <input
            id={blurId}
            type="range"
            min={0}
            max={60}
            step={1}
            value={parseInt(theme.glassBlur, 10)}
            onChange={(event) => onChange({ glassBlur: `${event.target.value}px` })}
            className={styles.slider}
          />
        </div>

        <ToggleGroup
          label="Spacing scale"
          options={SPACING_SCALES}
          value={theme.spacingScale}
          onChange={(spacingScale) => onChange({ spacingScale: spacingScale as SpacingScale })}
        />

        <div className={styles.control}>
          <label htmlFor={colorId} className={styles.controlLabel}>Accent color</label>
          <div className={styles.colorRow}>
            <input
              id={colorId}
              type="color"
              value={theme.accentColor}
              onChange={(event) => onChange({ accentColor: event.target.value })}
              className={styles.colorSwatch}
            />
            <input
              id={hexId}
              type="text"
              spellCheck={false}
              value={hexDraft ?? theme.accentColor}
              onChange={(event) => onHexChange(event.target.value)}
              onBlur={() => setHexDraft(null)}
              aria-label="Accent color hex value"
              className={styles.hexInput}
            />
          </div>
        </div>

        <details className={styles.detailsGroup}>
          <summary className={styles.detailsSummary}>Brand colors</summary>
          <BrandColor
            label="Surface 1 (cards)"
            value={theme.surface1}
            onChange={(surface1) => onChange({ surface1 })}
          />
          <BrandColor
            label="Surface 2 (raised)"
            value={theme.surface2}
            onChange={(surface2) => onChange({ surface2 })}
          />
          <BrandColor
            label="Surface 3 (active)"
            value={theme.surface3}
            onChange={(surface3) => onChange({ surface3 })}
          />
          <BrandColor
            label="Text on accent"
            value={theme.textOnAccent}
            onChange={(textOnAccent) => onChange({ textOnAccent })}
          />
        </details>

        <div className={styles.control}>
          <label htmlFor={fontId} className={styles.controlLabel}>UI font</label>
          <select
            id={fontId}
            value={theme.fontFamily}
            onChange={(event) => onChange({ fontFamily: event.target.value })}
            className={styles.select}
          >
            {FONT_OPTIONS.map((font) => (
              <option key={font.label} value={font.stack}>
                {font.label}
              </option>
            ))}
          </select>
        </div>

        <ToggleGroup
          label="Heading weight"
          options={HEADING_WEIGHTS}
          value={theme.fontWeightHeading}
          onChange={(fontWeightHeading) => onChange({ fontWeightHeading })}
        />

        <div className={styles.control}>
          <span className={styles.controlLabel}>Code font</span>
          <span className={styles.fixedValue}>JetBrains Mono (fixed)</span>
        </div>

        <div className={styles.sectionHead}>AI Act &amp; GDPR</div>

        <ToggleGroup
          label="Disclosure notice"
          options={DISCLOSURE_STATES}
          value={theme.disclosureEnabled}
          onChange={(v) => onChange({ disclosureEnabled: v as DisclosureEnabled })}
          format={(option) => (option === 'on' ? 'Shown' : 'Hidden')}
        />

        <div className={styles.control}>
          <label htmlFor={noticeId} className={styles.controlLabel}>
            Wording
            {theme.disclosureText === '' && (
              <span className={styles.unsetHint}>default</span>
            )}
          </label>
          <input
            id={noticeId}
            type="text"
            className={styles.textField}
            maxLength={DISCLOSURE_TEXT_MAX}
            placeholder="AI-generated content"
            value={theme.disclosureText}
            onChange={(event) => onChange({ disclosureText: event.target.value })}
          />
        </div>

        <div className={styles.control}>
          <label htmlFor={noticePositionId} className={styles.controlLabel}>
            Position
          </label>
          <select
            id={noticePositionId}
            className={styles.select}
            value={theme.disclosurePosition}
            onChange={(event) =>
              onChange({
                disclosurePosition: event.target.value as DisclosurePosition,
              })
            }
          >
            {DISCLOSURE_POSITIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.control}>
          <label htmlFor={noticeSizeId} className={styles.controlLabel}>
            Text size
            <span className={styles.controlValue}>{theme.disclosureFontSize}</span>
          </label>
          <input
            id={noticeSizeId}
            type="range"
            min={DISCLOSURE_MIN_FONT_PX}
            max={DISCLOSURE_MAX_FONT_PX}
            step={1}
            value={parseInt(theme.disclosureFontSize, 10)}
            onChange={(event) =>
              onChange({ disclosureFontSize: `${event.target.value}px` })
            }
            className={styles.slider}
          />
        </div>

        <div className={styles.control}>
          <label htmlFor={noticeOpacityId} className={styles.controlLabel}>
            Opacity
            <span className={styles.controlValue}>
              {Math.round(Number(theme.disclosureOpacity) * 100)}%
            </span>
          </label>
          <input
            id={noticeOpacityId}
            type="range"
            min={DISCLOSURE_MIN_OPACITY * 100}
            max={100}
            step={5}
            value={Math.round(Number(theme.disclosureOpacity) * 100)}
            onChange={(event) =>
              onChange({
                disclosureOpacity: String(Number(event.target.value) / 100),
              })
            }
            className={styles.slider}
          />
        </div>

        <p className={styles.groupHint}>
          Zones showing AI-generated content carry this notice. It is on by
          default and saved with the theme, so every page of this tenant words
          it the same way. Hiding it means you inform the visitor somewhere
          else: the machine-readable marking stays either way. The sliders stop
          before the notice becomes unreadable, and its color follows the
          theme's secondary text so it stays legible in light and dark.
        </p>
      </div>

      {TenantThemePanel && (
        <Suspense fallback={null}>
          <TenantThemePanel theme={theme} onLoad={onLoad} />
        </Suspense>
      )}

      <button type="button" className={styles.saveButton} onClick={onSave}>
        Save →
      </button>
    </aside>
  );
};
