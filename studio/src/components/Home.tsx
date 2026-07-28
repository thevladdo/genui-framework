/**
 * Homepage: hero + the 3 destination cards.
 */

import { motion, useReducedMotion } from 'framer-motion';
import GradientText from '../components/gradient-text/GradientText';
import { ConsoleCard } from './ConsoleCard';
import styles from './Home.module.css';

export const Home = () => {
  const reducedMotion = useReducedMotion();

  return (
    <main className={styles.home}>
      <section className={styles.hero}>
        <h1 className={`st-display ${styles.heroTitle}`}>
          Build UI.
          <br />
          Build&nbsp;
          <span style={{ display: 'inline-block' }}>
            <GradientText>
              faster
            </GradientText>
          </span>
          .
        </h1>
        <p className={styles.heroSub}>
          The companion for building with <em>GenUI</em>.
          <br />
          Theme it. Feed it. Ship it.
        </p>
      </section>

      <section className={styles.cards} aria-label="Studio sections">
        <motion.a
          href="#/playground"
          className={`${styles.card} ${styles.artPlayground}`}
          whileHover={reducedMotion ? undefined : { y: -6, scale: 1.015 }}
          whileTap={reducedMotion ? undefined : { scale: 0.99 }}
          transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        >
          <span className={styles.cardTag}>PUBLIC · NO LOGIN</span>
          <span className={styles.cardBody}>
            <span className={`st-display ${styles.cardTitle}`}>
              Theme
              <br />
              Playground
            </span>
            <span className={styles.cardDescription}>
              Configure tokens in real time: radius, blur, color, font.
              Preview every GenUI component live.
            </span>
          </span>
          <span className={styles.cardArrow} aria-hidden="true">
            →
          </span>
        </motion.a>

        <ConsoleCard />
      </section>

      <motion.a
        href="#/about"
        className={`${styles.card} ${styles.aboutCard}`}
        whileHover={reducedMotion ? undefined : { y: -4, scale: 1.008 }}
        whileTap={reducedMotion ? undefined : { scale: 0.995 }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        aria-label="What is GenUI"
      >
        <span className={styles.cardTag}>THE VISION</span>
        <span className={styles.aboutBody}>
          <span className={`st-display ${styles.aboutTitle}`}>
            What is{' '}
            <GradientText colors={['#a855f7', '#6366f1', '#c084fc', '#a855f7']}>
              GenUI
            </GradientText>
            ?
          </span>
          <span className={styles.cardDescription}>
            The idea, the potential, and why interfaces that adapt<br />to every
            user change how digital products are built.
          </span>
        </span>
        <span className={styles.cardArrow} aria-hidden="true">
          →
        </span>
      </motion.a>

    </main>
  );
};
