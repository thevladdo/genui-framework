import { gsap } from 'gsap';
import { CustomEase } from 'gsap/CustomEase';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type MouseEvent } from 'react';
import { markIntroSeen } from '../../lib/intro';
import { TransformBeams } from '../about/TransformBeams';
import GradientText from '../gradient-text/GradientText';
import styles from './IntroVideo.module.css';
import bannerImg from './media/banner.webp';
import contentImg from './media/content.webp';
import measureImg from './media/measure.webp';
import pgBlueImg from './media/pg-dark_blue_r12.webp';
import pgVioletImg from './media/pg-dark_violet_r32.webp';
import pgLightImg from './media/pg-light_violet_r32.webp';

gsap.registerPlugin(CustomEase);
CustomEase.create('studio', 'M0,0 C0.4,0 0.2,1 1,1');
CustomEase.create('cssInOut', 'M0,0 C0.42,0 0.58,1 1,1');
CustomEase.create('veilIn', 'M0,0 C0.32,0 0.67,0 1,1');
CustomEase.create('veilOut', 'M0,0 C0.33,1 0.68,1 1,1');

const E = 'studio';
const PURPLE = ['#a855f7', '#6366f1', '#c084fc', '#a855f7'];
const VEIL_IN_MS = 400;
const VEIL_OUT_MS = 600;
const START_DELAY = 0.5;
const FIRST_HOLD = 2;
const PROOF_EXTRA = 1.5;
const STAGE_FIT = 0.82;
const SCENE_AIR = 0.85;
const AIR: CSSProperties = { scale: String(SCENE_AIR), transformOrigin: '50% 50%' };
const aired = (x: number, y: number) => ({ x: 960 + (x - 960) * SCENE_AIR, y: 540 + (y - 540) * SCENE_AIR });

const W_PATH = 'M0 60 L 344 60';
const OUT: Record<Strand, string> = {
  v: 'M-6 60 C 110 60, 180 30, 290 22 C 350 17, 388 15, 420 12',
  i: 'M-6 60 C 150 60, 300 58, 420 57',
  t: 'M-6 60 C 110 60, 180 90, 290 98 C 350 103, 388 105, 420 108',
};
const OUT_DELAY: Record<Strand, number> = { v: 1.05, i: 1.18, t: 1.31 };
const OUT_V: Record<Strand, number> = { v: 12, i: 57, t: 108 };
const STRANDS = ['v', 'i', 't'] as const;
type Strand = (typeof STRANDS)[number];
const SEG_RGB: Record<Strand, string> = { v: '168, 85, 247', i: '129, 132, 255', t: '6, 212, 202' };

const mapPath = (d: string, ox: number, oy: number, sx: number, sy: number) => {
  let n = 0;
  return d.replace(/-?\d+(\.\d+)?/g, (m) => {
    const v = parseFloat(m);
    return (n++ % 2 === 0 ? ox + v * sx : oy + v * sy).toFixed(2);
  });
};

const rotate = (d: string, cx: number, oy: number, su: number, sv: number) => {
  const nums = d.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
  const pts: string[] = [];
  for (let k = 0; k < nums.length; k += 2) {
    pts.push(`${(cx + (nums[k + 1] - 60) * sv).toFixed(2)} ${(oy + nums[k] * su).toFixed(2)}`);
  }
  let p = 0;
  return d.replace(/-?\d+(\.\d+)?[ ,]+-?\d+(\.\d+)?/g, () => pts[p++]);
};

const gridDotsNear = (x: number, y: number, r: number) => {
  const wrap = document.querySelector('.dot-grid__wrap');
  if (!wrap) return [];
  const box = wrap.getBoundingClientRect();
  const cell = 41;
  const cols = Math.floor((box.width + 40) / cell);
  const rows = Math.floor((box.height + 40) / cell);
  const startX = box.left + (box.width - (cell * cols - 40)) / 2 + 0.5;
  const startY = box.top + (box.height - (cell * rows - 40)) / 2 + 0.5;
  const out: Array<{ x: number; y: number; d: number }> = [];
  const i0 = Math.max(0, Math.floor((x - r - startX) / cell));
  const j0 = Math.max(0, Math.floor((y - r - startY) / cell));
  for (let i = i0; i <= Math.min(cols - 1, i0 + Math.ceil((2 * r) / cell) + 1); i++) {
    for (let j = j0; j <= Math.min(rows - 1, j0 + Math.ceil((2 * r) / cell) + 1); j++) {
      const dx = startX + i * cell;
      const dy = startY + j * cell;
      const d = Math.hypot(dx - x, dy - y);
      if (d <= r) out.push({ x: dx, y: dy, d });
    }
  }
  return out;
};

const shock = (el: Element | null, at: 'left' | 'top' | 'center' = 'left') => {
  if (!el) return;
  const b = el.getBoundingClientRect();
  const clientX = at === 'left' ? b.left : b.left + b.width / 2;
  const clientY = at === 'top' ? b.top : b.top + b.height / 2;
  window.dispatchEvent(new window.MouseEvent('click', { clientX, clientY }));
};

const at = (left: number, top: number, width?: number, height?: number, extra: CSSProperties = {}): CSSProperties => ({
  left,
  top,
  width,
  height,
  ...extra,
});

type Block = [number, number, number, number, boolean?, CSSProperties?];
const Blocks = ({ list }: { list: Block[] }) => (
  <>
    {list.map(([l, t, w, h, light, extra], k) => (
      <div key={k} className={light ? styles.blkL : styles.blk} style={at(l, t, w, h, extra)} />
    ))}
  </>
);

const CHECK = (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="#22c55e" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const GENERIC_PAGE: Block[] = [
  [36, 34, 90, 16, true], [330, 34, 44, 16, true], [388, 34, 44, 16, true], [446, 34, 40, 16, true],
  [36, 90, 448, 180], [64, 130, 250, 26, true], [64, 172, 190, 18, true],
  [36, 296, 138, 150], [191, 296, 138, 150], [346, 296, 138, 150],
  [36, 476, 150, 44, true, { borderRadius: 999 }],
];
const GENERIC_SMALL: Block[] = [
  [24, 22, 70, 10, true], [24, 50, 432, 92], [24, 156, 132, 88], [174, 156, 132, 88], [324, 156, 132, 88],
];

const Lockup = ({ size }: { size: number }) => (
  <div className={styles.lockup} style={size === 1 ? undefined : { fontSize: size }}>
    <img src="./GenUI_Logo.png" alt="" style={{ height: `${1.65 * size}${size === 1 ? 'em' : 'px'}`, marginRight: `${0.82 * size}${size === 1 ? 'em' : 'px'}` }} />
    <b>GenUI</b>
    <span>Studio</span>
  </div>
);

const PersonaCards = () => {
  const cards = [
    { k: 'v', tag: 'Developer', title: 'Documentation' },
    { k: 'i', tag: 'Investor', title: 'The numbers' },
    { k: 't', tag: 'Buyer', title: 'The offer' },
  ];
  return (
    <>
      {cards.map((c, n) => (
        <div key={c.k} data-a={`p-${c.k}`} className={`${styles.abs} ${styles.glass}`} style={at(1250, 345 + n * 210, 520, 170)}>
          <span className={`${styles.tag} ${styles.pcardTag}`}>{c.tag}</span>
          <span className={styles.pcardTitle}>{c.title}</span>
          {c.k === 'v' && (
            <>
              <div data-fill className={styles.blk} style={at(24, 112, 300, 38, { background: 'rgba(255,255,255,.05)' })} />
              <div data-fill className={styles.blkL} style={at(38, 122, 180, 6, { background: 'rgba(99,102,241,.7)' })} />
              <div data-fill className={styles.blkL} style={at(38, 136, 120, 6)} />
            </>
          )}
          {c.k === 'i' &&
            [22, 34, 46, 56].map((h, b) => (
              <div key={h} data-fill className={styles.blk} style={at(28 + b * 34, 150 - h, 24, h, { borderRadius: 4, background: `rgba(168,85,247,${0.45 + b * 0.12})` })} />
            ))}
          {c.k === 't' && (
            <div data-fill className={styles.blk} style={at(24, 110, 130, 40, { background: 'rgba(6,212,202,.14)', border: '1px solid rgba(6,212,202,.4)' })} />
          )}
          <div data-fill className={styles.pbtn} style={c.k === 't' ? { background: 'rgba(255,255,255,.85)' } : undefined} />
        </div>
      ))}
    </>
  );
};

const Landscape = ({ endPlay, onEnter }: { endPlay: boolean; onEnter: (e: MouseEvent<HTMLAnchorElement>) => void }) => (
  <>
    <section data-a="s01" className={styles.scene}>
      <div data-a="s01-stage" className={styles.fill}>
        <span data-a="s01-tag" className={`${styles.abs} ${styles.tag}`} style={at(140, 282)}>The vision</span>
        <div className={`${styles.abs} st-display`} style={at(140, 350, undefined, undefined, { fontSize: 112 })}>
          <span data-a="s01-l" className={styles.line}>The web still</span>
          <span data-a="s01-l" className={styles.line}>shows everyone</span>
          <span data-a="s01-l" className={styles.line}>
            the{' '}
            <span data-a="s01-strike" className={styles.strike}>
              same thing<i data-a="s01-bar" className={styles.strikeBar} />
            </span>
            .
          </span>
        </div>
        <div data-a="s01-card" className={`${styles.abs} ${styles.glass} ${styles.glassLg}`} style={at(1250, 176, 520, 560)}>
          <Blocks list={GENERIC_PAGE} />
        </div>
        {[1340, 1535, 1704].map((x) => (
          <div key={x} data-a="s01-sight" className={styles.sight} style={at(x, 748, undefined, 66)} />
        ))}
        {[['Developer', 1247], ['Investor', 1455], ['Buyer', 1637]].map(([label, x]) => (
          <span key={label} data-a="s01-chip" className={`${styles.abs} ${styles.chip}`} style={at(x as number, 820)}>{label}</span>
        ))}
      </div>
      <div data-a="s01-line" className={styles.seamLine} />
      <div data-a="s01-dot" className={styles.seamDot} />
    </section>

    <section data-a="s02" className={styles.scene} style={AIR}>
      <div className={`${styles.abs} ${styles.centerX} st-display`} style={{ top: 100, fontSize: 96 }}>
        <span data-a="s02-l" className={styles.line}><span className={styles.noCase}>GenUI</span> shapes the page around</span>
        <span data-a="s02-l" className={styles.line}>whoever is reading it.</span>
      </div>
      <svg className={styles.beams} width="1920" height="1080" viewBox="0 0 1920 1080">
        <path data-a="s02-w" className={styles.strand} style={{ color: '#ffffff' }} />
        {STRANDS.map((k) => (
          <path key={k} data-a={`s02-${k}`} className={styles.strand} style={{ color: { v: '#a855f7', i: '#6366f1', t: '#06d4ca' }[k] }} />
        ))}
      </svg>
      <div data-a="s02-pill" className={styles.pill} style={{ left: 0, top: 582 }}>GenUI</div>
      <PersonaCards />
    </section>

    <section data-a="s03" className={styles.scene} style={AIR}>
      <p data-a="s03-sub" className={`${styles.abs} ${styles.body}`} style={at(160, 110, 1600, undefined, { fontSize: 40, textWrap: 'balance' } as CSSProperties)}>
        An AI reads who the visitor is and what they came for, then builds the section from your own content.
      </p>
      <div data-a="s03-wrap" className={styles.fill}>
        <div data-a="s03-card" className={`${styles.abs} ${styles.glass} ${styles.glassLg}`} style={at(560, 300, 800, 560)}>
          <div data-a="s03-hero" className={styles.abs} style={at(40, 96, 720, 200)}>
            <Blocks
              list={[
                [0, 0, 720, 200], [30, 40, 300, 30, true, { background: 'rgba(255,255,255,.2)' }], [30, 84, 240, 30, true, { background: 'rgba(255,255,255,.2)' }],
                [30, 134, 220, 12, true], [460, 20, 236, 160, false, { background: 'linear-gradient(135deg, rgba(168,85,247,.35), rgba(6,212,202,.25))' }],
              ]}
            />
          </div>
          {[40, 410].map((x, n) => (
            <div key={x} data-a={`s03-c${n}`} className={styles.abs} style={at(x, 316, 350, 140)}>
              <Blocks list={[[0, 0, 350, 140], [24, 26, 160, 14, true], [24, 52, 250, 10, true], [24, 72, n ? 190 : 210, 10, true]]} />
            </div>
          ))}
          <div data-a="s03-cta" className={styles.abs} style={at(40, 478, 210, 52, { borderRadius: 999, background: 'var(--st-accent)' })} />
        </div>
        {['Your content', 'Your components', 'The visitor'].map((label, n) => (
          <span key={label} data-a={`s03-t${n}`} className={`${styles.abs} ${styles.tag} ${styles.tagWhite}`} style={{ fontSize: 18, padding: '8px 14px' }}>{label}</span>
        ))}
      </div>
      <p data-a="s03-close" className={`${styles.abs} ${styles.centerX}`} style={{ top: 900, margin: 0, fontSize: 38, fontWeight: 500 }}>
        Every card comes from your content.
      </p>
    </section>

    <section data-a="s04" className={styles.scene} style={AIR}>
      <div className={`${styles.abs} ${styles.centerX} st-display`} style={{ top: 90, fontSize: 100 }}>
        <span data-a="s04-l" className={styles.line}>Generated once per segment.</span>
        <span data-a="s04-l" className={styles.line}>Served to everyone in it.</span>
      </div>
      <svg className={styles.beams} width="1920" height="1080" viewBox="0 0 1920 1080">
        {STRANDS.map((k) => (
          <path key={k} data-a={`s04-${k}`} className={styles.strand} style={{ color: { v: '#a855f7', i: '#6366f1', t: '#06d4ca' }[k] }} />
        ))}
      </svg>
      <div data-a="s04-node" className={styles.node} style={at(426, 666)} />
      {STRANDS.map((k) => (
        <span key={k} data-a={`s04-lab-${k}`} className={`${styles.abs} ${styles.tag} ${styles.tagWhite} ${styles.segLabel}`}>
          <i style={{ background: `rgb(${SEG_RGB[k]})` }} />
          {{ v: 'Developers', i: 'Investors', t: 'Buyers' }[k]}
        </span>
      ))}
    </section>

    <section data-a="s05" className={styles.scene} style={AIR}>
      <div className={`${styles.abs} ${styles.centerX} st-display`} style={{ top: 70, fontSize: 112 }}>
        <span data-a="s05-l" className={styles.line}>You control what</span>
        <span data-a="s05-l" className={styles.line}>reaches the screen.</span>
      </div>
      <svg className={styles.beams} width="1920" height="1080" viewBox="0 0 1920 1080">
        <rect data-a="s05-outline" x="426" y="666" width="28" height="28" rx="14" fill="#ffffff" fillOpacity="1" stroke="#ffffff" strokeWidth="2" opacity="0" style={{ filter: 'drop-shadow(0 0 6px #ffffff)' }} />
      </svg>
      <div data-a="s05-card" className={styles.card} style={at(550, 400, 820, 460, { opacity: 0 })}>
        <img src={bannerImg} alt="" />
      </div>
      {[
        ['Schema validated', 240, 450],
        ['URL allow-list', 1340, 510],
        ['Tenant isolation', 240, 800],
        ['Audit trail', 1340, 760],
      ].map(([label, x, y], n) => (
        <span key={label} data-a={`s05-g${n}`} className={`${styles.abs} ${styles.tag} ${styles.tagWhite}`} style={at(x as number, y as number)}>
          {CHECK}
          {label}
        </span>
      ))}
    </section>

    <section data-a="s06" className={styles.scene} style={AIR}>
      <div className={`${styles.abs} st-display`} style={at(140, 70, undefined, undefined, { fontSize: 104 })}>
        <span data-a="s06-l" className={styles.line}>A holdout group sees</span>
        <span data-a="s06-l" className={styles.line}>the generic page.</span>
      </div>
      <p data-a="s06-sub" className={`${styles.abs} ${styles.body}`} style={at(140, 300, undefined, undefined, { fontSize: 38, whiteSpace: 'nowrap' })}>
        The uplift shows up as a number on a dashboard.
      </p>
      <svg className={styles.beams} width="1920" height="1080" viewBox="0 0 1920 1080">
        <path data-a="s06-split" className={styles.strand} style={{ color: '#ffffff' }} d="M960 460 L960 770" />
      </svg>
      <div data-a="s06-left" className={`${styles.abs} ${styles.glass}`} style={at(240, 470, 480, 270)}>
        <Blocks list={GENERIC_SMALL} />
      </div>
      <div data-a="s06-right" className={styles.card} style={at(550, 400, 820, 460, { opacity: 0, borderColor: '#b180fa', boxShadow: '0 0 40px -9px #b180fa' })}>
        <img src={bannerImg} alt="" />
      </div>
      <span data-a="s06-c" className={`${styles.abs} ${styles.tag}`} style={at(398, 760)}>Holdout</span>
      <span data-a="s06-c" className={`${styles.abs} ${styles.tag} ${styles.tagWhite}`} style={at(1330, 760)}>Personalized</span>
      <div data-a="s06-measure" className={styles.shot} style={at(420, 430, 1080, 541)}>
        <img src={measureImg} alt="" />
      </div>
    </section>

    <section data-a="s07" className={styles.scene} style={AIR}>
      <span data-a="s07-tag" className={`${styles.abs} ${styles.tag}`} style={at(160, 40)}>GenUI Studio</span>
      <div className={`${styles.abs} st-display`} style={at(160, 100, undefined, undefined, { fontSize: 100, whiteSpace: 'nowrap' })}>
        <span data-a="s07-w1" style={{ display: 'inline-block' }}>Theme it.</span>{' '}
        <span data-a="s07-w2" style={{ display: 'inline-block' }}>Feed it.</span>{' '}
        <span data-a="s07-w3" style={{ display: 'inline-block' }}>Ship it.</span>
      </div>
      <div data-a="s07-pg" className={styles.abs} style={at(160, 310, 860, 579)}>
        <div className={styles.shot} style={at(0, 0, 860, 579)}>
          <img src={pgBlueImg} alt="" />
          <img data-a="s07-pg2" src={pgVioletImg} alt="" style={{ opacity: 0 }} />
          <img data-a="s07-pg3" src={pgLightImg} alt="" style={{ opacity: 0 }} />
        </div>
        <span className={`${styles.tag} ${styles.tagWhite} ${styles.frameTag}`} style={at(24, -18)}>Public · No login</span>
      </div>
      <div data-a="s07-cs" className={styles.abs} style={at(1120, 310, 600, 339)}>
        <div className={styles.shot} style={at(0, 0, 600, 339)}>
          <img src={contentImg} alt="" />
        </div>
        <span className={`${styles.tag} ${styles.frameTag} ${styles.frameTagSm}`} style={at(20, -16)}>Admin · Backend required</span>
      </div>
      <div data-a="s07-ms" className={styles.abs} style={at(1120, 720, 600, 301)}>
        <div className={styles.shot} style={at(0, 0, 600, 301)}>
          <img src={measureImg} alt="" />
        </div>
        <span className={`${styles.tag} ${styles.frameTag} ${styles.frameTagSm}`} style={at(20, -16)}>Admin · Backend required</span>
      </div>
    </section>

    <section data-a="s08" className={styles.scene} style={AIR}>
      <div data-a="s08-logo" className={`${styles.abs} ${styles.centerX}`} style={{ top: 100 }}>
        <Lockup size={40} />
      </div>
      <h2 className={`${styles.abs} ${styles.centerX} st-display`} style={{ top: 360, fontSize: 96 }}>
        <span data-a="s08-l" className={styles.line}>Stop building for the average.</span>
        <span data-a="s08-l" className={styles.line}>
          Start building for{' '}
          <GradientText colors={PURPLE} animationSpeed={7}>everyone</GradientText>
        </span>
      </h2>
      <div className={styles.cta} style={{ left: 960, top: 800, scale: '1.8' }}>
        <div data-a="s08-cta">
          <TransformBeams href="#/" label="Enter the Studio" reduced={false} play={endPlay} onClick={onEnter} />
        </div>
      </div>
    </section>
  </>
);

const MiniPage = ({ k }: { k: Strand }) => (
  <div className={`${styles.glass} ${styles.pPage}`}>
    <div className={styles.pBar} />
    <div className={styles.pVisual}>
      {k === 'v' && (
        <>
          <div data-fill className={styles.pCode} style={{ width: '82%', background: 'rgba(99,102,241,.7)' }} />
          <div data-fill className={styles.pCode} style={{ width: '58%' }} />
          <div data-fill className={styles.pCode} style={{ width: '70%' }} />
        </>
      )}
      {k === 'i' && (
        <div className={styles.pBars}>
          {[38, 56, 74, 92].map((h, b) => (
            <div key={h} data-fill style={{ height: `${h}%`, background: `rgba(168,85,247,${0.45 + b * 0.12})` }} />
          ))}
        </div>
      )}
      {k === 't' && <div data-fill className={styles.pOffer} />}
    </div>
    <div data-fill className={styles.pBtn} style={k === 't' ? { background: 'rgba(255,255,255,.85)' } : undefined} />
  </div>
);

const Portrait = ({ endPlay, onEnter }: { endPlay: boolean; onEnter: (e: MouseEvent<HTMLAnchorElement>) => void }) => (
  <>
    <section data-a="p1" className={styles.pScene}>
      <div className={styles.pCol}>
        <span data-a="p1-tag" className={`${styles.tag} ${styles.pTag}`}>The vision</span>
        <h2 className={`st-display ${styles.pHead}`}>
          <span data-a="p1-l" className={styles.line}>The web still</span>
          <span data-a="p1-l" className={styles.line}>shows everyone</span>
          <span data-a="p1-l" className={styles.line}>
            the{' '}
            <span data-a="p1-strike" className={styles.strike}>
              same thing<i data-a="p1-bar" className={styles.strikeBar} />
            </span>
            .
          </span>
        </h2>
        <div data-a="p1-card" className={`${styles.glass} ${styles.glassLg} ${styles.pGeneric}`}>
          <div className={styles.pNav}>
            <div className={styles.blkL} />
            <div className={styles.blkL} />
            <div className={styles.blkL} />
            <div className={styles.blkL} />
          </div>
          <div className={styles.pHero} />
          <div className={styles.pTiles}>
            <div className={styles.blk} />
            <div className={styles.blk} />
            <div className={styles.blk} />
          </div>
          <div className={styles.pCtaBlock} />
        </div>
        <div className={styles.pChips}>
          {['Developer', 'Investor', 'Buyer'].map((label) => (
            <span key={label} data-a="p1-chip" className={`${styles.chip} ${styles.pChip}`}>{label}</span>
          ))}
        </div>
      </div>
      <div data-a="p1-line" className={styles.pSeamLine} />
      <div data-a="p1-dot" className={styles.seamDot} />
    </section>

    <section data-a="p2" className={styles.pScene}>
      <svg data-a="p2-svg" className={styles.pSvg} aria-hidden="true">
        <path data-a="p2-w" className={styles.strand} style={{ color: '#ffffff' }} />
        {STRANDS.map((k) => (
          <path key={k} data-a={`p2-${k}`} className={styles.strand} style={{ color: { v: '#a855f7', i: '#6366f1', t: '#06d4ca' }[k] }} />
        ))}
      </svg>
      <div className={styles.pCol}>
        <h2 className={`st-display ${styles.pHead}`}>
          <span data-a="p2-l" className={styles.line}><span className={styles.noCase}>GenUI</span> shapes</span>
          <span data-a="p2-l" className={styles.line}>the page around</span>
          <span data-a="p2-l" className={styles.line}>whoever is</span>
          <span data-a="p2-l" className={styles.line}>reading it.</span>
        </h2>
        <div className={styles.pBeam}>
          <div data-a="p2-pill" className={styles.pPill}>GenUI</div>
          <div className={styles.pCards}>
            {STRANDS.map((k) => (
              <div key={k} data-a={`pp-${k}`} className={styles.pCardCol}>
                <span className={`${styles.tag} ${styles.pCardTag}`}>{{ v: 'Developer', i: 'Investor', t: 'Buyer' }[k]}</span>
                <MiniPage k={k} />
                <span className={styles.pCardTitle}>{{ v: 'Documentation', i: 'The numbers', t: 'The offer' }[k]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>

    <section data-a="p3" className={styles.pScene}>
      <div className={`${styles.pCol} ${styles.pEnd}`}>
        <div data-a="p3-logo" className={styles.pLockup}>
          <Lockup size={1} />
        </div>
        <h2 className={`st-display ${styles.pEndHead}`}>
          <span data-a="p3-l" className={styles.line}>Stop building</span>
          <span data-a="p3-l" className={styles.line}>for the average.</span>
          <span data-a="p3-l" className={styles.line}>Start building</span>
          <span data-a="p3-l" className={styles.line}>
            for <GradientText colors={PURPLE} animationSpeed={7}>everyone</GradientText>
          </span>
        </h2>
        <div data-a="p3-cta" className={styles.pCta}>
          <TransformBeams href="#/" label="Enter the Studio" reduced={false} play={endPlay} onClick={onEnter} />
        </div>
      </div>
    </section>
  </>
);

interface Kit {
  tl: gsap.core.Timeline;
  q: (name: string) => HTMLElement[];
  one: (name: string) => HTMLElement;
  stage: HTMLElement;
  clusters: SVGSVGElement;
  setEndPlay: (v: boolean) => void;
}

const helpers = ({ tl, q, one }: Kit) => {
  const rise = (name: string | HTMLElement[], t: number, stagger = 0.12) =>
    tl.fromTo(typeof name === 'string' ? q(name) : name, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.6, ease: E, stagger }, t);
  const leave = (names: string[], t: number) =>
    tl.fromTo(names.flatMap(q), { filter: 'blur(0px)' }, { opacity: 0, filter: 'blur(8px)', duration: 0.4, ease: E, immediateRender: false }, t);
  const len = (el: SVGPathElement) => {
    const L = el.getTotalLength();
    el.style.strokeDasharray = `${L}px ${L + 40}px`;
    return L;
  };
  const draw = (name: string, t: number) => {
    const el = one(name) as unknown as SVGPathElement;
    const L = len(el);
    tl.set(el, { opacity: 1 }, t);
    tl.fromTo(el, { strokeDashoffset: L }, { strokeDashoffset: 0, duration: 0.85, ease: E }, t);
  };
  const erase = (name: string, t: number, dur = 0.7) => {
    const el = one(name) as unknown as SVGPathElement;
    const L = len(el);
    tl.to(el, { strokeDashoffset: -(L + 8), duration: dur, ease: E }, t);
    tl.set(el, { opacity: 0 }, t + dur);
  };
  const breathe = (names: string[], t: number, until: number) => {
    const half = 1.7;
    const segs = Math.floor((until - t) / half + 1e-6);
    if (segs < 1) return;
    tl.fromTo(names.flatMap(q), { '--glow': '4px' }, { '--glow': '9px', duration: half, ease: 'cssInOut', yoyo: true, repeat: segs - 1, immediateRender: false }, t);
  };
  const ignite = (el: HTMLElement, t: number) => {
    tl.fromTo(
      el,
      { borderColor: 'rgba(255,255,255,0.28)', boxShadow: '0px 0px 0px 0px rgba(168,85,247,0)' },
      { borderColor: 'rgba(120,83,191,0.54)', boxShadow: '0px 0px 30px 6px rgba(168,85,247,0.55)', duration: 0.42, ease: E },
      t,
    );
    tl.to(el, { borderColor: 'rgba(177,128,250,1)', boxShadow: '0px 0px 40px -9px rgba(177,128,250,1)', duration: 0.78, ease: E }, t + 0.42);
  };
  const scene = (name: string, from: number, to?: number) => {
    tl.set(one(name), { visibility: 'visible' }, from);
    if (to !== undefined) tl.set(one(name), { visibility: 'hidden' }, to);
  };
  return { rise, leave, draw, erase, breathe, ignite, scene };
};

const buildLandscape = (kit: Kit) => {
  const { tl, q, one, stage, clusters, setEndPlay } = kit;
  const { rise, leave, draw, erase, breathe, ignite, scene } = helpers(kit);

  scene('s01', 0, 5.7);
  scene('s02', 5, 13.4);
  scene('s03', 12.9, 21.4);
  scene('s04', 20.9, 28.1);
  scene('s05', 27.8, 35.35);
  scene('s06', 34.4, 40.05);
  scene('s07', 39.95, 48.05);
  scene('s08', 47.95);

  rise('s01-tag', 0.15);
  rise('s01-l', 0.3);
  tl.fromTo(q('s01-card'), { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.8, ease: E }, 0.8);
  tl.fromTo(q('s01-bar'), { scaleX: 0, rotation: -2 }, { scaleX: 1, rotation: -2, duration: 0.5, ease: E }, 1.6);
  tl.fromTo(q('s01-strike'), { color: '#ffffff' }, { color: '#9ca3af', duration: 0.5, ease: E }, 1.6);
  rise('s01-chip', 2.0);
  tl.fromTo(q('s01-sight'), { scaleY: 0, opacity: 0 }, { scaleY: 1, opacity: 1, duration: 0.5, ease: E, stagger: 0.12 }, 2.2);
  tl.fromTo(q('s01-stage'), { scale: 1 }, { scale: 1.04, duration: 4.2 + FIRST_HOLD, ease: E, transformOrigin: '960px 540px' }, 0);
  leave(['s01-tag', 's01-l', 's01-chip', 's01-sight'], 4.2);
  tl.to(q('s01-card'), { scaleY: 0.01, opacity: 0, duration: 0.45, ease: E }, 4.3);
  tl.fromTo(q('s01-line'), { opacity: 0, scaleX: 1 }, { opacity: 1, duration: 0.25, ease: E }, 4.45);
  tl.to(q('s01-line'), { scaleX: 0.006, duration: 0.3, ease: E }, 4.8);
  tl.set(q('s01-line'), { opacity: 0 }, 5.1);
  tl.fromTo(q('s01-dot'), { x: 1261.6, y: 452.64, opacity: 0 }, { opacity: 1, duration: 0.05 }, 5.04);
  const whiteStart = aired(140, 640);
  tl.to(q('s01-dot'), { x: whiteStart.x, y: whiteStart.y, duration: 0.4, ease: E }, 5.1);
  tl.to(q('s01-dot'), { opacity: 0, duration: 0.15, ease: E }, 5.5);

  const pill = one('s02-pill');
  const pw = pill.offsetWidth;
  const L = 640 - pw / 2;
  const R = 640 + pw / 2;
  pill.style.left = `${L}px`;
  one('s02-w').setAttribute('d', mapPath(W_PATH, 140, 580, (L - 140) / 340, 1));
  STRANDS.forEach((k) => one(`s02-${k}`).setAttribute('d', mapPath(OUT[k], R, 377.5, (1250 - R) / 420, 4.375)));
  rise('s02-l', 5.2);
  rise('s02-pill', 5.25);
  const T2 = 5.4;
  draw('s02-w', T2 + 0.1);
  STRANDS.forEach((k) => draw(`s02-${k}`, T2 + OUT_DELAY[k]));
  ignite(pill, T2 + 0.8);
  STRANDS.forEach((k) => {
    const land = T2 + OUT_DELAY[k] + 0.85;
    tl.fromTo(q(`p-${k}`), { opacity: 0, x: 24 }, { opacity: 1, x: 0, duration: 0.6, ease: E }, land - 0.3);
    tl.call(() => shock(one(`p-${k}`), 'left'), [], land - 0.05);
  });
  tl.fromTo(stage.querySelectorAll('[data-a="s02"] [data-fill]'), { opacity: 0 }, { opacity: 1, duration: 0.5, ease: E, stagger: 0.05 }, 7.6);
  breathe(['s02-w', 's02-v', 's02-i', 's02-t'], T2 + 2.4, 12.4);
  leave(['s02-l', 'p-v', 'p-i', 'p-t', 's02-pill'], 12.4);
  erase('s02-w', 12.4, 0.5);
  STRANDS.forEach((k) => erase(`s02-${k}`, 12.45, 0.7));

  const tips: Array<[number, number]> = [[1250, 430], [1250, 626.9], [1250, 850]];
  const slots: Array<[number, number]> = [[600, 330], [822, 330], [1086, 330]];
  slots.forEach(([sx, sy], n) => {
    const el = one(`s03-t${n}`);
    el.style.left = `${sx}px`;
    el.style.top = `${sy}px`;
    const dx = tips[n][0] + 12 - sx;
    const dy = tips[n][1] - el.offsetHeight / 2 - sy;
    tl.fromTo(el, { x: dx, y: dy, opacity: 0 }, { opacity: 1, duration: 0.3, ease: E }, 13.0 + n * 0.06);
    tl.to(el, { x: 0, y: 0, duration: 1.0, ease: E }, 13.8 + n * 0.06);
  });
  rise('s03-sub', 13.1);
  tl.fromTo(q('s03-card'), { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.6, ease: E }, 13.9);
  rise('s03-hero', 15.0);
  rise('s03-c0', 15.6);
  rise('s03-c1', 15.75);
  rise('s03-cta', 16.5);
  rise('s03-close', 17.6);
  leave(['s03-sub', 's03-close'], 20.4);
  tl.to(q('s03-wrap'), { x: 440 - 960, y: 680 - 580, scale: 0.02, transformOrigin: '960px 580px', duration: 0.75, ease: E }, 20.45);
  tl.to(q('s03-wrap'), { opacity: 0, duration: 0.25, ease: E }, 20.95);

  tl.fromTo(q('s04-node'), { opacity: 0, scale: 0.3 }, { opacity: 1, scale: 1, duration: 0.35, ease: E }, 21.05);
  rise('s04-l', 21.2);
  const SX4 = 2.2;
  const SY4 = 4.5;
  STRANDS.forEach((k) => one(`s04-${k}`).setAttribute('d', mapPath(OUT[k], 440, 680 - 60 * SY4, SX4, SY4)));
  const T4 = 22.2 - 1.05;
  STRANDS.forEach((k) => draw(`s04-${k}`, T4 + OUT_DELAY[k]));
  tl.call(() => shock(one('s04-node'), 'center'), [], 22.2);
  STRANDS.forEach((k) => {
    const land = T4 + OUT_DELAY[k] + 0.85;
    const tx = 440 + 420 * SX4;
    const ty = 680 + (OUT_V[k] - 60) * SY4;
    tl.call(() => lightCluster(one('s04'), clusters, tx, ty, SEG_RGB[k]), [], land - 0.05);
    const lab = one(`s04-lab-${k}`);
    lab.style.left = `${tx + 26}px`;
    lab.style.top = `${ty - lab.offsetHeight / 2}px`;
    tl.fromTo(lab, { opacity: 0, x: -12 }, { opacity: 1, x: 0, duration: 0.6, ease: E }, land + 0.15);
  });
  breathe(['s04-v', 's04-i', 's04-t'], T4 + 1.05 + 2.4, 27.2);
  leave(['s04-l', 's04-lab-v', 's04-lab-i', 's04-lab-t'], 27.2);
  tl.to(['s04-v', 's04-i', 's04-t'].flatMap(q), { opacity: 0, duration: 0.5, ease: E }, 27.2);
  tl.fromTo(clusters, { opacity: 1 }, { opacity: 0, duration: 0.7, ease: E }, 27.2);
  tl.set(q('s04-node'), { opacity: 0 }, 27.95);

  tl.fromTo(q('s05-outline'), { attr: { x: 426, y: 666, width: 28, height: 28, rx: 14 }, opacity: 1 }, { attr: { x: 550, y: 400, width: 820, height: 460, rx: 24 }, duration: 0.6, ease: E }, 27.95);
  tl.to(q('s05-outline'), { fillOpacity: 0, duration: 0.18, ease: E }, 27.95);
  tl.fromTo(q('s05-card'), { opacity: 0 }, { opacity: 1, duration: 0.5, ease: E }, 28.45);
  tl.to(q('s05-outline'), { opacity: 0, duration: 0.6, ease: E }, 28.7);
  rise('s05-l', 28.2);
  [-24, 24, -24, 24].forEach((fromX, n) => {
    const t = 29.8 + n;
    const tag = q(`s05-g${n}`);
    tl.fromTo(tag, { opacity: 0, x: fromX, boxShadow: '0px 0px 0px 0px rgba(168,85,247,0)' }, { opacity: 1, x: 0, duration: 0.6, ease: E }, t);
    tl.fromTo(tag[0].querySelector('svg'), { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.35, ease: E }, t + 0.35);
    tl.to(tag, { boxShadow: '0px 0px 28px 2px rgba(168,85,247,0.5)', duration: 0.2, ease: E }, t + 0.45);
    tl.to(tag, { boxShadow: '0px 0px 0px 0px rgba(168,85,247,0)', duration: 0.5, ease: E }, t + 0.65);
    tl.to(q('s05-card'), { borderColor: 'rgba(177,128,250,0.7)', boxShadow: '0px 0px 30px 0px rgba(168,85,247,0.35)', duration: 0.2, ease: E }, t + 0.45);
    if (n < 3) tl.to(q('s05-card'), { borderColor: 'rgba(255,255,255,0.14)', boxShadow: '0px 0px 0px 0px rgba(177,128,250,0)', duration: 0.5, ease: E }, t + 0.65);
  });
  tl.to(q('s05-card'), { borderColor: 'rgba(177,128,250,1)', boxShadow: '0px 0px 40px -9px rgba(177,128,250,1)', duration: 0.7, ease: E }, 33.3);
  leave(['s05-l', 's05-g0', 's05-g1', 's05-g2', 's05-g3'], 34.4);
  const S6 = 480 / 820;
  tl.to(q('s05-card'), { x: 480, y: -25, scale: S6, transformOrigin: '50% 50%', duration: 0.8, ease: E }, 34.5);

  tl.set(q('s06-right'), { x: 480, y: -25, scale: S6, transformOrigin: '50% 50%' }, 0);
  tl.set(q('s06-right'), { opacity: 1 }, 35.3);
  draw('s06-split', 34.9);
  rise('s06-l', 35.0);
  rise('s06-left', 35.4);
  rise('s06-c', 35.9);
  leave(['s06-left', 's06-right', 's06-c'], 36.8);
  erase('s06-split', 36.8, 0.5);
  rise('s06-sub', 36.9);
  tl.fromTo(q('s06-measure'), { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.8, ease: E }, 37.1);

  tl.fromTo(q('veil'), { opacity: 0 }, { opacity: 1, duration: 0.4, ease: 'veilIn' }, 39.6);
  tl.to(q('veil'), { opacity: 0, duration: 0.6, ease: 'veilOut' }, 40.0);

  rise('s07-tag', 40.15);
  rise('s07-w1', 40.25);
  rise('s07-pg', 40.45);
  tl.fromTo(q('s07-pg2'), { opacity: 0 }, { opacity: 1, duration: 0.5, ease: E }, 41.9);
  tl.fromTo(q('s07-pg3'), { opacity: 0 }, { opacity: 1, duration: 0.5, ease: E }, 43.2);
  rise('s07-w2', 42.9);
  rise('s07-cs', 43.0);
  rise('s07-w3', 44.6);
  rise('s07-ms', 44.7);

  tl.fromTo(q('veil'), { opacity: 0 }, { opacity: 1, duration: 0.4, ease: 'veilIn', immediateRender: false }, 47.6);
  tl.to(q('veil'), { opacity: 0, duration: 0.6, ease: 'veilOut' }, 48.0);

  rise('s08-logo', 48.3);
  rise('s08-l', 48.45);
  rise('s08-cta', 49.4);
  tl.call(() => setEndPlay(true), [], 50.2);
  tl.call(() => shock(one('s08-cta').querySelector('a'), 'left'), [], 50.2 + 0.95);

  tl.shiftChildren(PROOF_EXTRA, false, 36.8);
  tl.shiftChildren(FIRST_HOLD, false, 4.2);
};

const buildPortrait = (kit: Kit) => {
  const { tl, q, one, setEndPlay } = kit;
  const { rise, leave, draw, erase, breathe, ignite, scene } = helpers(kit);
  const box = (name: string) => one(name).getBoundingClientRect();
  const card = box('p1-card');
  const pill = box('p2-pill');
  const cols = STRANDS.map((k) => box(`pp-${k}`));
  const headBottom = q('p2-l').slice(-1)[0].getBoundingClientRect().bottom;

  scene('p1', 0, 7.3);
  scene('p2', 6.7, 14.2);
  scene('p3', 13.9);

  rise('p1-tag', 0.15);
  rise('p1-l', 0.3);
  tl.fromTo(q('p1-card'), { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.8, ease: E }, 0.8);
  tl.fromTo(q('p1-bar'), { scaleX: 0, rotation: -2 }, { scaleX: 1, rotation: -2, duration: 0.5, ease: E }, 1.6);
  tl.fromTo(q('p1-strike'), { color: '#ffffff' }, { color: '#9ca3af', duration: 0.5, ease: E }, 1.6);
  rise('p1-chip', 2.0);

  const line = one('p1-line');
  line.style.left = `${card.left}px`;
  line.style.top = `${card.top + card.height / 2 - 1.8}px`;
  line.style.width = `${card.width}px`;
  const cx = pill.left + pill.width / 2;
  const whiteTop = pill.top - Math.max(48, pill.top - headBottom - 28);

  leave(['p1-tag', 'p1-l', 'p1-chip'], 4.2 + FIRST_HOLD);
  tl.to(q('p1-card'), { scaleY: 0.01, opacity: 0, duration: 0.45, ease: E }, 4.3 + FIRST_HOLD);
  tl.fromTo(line, { opacity: 0, scaleX: 1 }, { opacity: 1, duration: 0.25, ease: E }, 4.45 + FIRST_HOLD);
  tl.to(line, { scaleX: 0.006, duration: 0.3, ease: E }, 4.8 + FIRST_HOLD);
  tl.set(line, { opacity: 0 }, 5.1 + FIRST_HOLD);
  tl.fromTo(q('p1-dot'), { x: card.left + card.width / 2, y: card.top + card.height / 2, opacity: 0 }, { opacity: 1, duration: 0.05 }, 5.04 + FIRST_HOLD);
  tl.to(q('p1-dot'), { x: cx, y: whiteTop, duration: 0.4, ease: E }, 5.1 + FIRST_HOLD);
  tl.to(q('p1-dot'), { opacity: 0, duration: 0.15, ease: E }, 5.5 + FIRST_HOLD);

  const svg = one('p2-svg') as unknown as SVGSVGElement;
  svg.setAttribute('viewBox', `0 0 ${window.innerWidth} ${window.innerHeight}`);
  const land = cols[0].top - 8;
  const spread = (cols[2].left + cols[2].width / 2 - cx) / 48;
  one('p2-w').setAttribute('d', rotate(W_PATH, cx, whiteTop, (pill.top - whiteTop) / 340, 1));
  STRANDS.forEach((k) => one(`p2-${k}`).setAttribute('d', rotate(OUT[k], cx, pill.bottom, (land - pill.bottom) / 420, spread)));

  const T = 7.2;
  rise('p2-l', T - 0.2);
  rise('p2-pill', T - 0.15);
  draw('p2-w', T + 0.1);
  STRANDS.forEach((k) => draw(`p2-${k}`, T + OUT_DELAY[k]));
  ignite(one('p2-pill'), T + 0.8);
  STRANDS.forEach((k) => {
    const hit = T + OUT_DELAY[k] + 0.85;
    tl.fromTo(q(`pp-${k}`), { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.6, ease: E }, hit - 0.3);
    tl.call(() => shock(one(`pp-${k}`), 'top'), [], hit - 0.05);
  });
  tl.fromTo(kit.stage.querySelectorAll('[data-a="p2"] [data-fill]'), { opacity: 0 }, { opacity: 1, duration: 0.5, ease: E, stagger: 0.05 }, T + 2.3);
  breathe(['p2-w', 'p2-v', 'p2-i', 'p2-t'], T + 2.4, T + 6.4);
  leave(['p2-l', 'pp-v', 'pp-i', 'pp-t', 'p2-pill'], T + 6.4);
  erase('p2-w', T + 6.4, 0.5);
  STRANDS.forEach((k) => erase(`p2-${k}`, T + 6.45, 0.7));

  const E3 = T + 7.0;
  rise('p3-logo', E3);
  rise('p3-l', E3 + 0.15);
  rise('p3-cta', E3 + 0.9);
  tl.call(() => setEndPlay(true), [], E3 + 1.5);
  tl.call(() => shock(one('p3-cta').querySelector('a'), 'left'), [], E3 + 1.5 + 0.95);
};

const lightCluster = (scene: HTMLElement, svg: SVGSVGElement, tx: number, ty: number, rgb: string) => {
  const box = scene.getBoundingClientRect();
  const s = box.width / 1920;
  const x = box.left + tx * s;
  const y = box.top + ty * s;
  const r = Math.max(85 * s, 95);
  gridDotsNear(x, y, r).forEach((d) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('cx', `${d.x}`);
    c.setAttribute('cy', `${d.y}`);
    c.setAttribute('r', '1.6');
    c.setAttribute('fill', `rgb(${rgb})`);
    c.setAttribute('opacity', '0');
    svg.appendChild(c);
    gsap.to(c, { opacity: 1, duration: 0.5, delay: (d.d / r) * 0.5, ease: E });
  });
};

const fitScale = () => Math.min(1, (Math.min(window.innerWidth / 1920, window.innerHeight / 1080)) * STAGE_FIT);
const normalize = (hash: string) => hash.replace(/^#/, '').split('?')[0] || '/';

interface IntroVideoProps {
  onReveal: () => void;
  onDone: () => void;
}

export const IntroVideo = ({ onReveal, onDone }: IntroVideoProps) => {
  const [portrait] = useState(() => window.innerHeight > window.innerWidth);
  const [scale, setScale] = useState(fitScale);
  const [phase, setPhase] = useState<'play' | 'veil' | 'out'>('play');
  const [endPlay, setEndPlay] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const clustersRef = useRef<SVGSVGElement>(null);
  const closing = useRef(false);
  const timers = useRef<number[]>([]);
  const done = useRef({ onReveal, onDone });
  done.current = { onReveal, onDone };

  const close = useCallback(() => {
    if (closing.current) return;
    closing.current = true;
    markIntroSeen();
    setPhase('veil');
    timers.current.push(
      window.setTimeout(() => {
        done.current.onReveal();
        setPhase('out');
        timers.current.push(window.setTimeout(() => done.current.onDone(), VEIL_OUT_MS));
      }, VEIL_IN_MS),
    );
  }, []);

  const onEnter = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault();
      close();
    },
    [close],
  );

  useLayoutEffect(() => {
    let ctx: gsap.Context | undefined;
    let cancelled = false;
    document.fonts.ready.then(() => {
      const root = rootRef.current;
      const stage = stageRef.current;
      const clusters = clustersRef.current;
      if (cancelled || !root || !stage || !clusters) return;
      ctx = gsap.context(() => {
        const q = (name: string) => Array.from(root.querySelectorAll<HTMLElement>(`[data-a="${name}"]`));
        const one = (name: string) => q(name)[0];
        const kit: Kit = { tl: gsap.timeline({ delay: START_DELAY }), q, one, stage, clusters, setEndPlay };
        (portrait ? buildPortrait : buildLandscape)(kit);
      }, root);
    });
    return () => {
      cancelled = true;
      ctx?.kill();
    };
  }, [portrait]);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    rootRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    const onResize = () => setScale(fitScale());
    const onHash = () => {
      if (normalize(window.location.hash) === '/') return;
      markIntroSeen();
      done.current.onReveal();
      done.current.onDone();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('resize', onResize);
    window.addEventListener('hashchange', onHash);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('hashchange', onHash);
      timers.current.forEach(clearTimeout);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [close, portrait]);

  return (
    <div ref={rootRef} className={styles.overlay} data-phase={phase} role="dialog" aria-modal="true" aria-label="GenUI Studio intro" tabIndex={-1}>
      <svg ref={clustersRef} className={styles.clusters} aria-hidden="true" />
      {portrait ? (
        <div ref={stageRef} className={styles.pRoot}>
          <Portrait endPlay={endPlay} onEnter={onEnter} />
        </div>
      ) : (
        <div ref={stageRef} className={styles.stage} style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
          <Landscape endPlay={endPlay} onEnter={onEnter} />
        </div>
      )}
      <div data-a="veil" className={styles.veil} />
      <button type="button" className={styles.skip} onClick={close}>
        Skip intro
      </button>
    </div>
  );
};

export default IntroVideo;
