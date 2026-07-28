import styles from './Footer.module.css';

export const Footer = () => (
  <footer className={styles.footer}>
    <div className={styles.inner}>
      <span className={styles.left}>
        <span className={styles.brand}>GenUI</span>
        <span className={styles.note}>Designed &amp; built by Vlad Dogariu.</span>
      </span>
      <nav className={styles.links} aria-label="Project links">
        <a className={styles.link} href="#/compliance">
          AI Act &amp; GDPR ↗
        </a>
        <a
          className={styles.link}
          href="https://github.com/thevladdo/genui-framework"
          target="_blank"
          rel="noreferrer"
        >
          Source on GitHub ↗
        </a>
        <a
          className={styles.link}
          href="https://thevladdo.github.io/"
          target="_blank"
          rel="noreferrer"
        >
          Portfolio ↗
        </a>
      </nav>
    </div>
  </footer>
);

export default Footer;
