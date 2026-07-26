/**
 * The console entry on the homepage.
 */

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { CONSOLE_TOOLS } from '../lib/console';
import styles from './Home.module.css';

const DESCRIPTION = 'Six tools over one backend, one tenant at a time: curate it, govern it, prove it.';
const HINT_DEFAULT = 'Six tools over one backend, one tenant at a time.';

const TITLE_MS = 620;
const REVEAL_DELAY_MS = 440;

export const ConsoleCard = () => {
  const reducedMotion = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const firstToolRef = useRef<HTMLAnchorElement>(null);
  const openedByKeyboard = useRef(false);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
  }, []);

  useEffect(() => {
    if (!open) return;
    if (openedByKeyboard.current) firstToolRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const close = () => {
    setOpen(false);
    setActive(null);
    triggerRef.current?.focus();
  };

  const seconds = (ms: number) => (reducedMotion ? 0 : ms / 1000);
  const travel = {
    duration: seconds(TITLE_MS),
    ease: [0.22, 1, 0.36, 1] as const,
  };
  const reveal = {
    duration: seconds(280),
    delay: seconds(REVEAL_DELAY_MS),
  };

  const hint = CONSOLE_TOOLS.find((tool) => tool.path === active)?.blurb ?? HINT_DEFAULT;

  return (
    <motion.section
      className={`${styles.card} ${styles.artConsole}`}
      whileHover={reducedMotion || open ? undefined : { y: -6, scale: 1.015 }}
      transition={{ duration: open ? 0 : 0.25, ease: [0.4, 0, 0.2, 1] }}
      aria-labelledby="home-console-title"
    >
      <AnimatePresence initial={false}>
        {!open && (
          <motion.span
            key="tag"
            className={styles.cardTag}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: reveal }}
            exit={{ opacity: 0, transition: { duration: seconds(160) } }}
          >
            ADMIN · BACKEND REQUIRED
          </motion.span>
        )}
      </AnimatePresence>

      <div
        className={`${styles.consoleBody} ${open ? styles.consoleBodyOpen : ''}`}
      >
        <div className={styles.titleRow}>
          <span
            id="home-console-title"
            className={`st-display ${styles.consoleTitle} ${open ? styles.consoleTitleOpen : ''}`}
          >
            <motion.span layout className={styles.consoleWord} transition={travel}>
              Control
            </motion.span>{' '}
            <motion.span layout className={styles.consoleWord} transition={travel}>
              Console
            </motion.span>
          </span>

          {open && (
            <motion.button
              type="button"
              className={styles.consoleBack}
              onClick={close}
              aria-label="Back to the console card"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: reveal }}
            >
              ←
            </motion.button>
          )}
        </div>

        {open ? (
          <motion.div
            className={styles.consoleIndex}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: reveal }}
          >
            <nav className={styles.toolList} aria-label="Console tools">
              {CONSOLE_TOOLS.map((tool, index) => (
                <a
                  key={tool.path}
                  ref={index === 0 ? firstToolRef : undefined}
                  href={`#${tool.path}`}
                  className={styles.toolRow}
                  aria-label={`${tool.label}: ${tool.blurb}`}
                  data-pending={pending === tool.path ? '' : undefined}
                  onPointerEnter={() => setActive(tool.path)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(tool.path)}
                  onBlur={() => setActive(null)}
                  onClick={() => setPending(tool.path)}
                >
                  <span className={styles.toolName}>{tool.label}</span>
                  <span className={styles.toolMark} aria-hidden="true">
                    {pending === tool.path ? '•••' : '→'}
                  </span>
                </a>
              ))}
            </nav>

            <p className={hint === HINT_DEFAULT ? styles.toolHintDefault : styles.toolHint} aria-hidden="true">
              {hint}
            </p>
          </motion.div>
        ) : (
          <motion.span
            className={styles.cardDescription}
            initial={mounted.current ? { opacity: 0 } : false}
            animate={{ opacity: 1, transition: reveal }}
          >
            {DESCRIPTION}
          </motion.span>
        )}
      </div>

      {!open && (
        <>
          <button
            ref={triggerRef}
            type="button"
            className={styles.consoleTrigger}
            aria-labelledby="home-console-title"
            aria-expanded={false}
            onKeyDown={(e) => {
              openedByKeyboard.current = e.key === 'Enter' || e.key === ' ';
            }}
            onClick={() => setOpen(true)}
          />
          <span className={styles.cardArrow} aria-hidden="true">
            →
          </span>
        </>
      )}
    </motion.section>
  );
};
