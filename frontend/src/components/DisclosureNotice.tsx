/**
 * The AI content notice a person reads.
 *
 * Lives outside GenUIZone because the zone is not the only way generated
 * content reaches a page: a host that drives `useZone` and renders the
 * components itself, or a tool that previews a render, shows the same
 * content and owes the same information. Same component, same class,
 * same `--genui-*` tokens, so it cannot drift into a second look.
 *
 * Plain text in the document flow: nothing is carried by color alone,
 * nothing is hidden from assistive technology, and it is announced in
 * reading order like any other paragraph.
 */

import React from 'react';
import {
  DEFAULT_DISCLOSURE_TEXT,
  type GenUIDisclosurePosition,
} from '../utils/disclosure';

export interface GenUIDisclosureNoticeProps {
  /** Visible wording. The exact phrasing is a legal choice, so it is yours */
  text?: string;
  /**
   * Which side of the content it sits on and how it is aligned there
   * (default: 'above-left'). The class carries both.
   */
  position?: GenUIDisclosurePosition;
  className?: string;
}

export const GenUIDisclosureNotice: React.FC<GenUIDisclosureNoticeProps> = ({
  text = DEFAULT_DISCLOSURE_TEXT,
  position = 'above-left',
  className = '',
}) => (
  <p
    className={`genui-zone__disclosure genui-zone__disclosure--${position} ${className}`.trim()}
  >
    {text}
  </p>
);

export default GenUIDisclosureNotice;
