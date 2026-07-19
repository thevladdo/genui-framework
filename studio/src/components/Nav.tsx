/**
 * Top navigation: wordmark (home) + the two destinations as tabs.
 */

import styles from './Nav.module.css';
import type { RoutePath } from '../hooks/useHashRoute';

interface NavProps {
  path: RoutePath;
}

const TABS: Array<{ path: RoutePath; label: string }> = [
  { path: '/playground', label: 'Theme Playground' },
  { path: '/studio', label: 'Content Studio' },
  { path: '/measure', label: 'Measurement' },
];

export const Nav = ({ path }: NavProps) => (
  <header className={styles.nav}>
    <a href="#/" className={styles.wordmark}>
      GenUI <span>Studio</span>
    </a>

    <nav aria-label="Sections" className={styles.tabs}>
      {TABS.map((tab) => (
        <a
          key={tab.path}
          href={`#${tab.path}`}
          className={styles.tab}
          aria-current={path === tab.path ? 'page' : undefined}
        >
          {tab.label}
        </a>
      ))}
    </nav>
  </header>
);
