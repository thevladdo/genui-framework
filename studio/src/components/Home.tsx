/**
 * Homepage: hero + the 3 destination cards.
 */

import { motion, useReducedMotion } from 'framer-motion';
import GradientText from '../components/gradient-text/GradientText';
import styles from './Home.module.css';

interface CardDef {
  href: string;
  tag: string;
  title: [string, string];
  description: string;
  artClass: string;
}

const CARDS: CardDef[] = [
  {
    href: '#/playground',
    tag: 'PUBLIC · NO LOGIN',
    title: ['Theme', 'Playground'],
    description:
      'Configure tokens in real time: radius, blur, color, font. Preview every GenUI component live.',
    artClass: styles.artPlayground,
  },
  {
    href: '#/studio',
    tag: 'ADMIN · BACKEND REQUIRED',
    title: ['Content', 'Studio'],
    description:
      'Upload documents, manage your knowledge base, and test RAG queries. Connect once, explore everything.',
    artClass: styles.artStudio,
  },
];

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
        {CARDS.map((card) => (
          <motion.a
            key={card.href}
            href={card.href}
            className={`${styles.card} ${card.artClass}`}
            whileHover={reducedMotion ? undefined : { y: -6, scale: 1.015 }}
            whileTap={reducedMotion ? undefined : { scale: 0.99 }}
            transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
          >
            <span className={styles.cardTag}>{card.tag}</span>
            <span className={styles.cardBody}>
              <span className={`st-display ${styles.cardTitle}`}>
                {card.title[0]}
                <br />
                {card.title[1]}
              </span>
              <span className={styles.cardDescription}>{card.description}</span>
            </span>
            <span className={styles.cardArrow} aria-hidden="true">
              →
            </span>
          </motion.a>
        ))}
      </section>

      <motion.a
        href="#/about"
        className={`${styles.card} ${styles.aboutCard}`}
        whileHover={reducedMotion ? undefined : { y: -4, scale: 1.008 }}
        whileTap={reducedMotion ? undefined : { scale: 0.995 }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        aria-label="What is GenUI"
      >
        <span className={styles.cardTag}>THE VISION · FOR EVERYONE</span>
        <span className={styles.aboutBody}>
          <span className={`st-display ${styles.aboutTitle}`}>
            What is{' '}
            <GradientText colors={['#a855f7', '#6366f1', '#c084fc', '#a855f7']}>
              GenUI
            </GradientText>
            ?
          </span>
          <span className={styles.cardDescription}>
            The idea, the potential, and why interfaces that adapt to every
            user change how digital products are built.
          </span>
        </span>
        <span className={styles.cardArrow} aria-hidden="true">
          →
        </span>
      </motion.a>

      <footer className={styles.footer}>
        <span className={styles.footerLeft}>
          <span className={styles.footerBrand}>GenUI</span>
          <span className={styles.footerNote}>
            Designed &amp; built by Vlad Dogariu.
          </span>
        </span>
        <nav className={styles.footerLinks} aria-label="Project links">
          <a
            className={styles.footerLink}
            href="https://github.com/thevladdo/genui-framework"
            target="_blank"
            rel="noreferrer"
          >
            Source on GitHub ↗
          </a>
          <a
            className={styles.footerLink}
            href="https://thevladdo.github.io/"
            target="_blank"
            rel="noreferrer"
          >
            Portfolio ↗
          </a>
        </nav>
      </footer>
    </main>
  );
};
