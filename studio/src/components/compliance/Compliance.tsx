import { motion, useReducedMotion, type Variants } from 'framer-motion';
import styles from './Compliance.module.css';

const EASE = [0.4, 0, 0.2, 1] as const;

export const DOC_BASE = 'https://github.com/thevladdo/genui-framework/blob/main/deploy/';

export const DOCS: Array<{ file: string; title: string; body: string }> = [
  {
    file: 'AI-ACT.md',
    title: 'AI Act statement',
    body: 'Who answers for what, the transparency obligations one by one, and the boundaries this system must not be wired across.',
  },
  {
    file: 'GDPR.md',
    title: 'Data protection statement',
    body: 'Processing activities, lawful basis by what is touched, the rights runbook with real commands, retention and transfers.',
  },
  {
    file: 'OUTPUT-GUARANTEES.md',
    title: 'Output guarantees',
    body: 'What is enforced on generated content after the model has spoken, and what no post-generation check can promise.',
  },
  {
    file: 'TENANT-ISOLATION.md',
    title: 'Tenant isolation',
    body: 'The data boundary between audiences served by the same deployment, and where it is enforced.',
  },
];

interface Point {
  term: string;
  body: string;
}

interface Mechanism {
  label: string;
  title: string;
  lead: string;
  points: Point[];
  operator?: string;
}

const MECHANISMS: Mechanism[] = [
  {
    label: 'AI ACT ART. 50',
    title: 'Generated content says that it is generated',
    lead: 'The obligation falls on whoever puts the system into service. What the framework owes them is a marking they do not have to build.',
    points: [
      {
        term: 'In the payload',
        body: 'Every served response carries a disclosure block: whether a model wrote it, what the provenance is, and when the generation actually happened. Sync, streamed, batch, warmup and every cache hit.',
      },
      {
        term: 'In the markup',
        body: 'The zone root carries data attributes and a JSON-LD block built on the IPTC digitalSourceType vocabulary, the one C2PA reads too. It is in the server rendered HTML and in the first paint of a streamed render.',
      },
      {
        term: 'On the screen',
        body: 'A visible line of text, on by default, rendered as text and never as a CSS value, readable in both colour modes with nothing carried by colour alone. It can be made discreet and it cannot be shrunk into invisibility.',
      },
      {
        term: 'When no model ran',
        body: 'A render assembled from your own pinned content after a generation failure reports itself as not generated. Marking your copy as AI written would be a false marking in exactly the direction the rule exists to prevent.',
      },
    ],
    operator: 'Yours to set: the wording and the position of the notice, because the formulation is a legal choice. The deployment wide switch that removes it exists, and it writes a warning into the logs at every startup.',
  },
  {
    label: 'EPRIVACY AND GDPR ART. 6',
    title: 'Nothing is touched on the device without consent',
    lead: 'Reading or writing a visitor terminal is the thing that needs permission, whatever the storage is called. So consent is checked at the one place any of it can start.',
    points: [
      {
        term: 'Consent is a literal yes',
        body: 'The profile cache and the chat history live in the browser, and nothing is read or written unless consent is explicitly true. An integrator who has not wired a consent flow yet gets the anonymous mode, not a quiet write to a visitor device.',
      },
      {
        term: 'No identifier, no tracker',
        body: 'Without consent no user id leaves the page, no server side profile is read or created, and the behaviour tracker is never constructed rather than constructed and then filtered.',
      },
      {
        term: 'The page is still personalised',
        body: 'Refused consent takes the path the framework already runs for every visitor nobody logged in: the segment collapses to anonymous and the band is generated from a segment archetype. Personalisation that needs no banner is a configuration here, not a workaround.',
      },
      {
        term: 'Free text is minimised at the source',
        body: 'Form fields are never captured at any level. A marked subtree is excluded outright or reduced to its shape, and common personal data patterns are redacted before anything is sent. Pattern matching is not detection, so the exclusion attribute is the answer for anything sensitive by construction.',
      },
    ],
    operator: 'Yours: the consent decision itself. The system consumes a boolean and keeps no consent record, so collecting, timestamping and proving it stays with your platform.',
  },
  {
    label: 'TRANSFERS',
    title: 'Where the data goes is a line in a config file',
    lead: 'One deployment per customer, on their own infrastructure. There is no service in the middle, and no account to open with the author of the framework.',
    points: [
      {
        term: 'Your key, your provider',
        body: 'The model and the embedding endpoint are chosen by the operator and billed to them. Swapping the vendor is configuration, not a fork.',
      },
      {
        term: 'Shared renders carry an archetype',
        body: 'A cached render sends the segment archetype parsed from the cache key, not the raw profile of whoever happened to trigger the generation. No user id and no API key are ever placed in a prompt.',
      },
      {
        term: 'The configuration where nothing leaves',
        body: 'Point the base URL at an engine inside your own network and the whole chain runs on your infrastructure: prompts, generations, embeddings, documents, traces. The datastores are already internal in the shipped compose.',
      },
      {
        term: 'The uncomfortable rows are written down too',
        body: 'Cloud document extraction sends whole uploaded files out, and it is the largest egress in the matrix. It is opt in, it is named, and a script prints the egress map for the configuration you actually have running.',
      },
    ],
  },
  {
    label: 'GDPR ART. 15 TO 21',
    title: 'Data subject rights are endpoints, not intentions',
    lead: 'Two things in this system are keyed to a person: the profile, and the audit lines that name a user. The rights below act on exactly those.',
    points: [
      {
        term: 'Access and portability',
        body: 'One call returns the stored profile plus the audit entries naming that person, as structured JSON, behind the same identity guard as every other per user route. An export endpoint with a weak guard is a breach wearing a compliance label.',
      },
      {
        term: 'Rectification',
        body: 'The profile is a small typed structure that merges by confidence, so a correction supplied by a human outranks a value the system inferred.',
      },
      {
        term: 'Erasure, and what survives it',
        body: 'The profile goes, and it is the whole of the personalisation data held about that person. The audit trail stays, because a record of what was shown to whom is worth nothing if the party who showed it can rewrite it afterwards. The response says so instead of reporting a clean deletion.',
      },
      {
        term: 'Withdrawal',
        body: 'One property. The tracker stops, device storage stops, the identifier stops being sent, and the visitor keeps a personalised page served from the anonymous segment.',
      },
      {
        term: 'Retention is a setting',
        body: 'Profiles expire after a window of inactivity, cached renders belong to a segment rather than a person and are short lived. The numbers a deployment can defend are the operator to choose.',
      },
    ],
  },
];

const OPERATOR_DUTIES: Point[] = [
  {
    term: 'The lawful basis and the consent platform',
    body: 'The system consumes a consent decision and never collects one. Choosing the basis, running the prompt and keeping the record are yours.',
  },
  {
    term: 'The impact assessment and the processing records',
    body: 'Personalising content for a large audience sits close to the criteria that make an assessment necessary. The documents are written to be an input to yours; they do not conclude in your place.',
  },
  {
    term: 'There is no human review of generated text',
    body: 'Zone configuration has draft and approve under a named admin identity. That approves the prompt, not the copy a model later writes from it. Nothing here puts a person in front of generated text before a page shows it, and calling configuration approval an editorial review would be the most damaging sentence on this page.',
  },
  {
    term: 'The use boundaries are documentation, not enforcement',
    body: 'This system curates presentation. Wiring its output into pricing, eligibility, credit scoring or hiring moves the resulting system into the high risk regime, and no code path in here refuses to render a price.',
  },
];

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

const rise: Variants = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE } },
};

const Reveal = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => {
  const reduced = useReducedMotion();
  return (
    <motion.section
      className={`${styles.section} ${className}`.trim()}
      variants={container}
      initial={reduced ? undefined : 'hidden'}
      whileInView={reduced ? undefined : 'show'}
      viewport={{ once: true, amount: 0.2 }}
    >
      {children}
    </motion.section>
  );
};

const PointList = ({ points }: { points: Point[] }) => (
  <dl className={styles.points}>
    {points.map((p) => (
      <motion.div key={p.term} variants={rise} className={styles.point}>
        <dt className={styles.term}>{p.term}</dt>
        <dd className={styles.body}>{p.body}</dd>
      </motion.div>
    ))}
  </dl>
);

export const Compliance = () => {
  const reduced = useReducedMotion();

  return (
    <main className={styles.compliance}>
      <motion.section
        className={styles.hero}
        initial={reduced ? undefined : { opacity: 0, y: 28 }}
        animate={reduced ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: EASE }}
      >

        <span className={styles.eyebrow} style={{ display: "flex", alignItems: "center", gap: "15px" }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 300 300" aria-hidden="true" focusable="false" style={{ display: 'block' }}>
            <g id="s" transform="translate(150,30)" fill="#9ca3af">
              <g id="c">
                <path id="t" d="M 0,-20 V 0 H 10" transform="rotate(18 0,-20)" />
                <use href="#t" transform="scale(-1,1)" />
              </g>
              <use href="#c" transform="rotate(72)" />
              <use href="#c" transform="rotate(144)" />
              <use href="#c" transform="rotate(216)" />
              <use href="#c" transform="rotate(288)" />
            </g>
            <use href="#s" transform="rotate(30 150,150) rotate(330 150,30)" />
            <use href="#s" transform="rotate(60 150,150) rotate(300 150,30)" />
            <use href="#s" transform="rotate(90 150,150) rotate(270 150,30)" />
            <use href="#s" transform="rotate(120 150,150) rotate(240 150,30)" />
            <use href="#s" transform="rotate(150 150,150) rotate(210 150,30)" />
            <use href="#s" transform="rotate(180 150,150) rotate(180 150,30)" />
            <use href="#s" transform="rotate(210 150,150) rotate(150 150,30)" />
            <use href="#s" transform="rotate(240 150,150) rotate(120 150,30)" />
            <use href="#s" transform="rotate(270 150,150) rotate(90 150,30)" />
            <use href="#s" transform="rotate(300 150,150) rotate(60 150,30)" />
            <use href="#s" transform="rotate(330 150,150) rotate(30 150,30)" />
          </svg>
          AI ACT AND GDPR
        </span>
        <h1 className={`st-display ${styles.heroTitle}`}>
          Compliance<br /> isn't just a label.
          <br />
          It's built on real, <br />working processes.
        </h1>
        <p className={styles.heroLead}>
          The transparency duties of the AI Act and the obligations of the GDPR land on
          whoever puts a system into service, never on the framework it was built with. So
          the work of the framework is to make that a configuration instead of a project.
          This page says what exists in the code today, and what does not.
        </p>
        <p className={styles.heroMeta}>
          Article 50 of the AI Act applies from 2 August 2026.
        </p>

        <aside className={styles.disclaimer} aria-labelledby="disclaimer-title">
          <h2 className={styles.disclaimerTitle} id="disclaimer-title">
            This is engineering documentation, not legal advice
          </h2>
          <p className={styles.disclaimerBody}>
            It describes mechanisms that exist in the code and says where each one stops. It
            certifies nothing, and nothing here says a deployment is compliant. That
            assessment belongs to whoever puts the system into service, made by their own
            counsel on their own facts. The point of all of it is to make that assessment
            possible and cheap, never to replace it.
          </p>
        </aside>
      </motion.section>

      {MECHANISMS.map((m) => (
        <Reveal key={m.title}>
          <motion.span variants={rise} className={styles.label}>
            {m.label}
          </motion.span>
          <motion.h2 variants={rise} className={styles.h2}>
            {m.title}
          </motion.h2>
          <motion.p variants={rise} className={styles.lead}>
            {m.lead}
          </motion.p>
          <PointList points={m.points} />
          {m.operator && (
            <motion.p variants={rise} className={styles.operatorNote}>
              <span className={styles.operatorTag}>OPERATOR CONTROLS</span>
              {m.operator}
            </motion.p>
          )}
        </Reveal>
      ))}

      <Reveal className={styles.yours}>
        <motion.span variants={rise} className={`${styles.label} ${styles.labelYours}`}>
          YOUR RESPONSIBILITY
        </motion.span>
        <motion.h2 variants={rise} className={styles.h2}>
          What the system does not do for you
        </motion.h2>
        <motion.p variants={rise} className={styles.lead}>
          Everything above is a mechanism. None of it is a determination, and this is the
          half a compliance page usually leaves out.
        </motion.p>
        <PointList points={OPERATOR_DUTIES} />
      </Reveal>

      <Reveal>
        <motion.h2 variants={rise} className={styles.h2}>
          The full documents
        </motion.h2>
        <motion.p variants={rise} className={styles.lead}>
          This page is the short version. Each document below names the symbol that
          implements a mechanism and the test that holds it in place, and each one ends with
          its own honest limits.
        </motion.p>
        <div className={styles.docs}>
          {DOCS.map((d) => (
            <motion.a
              key={d.file}
              variants={rise}
              className={`st-glass ${styles.doc}`}
              href={`${DOC_BASE}${d.file}`}
              target="_blank"
              rel="noreferrer"
            >
              <span className={styles.docFile}>{d.file} ↗</span>
              <span className={styles.docTitle}>{d.title}</span>
              <span className={styles.docBody}>{d.body}</span>
            </motion.a>
          ))}
        </div>
      </Reveal>

      <div className={styles.closing}>
        <a href="#/" className={styles.back}>
          Back to Studio
        </a>
      </div>
    </main>
  );
};

export default Compliance;
