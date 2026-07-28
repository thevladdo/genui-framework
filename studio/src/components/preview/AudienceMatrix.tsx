/**
 * Audience matrix: can preview a draft with the samw component.
 */

import { useEffect, useState } from 'react';
import {
  ComponentRenderer,
  GenUIDisclosureNotice,
  GenUISection,
  noticeComesFirst,
  parseDisclosure,
  type GenUIComponent,
  type GenUITheme,
} from 'genui-framework';
import studioStyles from '../studio/Studio.module.css';
import styles from './Preview.module.css';
import { getTenantTheme, renderZone } from '../../lib/api';
import { genUIThemeFromTokens } from '../../lib/theme';
import {
  buildRenderProfile,
  isFallbackRender,
  sanitizationCount,
  segmentKey,
  toSanitizationReport,
  type Engagement,
  type PreviewRenderResponse,
  type RenderProfile,
  type SegmentInput,
} from '../../lib/segment';
import type { AdminSession } from '../../lib/session';

const USER_TYPES = ['explorer', 'focused', 'scanner', 'deep_reader', 'casual'] as const;
const ENGAGEMENTS: Engagement[] = ['low', 'mid', 'high'];
const MAX_SEGMENTS = 4;

interface SegmentDraft {
  id: number;
  role: string;
  interests: string;
  userType: string;
  engagement: Engagement | '';
}

const PRESETS: Array<Omit<SegmentDraft, 'id'>> = [
  { role: 'developer', interests: 'ai, devtools', userType: 'deep_reader', engagement: 'high' },
  { role: 'marketing manager', interests: 'analytics', userType: 'scanner', engagement: 'low' },
  { role: '', interests: '', userType: '', engagement: '' },
];

const toInput = (draft: SegmentDraft): SegmentInput => ({
  role: draft.role,
  interests: draft.interests.split(',').map((i) => i.trim()).filter(Boolean),
  userType: draft.userType,
  engagement: draft.engagement,
});

type ColumnResult = { response: PreviewRenderResponse } | { error: string };

const ColumnRender = ({
  response,
  theme,
}: {
  response: PreviewRenderResponse;
  theme?: GenUITheme;
}) => {
  const report = toSanitizationReport(response.meta);
  const removed = sanitizationCount(report);
  const fallback = isFallbackRender(response.meta);
  const cache = response.meta?.cache;
  // The preview claims to show what the visitor is served, so it shows
  // the notice the visitor gets: this render's own marking decides
  // whether there is one at all (a pinned-only fallback is not
  // generated and carries none), and the tenant's saved theme decides
  // its wording and placement.
  const disclosure = parseDisclosure(response.meta?.disclosure);
  const noticePosition = theme?.disclosurePosition ?? 'above-left';
  const notice =
    disclosure?.aiGenerated && theme?.disclosureEnabled !== 'off' ? (
      <GenUIDisclosureNotice
        text={theme?.disclosureText}
        position={noticePosition}
      />
    ) : null;
  const noticeFirst = noticeComesFirst(noticePosition);

  const sanitizationRows: Array<{ label: string; items: string[] }> = [
    { label: 'URLs removed', items: report.removedUrls },
    { label: 'Components dropped', items: report.droppedComponents },
    { label: 'Numbers ungrounded', items: report.removedNumbers },
    { label: 'Policy violations', items: report.policyViolations },
  ].filter((row) => row.items.length > 0);

  return (
    <>
      {fallback && (
        <p className={styles.warnBanner} role="alert">
          Pinned-only fallback: the backend could not run a generation
          (LLM engine missing or failing). This is NOT what GenUI
          produces when configured. Check LLM_PROVIDER and the engine
          key on the backend, then render again.
        </p>
      )}

      <div className={styles.canvas}>
        {response.components.length > 0 ? (
          <GenUISection theme={theme}>
            {noticeFirst && notice}
            <ComponentRenderer
              components={response.components as unknown as GenUIComponent[]}
            />
            {!noticeFirst && notice}
          </GenUISection>
        ) : (
          <p className={styles.emptyNote}>
            No components came back for this audience (nothing generated,
            or everything was removed by the guarantee chain below).
          </p>
        )}
      </div>

      <div className={styles.metaList}>
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>Cache</span>
          <span className={styles.metaValue}>
            {cache?.status ?? 'unknown'} · strategy {cache?.strategy ?? 'unknown'}
            {cache?.status === 'bypass' && ', live generation, not written to the segment cache'}
          </span>
        </div>
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>Personalized</span>
          <span className={styles.metaValue}>
            {response.personalization_applied ? 'yes' : 'no'}
          </span>
        </div>
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>Disclosure</span>
          <span className={styles.metaValue}>
            {disclosure
              ? `${disclosure.aiGenerated ? 'AI-generated' : 'not generated'} · ${disclosure.provenance}${
                  disclosure.generatedAt ? ` · generated ${disclosure.generatedAt}` : ''
                }`
              : 'no marking in the payload (GENUI_DISCLOSURE_OFF, or an older backend)'}
          </span>
        </div>
        {typeof response.meta?.confidence === 'number' && (
          <div className={styles.metaRow}>
            <span className={styles.metaLabel}>Confidence</span>
            <span className={styles.metaValue}>{response.meta.confidence}</span>
          </div>
        )}
        <div className={styles.metaRow}>
          <span className={styles.metaLabel}>Guarantees</span>
          {removed === 0 ? (
            <span className={`${styles.metaValue} ${styles.sanitClean}`}>
              nothing removed by the guarantee chain
            </span>
          ) : (
            <span className={styles.metaValue}>
              {removed} item{removed === 1 ? '' : 's'} removed before serving
            </span>
          )}
        </div>
        {sanitizationRows.map((row) => (
          <div className={styles.metaRow} key={row.label}>
            <span className={styles.metaLabel}>{row.label}</span>
            <ul className={styles.sanitList}>
              {row.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
};

export interface AudienceMatrixProps {
  session: AdminSession;
  buildPayload: (profile: RenderProfile) => Record<string, unknown>;
}

export const AudienceMatrix = ({ session, buildPayload }: AudienceMatrixProps) => {
  const [drafts, setDrafts] = useState<SegmentDraft[]>(
    PRESETS.map((preset, i) => ({ id: i, ...preset })),
  );
  const [nextId, setNextId] = useState(PRESETS.length);
  const [results, setResults] = useState<Record<number, ColumnResult>>({});
  const [busy, setBusy] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [tenantTheme, setTenantTheme] = useState<GenUITheme | null>(null);

  useEffect(() => {
    let current = true;
    getTenantTheme(session)
      .then((stored) => {
        if (current && stored.theme) setTenantTheme(genUIThemeFromTokens(stored.theme));
      })
      .catch(() => undefined);
    return () => { current = false; };
  }, [session]);

  const patchDraft = (id: number, patch: Partial<SegmentDraft>) =>
    setDrafts((current) =>
      current.map((d) => (d.id === id ? { ...d, ...patch } : d)),
    );

  const addDraft = () => {
    setDrafts((current) => [
      ...current,
      { id: nextId, role: '', interests: '', userType: '', engagement: '' },
    ]);
    setNextId((n) => n + 1);
  };

  const removeDraft = (id: number) => {
    setDrafts((current) => current.filter((d) => d.id !== id));
    setResults(({ [id]: _dropped, ...rest }) => rest);
  };

  const onRender = async () => {
    setConfigError(null);

    let payloads: Array<[number, Record<string, unknown>]>;
    try {
      payloads = drafts.map((draft) => [
        draft.id,
        buildPayload(buildRenderProfile(toInput(draft))),
      ]);
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : 'Invalid zone config');
      return;
    }

    setBusy(true);
    const entries = await Promise.all(
      payloads.map(async ([id, payload]): Promise<[number, ColumnResult]> => {
        try {
          return [id, { response: await renderZone(session, payload) }];
        } catch (e) {
          return [id, { error: e instanceof Error ? e.message : 'Render failed' }];
        }
      }),
    );
    setResults(Object.fromEntries(entries));
    setBusy(false);
  };

  return (
    <>
      <div className={styles.renderRow}>
        <button
          type="button"
          className={studioStyles.primaryButton}
          disabled={busy}
          onClick={() => void onRender()}
        >
          {busy ? 'Rendering…' : `Render ${drafts.length} audience${drafts.length === 1 ? '' : 's'} →`}
        </button>
        {drafts.length < MAX_SEGMENTS && (
          <button type="button" className={styles.removeBtn} onClick={addDraft}>
            + Add audience
          </button>
        )}
        <span className={styles.themeNote}>
          {tenantTheme
            ? `Rendered with the theme saved for ${session.tenant}`
            : `No theme saved for ${session.tenant}: library defaults`}
        </span>
      </div>

      {configError && <p className={studioStyles.error} role="alert">{configError}</p>}

      <div className={styles.rows}>
        {drafts.map((draft) => {
          const key = segmentKey(toInput(draft));
          const result = results[draft.id];
          return (
            <section className={`st-glass ${styles.row}`} key={draft.id}>
              <header className={styles.colHead}>
                <span className={styles.keyChip} title="Segment key this audience falls into, computed like the backend segmenter">
                  {key === 'anon' ? 'anon (no signals)' : key}
                </span>
                {drafts.length > 1 && (
                  <button
                    type="button"
                    className={styles.removeBtn}
                    onClick={() => removeDraft(draft.id)}
                  >
                    Remove
                  </button>
                )}
              </header>

              <div className={styles.segFields}>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-role-${draft.id}`}>Role</label>
                  <input
                    id={`pv-role-${draft.id}`}
                    type="text"
                    className={studioStyles.field}
                    placeholder="e.g. developer"
                    value={draft.role}
                    onChange={(e) => patchDraft(draft.id, { role: e.target.value })}
                  />
                </div>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-int-${draft.id}`}>Interests (comma separated)</label>
                  <input
                    id={`pv-int-${draft.id}`}
                    type="text"
                    className={studioStyles.field}
                    placeholder="e.g. ai, sustainability"
                    value={draft.interests}
                    onChange={(e) => patchDraft(draft.id, { interests: e.target.value })}
                  />
                </div>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-type-${draft.id}`}>Browsing style</label>
                  <select
                    id={`pv-type-${draft.id}`}
                    className={studioStyles.field}
                    value={draft.userType}
                    onChange={(e) => patchDraft(draft.id, { userType: e.target.value })}
                  >
                    <option value="">Not set</option>
                    {USER_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={studioStyles.fieldLabel} htmlFor={`pv-eng-${draft.id}`}>Engagement</label>
                  <select
                    id={`pv-eng-${draft.id}`}
                    className={studioStyles.field}
                    value={draft.engagement}
                    onChange={(e) =>
                      patchDraft(draft.id, { engagement: e.target.value as Engagement | '' })
                    }
                  >
                    <option value="">Not set</option>
                    {ENGAGEMENTS.map((eng) => (
                      <option key={eng} value={eng}>{eng}</option>
                    ))}
                  </select>
                </div>
              </div>

              {result && 'error' in result && (
                <p className={studioStyles.error} role="alert">{result.error}</p>
              )}
              {result && 'response' in result && (
                <ColumnRender
                  response={result.response}
                  theme={tenantTheme ?? undefined}
                />
              )}
            </section>
          );
        })}
      </div>
    </>
  );
};
