/**
 * Theme Playground page: sidebar controls + live preview.
 */

import { useCallback, useEffect, useState } from 'react';
import styles from './Playground.module.css';
import { Controls } from './Controls';
import { ExportPanel } from './ExportPanel';
import { Preview } from './Preview';
import { themeFromQuery, themeToQuery, type StudioTheme } from '../../lib/theme';

interface PlaygroundPageProps {
  query: string;
  replaceQuery: (query: string) => void;
}

export const PlaygroundPage = ({ query, replaceQuery }: PlaygroundPageProps) => {
  const [theme, setTheme] = useState<StudioTheme>(() => themeFromQuery(query));
  const [exportOpen, setExportOpen] = useState(false);

  // The URL is an external source too (share links, back/forward): re-sync
  // state when the query changes from outside.
  useEffect(() => {
    setTheme((current) => {
      const fromUrl = themeFromQuery(query);
      return themeToQuery(fromUrl) === themeToQuery(current) ? current : fromUrl;
    });
  }, [query]);

  const onChange = useCallback(
    (patch: Partial<StudioTheme>) => {
      setTheme((current) => {
        const next = { ...current, ...patch };
        replaceQuery(themeToQuery(next));
        return next;
      });
    },
    [replaceQuery],
  );

  return (
    <main className={styles.page}>
      <Controls theme={theme} onChange={onChange} onSave={() => setExportOpen(true)} />
      <Preview theme={theme} />
      {exportOpen && <ExportPanel theme={theme} onClose={() => setExportOpen(false)} />}
    </main>
  );
};

export default PlaygroundPage;
