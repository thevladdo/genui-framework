import { useInView } from 'framer-motion';
import { useRef, type MouseEvent } from 'react';
import styles from './About.module.css';

const OUT_STRANDS: Array<{ d: string; color: string; delay: number }> = [
  { d: 'M-6 60 C 110 60, 180 30, 290 22 C 350 17, 388 15, 420 12', color: '#a855f7', delay: 1.05 },
  { d: 'M-6 60 C 150 60, 300 58, 420 57', color: '#6366f1', delay: 1.18 },
  { d: 'M-6 60 C 110 60, 180 90, 290 98 C 350 103, 388 105, 420 108', color: '#06d4ca', delay: 1.31 },
];

const Strand = ({ d, color, delay }: { d: string; color: string; delay: number }) => (
  <path
    d={d}
    className={styles.strand}
    pathLength={1}
    style={{ color, ['--draw-delay' as string]: `${delay}s` }}
  />
);

interface TransformBeamsProps {
  href: string;
  label: string;
  reduced: boolean | null;
  play?: boolean;
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void;
}

export const TransformBeams = ({ href, label, reduced, play, onClick }: TransformBeamsProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const run = (play ?? inView) && !reduced;

  return (
    <div ref={ref} className={`${styles.ctaWrap} ${run ? styles.play : ''}`.trim()}>
      <div className={`${styles.beam} ${styles.beamLeft}`}>
        <svg viewBox="0 0 340 120" preserveAspectRatio="none" aria-hidden="true">
          <Strand d="M0 60 L 344 60" color="#ffffff" delay={0.1} />
        </svg>
      </div>

      <a href={href} className={styles.tryPlayground} onClick={onClick}>
        {label}
      </a>

      <div className={`${styles.beam} ${styles.beamRight}`}>
        <svg viewBox="0 0 420 120" preserveAspectRatio="none" aria-hidden="true">
          {OUT_STRANDS.map((s) => (
            <Strand key={s.color} {...s} />
          ))}
        </svg>
      </div>
    </div>
  );
};

export default TransformBeams;
