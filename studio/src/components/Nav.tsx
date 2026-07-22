/**
 * Top navigation.
 */

import { useEffect, useRef, useState } from 'react';
import styles from './Nav.module.css';
import type { RoutePath } from '../hooks/useHashRoute';

interface NavProps {
  path: RoutePath;
}

interface NavItem {
  path: RoutePath;
  label: string;
}

const PUBLIC_TABS: NavItem[] = [{ path: '/playground', label: 'Theme Playground' }];
const PUBLIC_TABS_AFTER: NavItem[] = [{ path: '/about', label: 'About' }];
const CONSOLE_ITEMS: NavItem[] = [
  { path: '/preview', label: 'Segment Preview' },
  { path: '/studio', label: 'Content Studio' },
  { path: '/measure', label: 'Measurement' },
];

const DisclosureIcon = ({ open }: { open: boolean }) => (
  <svg
    className={styles.disclosureIcon}
    viewBox="0 0 12 12"
    width="12"
    height="12"
    aria-hidden="true"
    data-open={open}
  >
    <path d="M1.5 6h9" />
    <path className={styles.disclosureIconV} d="M6 1.5v9" />
  </svg>
);

const BurgerIcon = ({ open }: { open: boolean }) => (
  <svg
    className={styles.burgerIcon}
    viewBox="0 0 18 14"
    width="18"
    height="14"
    aria-hidden="true"
    data-open={open}
  >
    <path className={styles.burgerTop} d="M1 2h16" />
    <path className={styles.burgerMid} d="M1 7h16" />
    <path className={styles.burgerBot} d="M1 12h16" />
  </svg>
);

const TabLink = ({ item, path, className }: { item: NavItem; path: RoutePath; className: string }) => (
  <a
    href={`#${item.path}`}
    className={className}
    aria-current={path === item.path ? 'page' : undefined}
  >
    {item.label}
  </a>
);

export const Nav = ({ path }: NavProps) => {
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const consoleRef = useRef<HTMLDivElement>(null);

  const inConsole = CONSOLE_ITEMS.some((item) => item.path === path);

  useEffect(() => {
    setConsoleOpen(false);
    setMobileOpen(false);
  }, [path]);

  useEffect(() => {
    if (!consoleOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!consoleRef.current?.contains(e.target as Node)) setConsoleOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [consoleOpen]);

  useEffect(() => {
    if (!consoleOpen && !mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setConsoleOpen(false);
        setMobileOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [consoleOpen, mobileOpen]);

  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [mobileOpen]);

  return (
    <header className={styles.nav}>
      <a href="#/" className={styles.wordmark}>
        GenUI <span>Studio</span>
      </a>

      <nav aria-label="Sections" className={styles.tabs}>
        {PUBLIC_TABS.map((item) => (
          <TabLink key={item.path} item={item} path={path} className={styles.tab} />
        ))}

        <div className={styles.consoleWrap} ref={consoleRef}>
          <button
            type="button"
            className={styles.consoleTrigger}
            aria-expanded={consoleOpen}
            aria-controls="nav-console-panel"
            aria-current={inConsole && !consoleOpen ? 'page' : undefined}
            onClick={() => setConsoleOpen((open) => !open)}
          >
            Console
            <DisclosureIcon open={consoleOpen} />
          </button>

          <div id="nav-console-panel" className={styles.consolePanel} data-open={consoleOpen}>
            {CONSOLE_ITEMS.map((item) => (
              <TabLink key={item.path} item={item} path={path} className={styles.consoleItem} />
            ))}
          </div>
        </div>

        {PUBLIC_TABS_AFTER.map((item) => (
          <TabLink key={item.path} item={item} path={path} className={styles.tab} />
        ))}
      </nav>

      <button
        type="button"
        className={styles.burger}
        aria-expanded={mobileOpen}
        aria-controls="nav-mobile-overlay"
        aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
        onClick={() => setMobileOpen((open) => !open)}
      >
        <BurgerIcon open={mobileOpen} />
      </button>

      <div id="nav-mobile-overlay" className={styles.mobileOverlay} data-open={mobileOpen}>
        <nav aria-label="All sections" className={styles.mobileList}>
          {[...PUBLIC_TABS, ...PUBLIC_TABS_AFTER].map((item) => (
            <TabLink key={item.path} item={item} path={path} className={styles.mobileItem} />
          ))}
          <div className={styles.mobileGroupLabel} aria-hidden="true">
          </div>
          {CONSOLE_ITEMS.map((item) => (
            <TabLink key={item.path} item={item} path={path} className={styles.mobileItem} />
          ))}
        </nav>
      </div>
    </header>
  );
};
