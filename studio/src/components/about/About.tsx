/**
 * About page: the business-facing story of GenUI (not a dev tutorial).
 */

import { motion, useInView, useReducedMotion, type Variants } from 'framer-motion';
import { useRef } from 'react';
import GradientText from '../gradient-text/GradientText';
import styles from './About.module.css';

const EASE = [0.4, 0, 0.2, 1] as const;
const PURPLE = ['#a855f7', '#6366f1', '#c084fc', '#a855f7'];
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

const TransformBeams = ({ reduced }: { reduced: boolean | null }) => {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const play = inView && !reduced;

  return (
    <div ref={ref} className={`${styles.ctaWrap} ${play ? styles.play : ''}`.trim()}>
      <div className={`${styles.beam} ${styles.beamLeft}`}>
        <svg viewBox="0 0 340 120" preserveAspectRatio="none" aria-hidden="true">
          <Strand d="M0 60 L 344 60" color="#ffffff" delay={0.1} />
        </svg>
      </div>

      <a href="#/playground" className={styles.tryPlayground}>
        Try the Theme Playground
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

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12 } },
};

const rise: Variants = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE } },
};

interface Reveal {
  children: React.ReactNode;
  className?: string;
}

const Section = ({ children, className = '' }: Reveal) => {
  const reduced = useReducedMotion();
  return (
    <motion.section
      className={`${styles.section} ${className}`.trim()}
      variants={container}
      initial={reduced ? undefined : 'hidden'}
      whileInView={reduced ? undefined : 'show'}
      viewport={{ once: true, amount: 0.3 }}
    >
      {children}
    </motion.section>
  );
};

const VALUE_PROPS: Array<{ metric: string; title: string; body: string }> = [
  {
    metric: 'Relevance',
    title: 'Every visitor, their page',
    body: 'A developer sees documentation, an investor sees the numbers, a buyer sees the offer. One page, shaped to the person in front of it.',
  },
  {
    metric: 'Efficiency',
    title: 'Generated once, served to many',
    body: 'The AI runs per audience segment, not per visit. The cost of personalization drops by orders of magnitude and the experience stays instant.',
  },
  {
    metric: 'Trust',
    title: 'The system guarantees the output',
    body: 'Schema validation, a strict URL allow-list, tenant isolation, and an audit trail. What reaches the screen is controlled, not hoped for.',
  },
  {
    metric: 'Proof',
    title: 'Personalization you can measure',
    body: 'A holdout group sees the generic page, everyone else the tailored one. The uplift is a number on a dashboard, not a promise in a pitch.',
  },
];

const AUDIENCES = ['E-commerce', 'Insurance', 'SaaS', 'Editorial', 'Enterprise portals'];

export const About = () => {
  const reduced = useReducedMotion();

  return (
    <main className={styles.about}>
      <motion.section
        className={styles.hero}
        initial={reduced ? undefined : { opacity: 0, y: 30 }}
        animate={reduced ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: EASE }}
      >
        <span className={styles.eyebrow}>THE VISION</span>
        <h1 className={`st-display ${styles.heroTitle}`}>
          The web <br className='hide-lg show-sm' /> still shows
          <br />
          everyone the{' '}
          <span className={styles.strike}>same thing</span>.
        </h1>
        <div className={styles.heroLead}>
          GenUI is a framework for interfaces that{' '}
          <GradientText colors={PURPLE} animationSpeed={7}>
            adapt to every user
          </GradientText>{' '}
          in real time. The content of a page becomes a decision, made for the
          person reading it, instead of a fixed layout built for the average.
        </div>
      </motion.section>

      <Section>
        <motion.p variants={rise} className={styles.big}>
          For 30 years we personalized recommendations.
        </motion.p>
        <motion.p variants={rise} className={styles.big}>
          GenUI personalizes the <em>interface itself</em>.
        </motion.p>
        <motion.p variants={rise} className={styles.sub}>
          An AI reads who the visitor is and what they came for, then composes
          the section from your own content: the right cards, the right story,
          the right call to action. Nothing invented, everything curated.
        </motion.p>
      </Section>

      <Section>
        <motion.h2 variants={rise} className={`st-section-title ${styles.h2}`}>
          Why it matters
        </motion.h2>
        <div className={styles.grid}>
          {VALUE_PROPS.map((vp) => (
            <motion.article key={vp.title} variants={rise} className={`st-glass ${styles.valueCard}`}>
              <span className={styles.valueMetric}>{vp.metric}</span>
              <h3 className={styles.valueTitle}>{vp.title}</h3>
              <p className={styles.valueBody}>{vp.body}</p>
            </motion.article>
          ))}
        </div>
      </Section>

      <Section className={styles.audiences}>
        <motion.h2 variants={rise} className={`st-section-title ${styles.h2}`}>
          Built for real businesses
        </motion.h2>
        <motion.p variants={rise} className={styles.sub}>
          The same engine dresses itself in any brand and speaks to any market.
        </motion.p>
        <div className={styles.pillRow}>
          {AUDIENCES.map((a) => (
            <motion.span key={a} variants={rise} className={styles.pill}>
              {a}
            </motion.span>
          ))}
        </div>
      </Section>

      <Section className={styles.closing}>
        <motion.h2 variants={rise} className={`st-display ${styles.closeTitle}`} style={{ marginBottom: "4rem" }}>
          Stop building for the average
          <br />
          Start building for{' '}
          <GradientText colors={PURPLE} animationSpeed={7}>
            everyone
          </GradientText>
        </motion.h2>
        <motion.div variants={rise} className={styles.closeCta}>
          <TransformBeams reduced={reduced} />
          <a href="#/" className={styles.backStudioHome}>
            Back to Studio
          </a>
        </motion.div>
      </Section>
    </main>
  );
};

export default About;
