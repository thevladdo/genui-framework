/**
 * AI content disclosure: what a machine reads, and what a person reads.
 *
 * The backend marks every payload with what produced it. This module
 * turns that marking into the two things a page has to carry: standard
 * machine-readable markup a crawler or a third-party verifier can pick
 * up without calling our API, and the plain text a visitor reads.
 *
 * The vocabulary is not invented here. `digitalSourceType` and its
 * values come from the IPTC digital source type NewsCodes, the same
 * vocabulary C2PA uses, so a verifier that already understands
 * provenance metadata understands this without a GenUI-specific parser.
 *
 * Nothing here is signed. A C2PA manifest embedded in the HTML would be,
 * but a signature is only worth its certificate chain: that needs a
 * signing identity and key custody that belong to the deployment, not to
 * a React package. This markup is therefore a declaration, strippable by
 * whoever controls the page, not a proof.
 */

export type GenUIProvenance =
  | 'generated'
  | 'verbatim-from-input'
  | 'not-generated';

export interface GenUIDisclosure {
  /** Whether a model wrote this content */
  aiGenerated: boolean;
  /** Original prose, the input copied verbatim, or no model output at all */
  provenance: GenUIProvenance;
  /** When the content was generated (not when it was served) */
  generatedAt?: string;
  /** What produced it */
  system?: string;
  /** Model name, present only when the backend is set to expose it */
  model?: string;
}

/**
 * Where the notice sits around the content it describes: which side of
 * the content, and how the line is aligned on that side.
 */
export type GenUIDisclosurePosition =
  | 'above-left'
  | 'above-center'
  | 'above-right'
  | 'below-left'
  | 'below-center'
  | 'below-right';

export interface GenUIDisclosureOptions {
  /** Visible wording. The exact phrasing is the host's legal choice */
  text?: string;
  /** Where the notice sits relative to the zone content (default: 'above-left') */
  position?: GenUIDisclosurePosition;
}

/**
 * Whether the notice precedes the content in DOM order.
 *
 * Reading order follows visual order, so someone hearing the page gets
 * the notice at the point where it is shown, not always first or always
 * last. One place decides it, for every surface that renders a notice.
 */
export const noticeComesFirst = (position: GenUIDisclosurePosition): boolean =>
  position.startsWith('above');

/**
 * What a zone assumes before the backend has said anything.
 *
 * A zone about to show model output has to be marked from the first
 * paint, including server-side and while streaming, and at that point
 * the only honest assumption is the one that cannot under-disclose.
 */
export const PENDING_DISCLOSURE: GenUIDisclosure = {
  aiGenerated: true,
  provenance: 'generated',
};

export const DEFAULT_DISCLOSURE_TEXT = 'AI-generated content';

export const DEFAULT_CHAT_DISCLOSURE_TEXT =
  'You are chatting with an AI assistant. Responses are AI-generated.';

const IPTC_DIGITAL_SOURCE_TYPE =
  'https://cv.iptc.org/newscodes/digitalsourcetype/';

const SOURCE_TYPE_BY_PROVENANCE: Record<GenUIProvenance, string> = {
  'generated': 'trainedAlgorithmicMedia',
  'verbatim-from-input': 'compositeWithTrainedAlgorithmicMedia',
  'not-generated': 'algorithmicMedia',
};

/** Read the backend block; anything unreadable stays fully disclosed. */
export const parseDisclosure = (raw: unknown): GenUIDisclosure | undefined => {
  if (!raw || typeof raw !== 'object') return undefined;
  const value = raw as Record<string, unknown>;
  const aiGenerated = value.ai_generated !== false;
  const provenance = value.provenance as GenUIProvenance | undefined;
  return {
    aiGenerated,
    provenance:
      provenance ?? (aiGenerated ? 'generated' : 'not-generated'),
    generatedAt:
      typeof value.generated_at === 'string' ? value.generated_at : undefined,
    system: typeof value.system === 'string' ? value.system : undefined,
    model: typeof value.model === 'string' ? value.model : undefined,
  };
};

export const digitalSourceType = (provenance: GenUIProvenance): string =>
  IPTC_DIGITAL_SOURCE_TYPE +
  (SOURCE_TYPE_BY_PROVENANCE[provenance] ?? SOURCE_TYPE_BY_PROVENANCE.generated);

/**
 * JSON-LD for one zone, ready to put inside a <script> tag.
 *
 * `<` is escaped so no string coming from the content can close the
 * script element and turn provenance markup into an injection point.
 */
export const disclosureJsonLd = (
  disclosure: GenUIDisclosure,
  zoneId: string,
): string =>
  JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'CreativeWork',
    identifier: zoneId,
    digitalSourceType: digitalSourceType(disclosure.provenance),
    ...(disclosure.generatedAt ? { dateCreated: disclosure.generatedAt } : {}),
    ...(disclosure.model
      ? { creator: { '@type': 'SoftwareApplication', name: disclosure.model } }
      : {}),
  }).replace(/</g, '\\u003c');
