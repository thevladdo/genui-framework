/**
 * Shell: hash router -> Home | Playground | Studio.
 *
 * StudioPage is React.lazy'd so the admin tooling (API client included)
 * ships as a separate chunk that public visitors never download; the
 * Playground stays in the main bundle because it IS the public product.
 */

import { lazy, Suspense, useEffect } from 'react';
import { About } from './components/about/About';
import { Home } from './components/Home';
import { LocalOnlyModal } from './components/LocalOnlyModal';
import { Nav } from './components/Nav';
import { PlaygroundPage } from './components/playground/PlaygroundPage';
import { useHashRoute } from './hooks/useHashRoute';
import SideRays from './components/side-rays/SideRays';
import DotGrid from './components/dot-grid/DotGrid';

// Content Studio and the Measurement dashboard need a backend + admin key,
// so they're gated to local dev until user auth (JWT) lands.
// `import.meta.env.DEV` is statically false in the production (GitHub
// Pages) build, so the branches are dead code and the dynamic imports are
// tree-shaken — the admin bundles never ship publicly.
const StudioPage = import.meta.env.DEV
  ? lazy(() => import('./components/studio/StudioPage'))
  : null;
const MeasurePage = import.meta.env.DEV
  ? lazy(() => import('./components/measure/MeasurePage'))
  : null;
const PreviewPage = import.meta.env.DEV
  ? lazy(() => import('./components/preview/PreviewPage'))
  : null;

const App = () => {
  const { path, query, replaceQuery, navigate } = useHashRoute();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [path]);
  const isSafari =
    typeof navigator !== 'undefined' &&
    /Safari/i.test(navigator.userAgent) &&
    !/(Chrome|Chromium|CriOS|FxiOS|Edg|OPR)/i.test(navigator.userAgent);

  const sideRaysProps = isSafari
    ? {
      speed: 2.5,
      rayColor1: '#EAB308',
      rayColor2: '#96c8ff',
      intensity: 0.5,
      spread: 1,
      origin: 'top-right' as const,
      tilt: 0,
      saturation: 1.5,
      blend: 0.75,
      falloff: 1.6,
      opacity: 0.5,
    }
    : {
      speed: 2.5,
      rayColor1: '#EAB308',
      rayColor2: '#96c8ff',
      intensity: 2,
      spread: 2,
      origin: 'top-right' as const,
      tilt: 0,
      saturation: 1.5,
      blend: 0.75,
      falloff: 1.6,
      opacity: 1,
    };

  return (
    <>
      <DotGrid
        dotSize={1}
        gap={50}
        baseColor="#ffffffbd"
        proximity={120}
        shockRadius={250}
        shockStrength={5}
        resistance={750}
        returnDuration={1.5}
      />

      <Nav path={path} />

      {path === '/' && (
        <>
          <SideRays {...sideRaysProps} />
          <Home />
        </>
      )}

      {path === '/about' && <About />}

      {path === '/playground' && (
        <PlaygroundPage query={query} replaceQuery={replaceQuery} />
      )}

      {path === '/studio' && (
        StudioPage ? (
          <Suspense fallback={<p style={{ padding: 32 }}>Loading Content Studio…</p>}>
            <StudioPage />
          </Suspense>
        ) : (
          // Public build: show the homepage with a "runs locally" modal over it
          <>
            <Home />
            <LocalOnlyModal onClose={() => navigate('/')} />
          </>
        )
      )}

      {path === '/preview' && (
        PreviewPage ? (
          <Suspense fallback={<p style={{ padding: 32 }}>Loading Segment Preview…</p>}>
            <PreviewPage />
          </Suspense>
        ) : (
          <>
            <Home />
            <LocalOnlyModal
              onClose={() => navigate('/')}
              title="Segment Preview runs locally"
              body="The Segment Preview renders zones live against your GenUI backend with an admin key, so for now it's available only when you run the studio on your own machine:"
            />
          </>
        )
      )}

      {path === '/measure' && (
        MeasurePage ? (
          <Suspense fallback={<p style={{ padding: 32 }}>Loading Measurement…</p>}>
            <MeasurePage />
          </Suspense>
        ) : (
          <>
            <Home />
            <LocalOnlyModal
              onClose={() => navigate('/')}
              title="Measurement runs locally"
              body="The Measurement dashboard reads uplift and cache statistics from your GenUI backend with an admin key, so for now it's available only when you run the studio on your own machine:"
            />
          </>
        )
      )}
    </>
  );
};

export default App;
