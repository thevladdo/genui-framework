/**
 * RouteVeil: the curtain page transition.
 */

import { useEffect, useRef, useState } from 'react';
import styles from './RouteVeil.module.css';

const IN_MS = 400;
const OUT_MS = 600;
const SAFETY_MS = 900;

type Phase = 'idle' | 'in' | 'out';

const normalize = (hash: string): string =>
  (hash.replace(/^#/, '').split('?')[0] || '/');

export const RouteVeil = () => {
  const [phase, setPhase] = useState<Phase>('idle');
  const busy = useRef(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

      const anchor = (e.target as Element).closest?.('a[href^="#/"]');
      if (!anchor || anchor.getAttribute('target') === '_blank') return;

      const href = anchor.getAttribute('href') ?? '';
      if (normalize(href) === normalize(window.location.hash)) return;

      if (busy.current) {
        e.preventDefault();
        return;
      }
      if (window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) {
        return;
      }

      e.preventDefault();
      busy.current = true;
      setPhase('in');

      timers.current.push(
        window.setTimeout(() => {
          let lowered = false;
          const lower = () => {
            if (lowered) return;
            lowered = true;
            window.removeEventListener('hashchange', onHash);
            setPhase('out');
            timers.current.push(
              window.setTimeout(() => {
                setPhase('idle');
                busy.current = false;
              }, OUT_MS),
            );
          };
          const onHash = () => {
            const settle = () => {
              requestAnimationFrame(() => {
                if (lowered) return;
                if (document.querySelector('[data-route-loading]')) {
                  settle();
                  return;
                }
                requestAnimationFrame(lower);
              });
            };
            settle();
          };
          window.addEventListener('hashchange', onHash);
          timers.current.push(window.setTimeout(lower, SAFETY_MS));
          window.location.hash = href.slice(1);
        }, IN_MS),
      );
    };

    document.addEventListener('click', onClick);
    return () => {
      document.removeEventListener('click', onClick);
      timers.current.forEach(clearTimeout);
    };
  }, []);

  return <div className={styles.veil} data-phase={phase} aria-hidden="true" />;
};
