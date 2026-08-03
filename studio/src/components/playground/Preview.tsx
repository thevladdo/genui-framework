/**
 * Live preview canvas.
 * Renders the REAL package components inside a GenUISection.
 */

import {
  BentoComponent,
  ButtonsComponent,
  CaseStudies,
  ChartComponent,
  ComparisonBars,
  ContentGrid,
  Faq,
  GenUIDisclosureNotice,
  GenUISection,
  HeroBanner,
  LogoWall,
  MetricsTrend,
  PricingCards,
  ProsCons,
  QuoteBlock,
  StatsBanner,
  StepsSection,
  TabsFeature,
  TestimonialCarousel,
  TextComponent,
  noticeComesFirst,
} from 'genui-framework';
import styles from './Playground.module.css';
import { isLightColor, toGenUITheme, type StudioTheme } from '../../lib/theme';

import heroImg from '../../../stock-img/milad-fakurian-61bq5E8i0WM-unsplash.jpg';
import tabsImg from '../../../stock-img/puscas-adryan-OLADYT0pz6o-unsplash.jpg';
import stepsImg from '../../../stock-img/egor-litvinov-t0OY8pONcf8-unsplash.jpg';
import gridImgA from '../../../stock-img/kir-3WUiwmyoNEw-unsplash.jpg';
import gridImgB from '../../../stock-img/brotherhood-studio--psmFP4VC8A-unsplash.jpg';
import avatarImg from '../../../stock-img/3d-render-lv_WRGCQJVc-unsplash.jpg';
import logo1 from '../../../logo-img/logo-1.svg?no-inline';
import logo2 from '../../../logo-img/logo-2.svg?no-inline';
import logo3 from '../../../logo-img/logo-3.svg?no-inline';
import logo4 from '../../../logo-img/logo-4.svg?no-inline';
import logo5 from '../../../logo-img/logo-5.svg?no-inline';
import logo6 from '../../../logo-img/logo-6.svg?no-inline';

const BUTTON_VARIANTS = [
  'primary', 'secondary', 'outline', 'ghost',
  'shine', 'gooey', 'expandIcon', 'ringHover',
] as const;

const BENTO_SIX = {
  cards: [
    {
      title: 'Six cards, one lead',
      description: 'The cells are unequal on purpose.',
      image: avatarImg
    },
    {
      title: 'Glass Caption Rail',
      description: 'The caption strip blurs the photo behind it: this is the only surface the blur slider reaches.',
      image: gridImgB,
    },
    {
      title: 'Claims',
      description: 'Fills beside the lead.',
      image: gridImgA
    },
    {
      title: 'Text-Only Degradation',
      description: 'No photo, so no glass to blur: the accent gradient takes the whole card and the text moves up into it.',
    },
    {
      title: 'Support', description: 'Marked featured, so it takes the large cell whatever its position in the list.',
      badge: 'Featured',
      featured: true,
      image: stepsImg,
    },
  ],
  columns: 3 as const,
};

const CHART_BAR = {
  chartType: 'bar' as const,
  title: 'Weekly sessions',
  data: [
    { label: 'Mon', value: 32 },
    { label: 'Tue', value: 48 },
    { label: 'Wed', value: 41 },
    { label: 'Thu', value: 74 },
    { label: 'Fri', value: 58 },
  ],
  showLegend: false,
  height: 220,
};

const CHART_DONUT = {
  chartType: 'donut' as const,
  title: 'Cache hit ratio',
  data: [
    { label: 'Fresh', value: 75 },
    { label: 'Stale', value: 17 },
    { label: 'Miss', value: 8 },
  ],
  height: 220,
};

const CREDITS: Array<{ photo: string; author: string; url: string }> = [
  { photo: 'https://unsplash.com/photos/OLADYT0pz6o', author: 'Puscas Adryan', url: 'https://unsplash.com/@adryan_studio' },
  { photo: 'https://unsplash.com/photos/lv_WRGCQJVc', author: '3D Render', url: 'https://unsplash.com/@3drender' },
  { photo: 'https://unsplash.com/photos/t0OY8pONcf8', author: 'Egor Litvinov', url: 'https://unsplash.com/@litvinov' },
  { photo: 'https://unsplash.com/photos/-psmFP4VC8A', author: 'BROTHERHOOD STUDIO', url: 'https://unsplash.com/@brotherhoodstudio' },
  { photo: 'https://unsplash.com/photos/3WUiwmyoNEw', author: 'Kir', url: 'https://unsplash.com/@kirrender' },
  { photo: 'https://unsplash.com/photos/61bq5E8i0WM', author: 'Milad Fakurian', url: 'https://unsplash.com/@fakurian' },
];

export const Preview = ({ theme }: { theme: StudioTheme }) => {
  const sectionClass = `${styles.previewSection} ${theme.mode === 'light' ? styles.sectionLight : ''
    }`.trim();

  const notice = theme.disclosureEnabled === 'on' ? (
    <GenUIDisclosureNotice
      text={theme.disclosureText || undefined}
      position={theme.disclosurePosition}
    />
  ) : null;
  const noticeFirst = noticeComesFirst(theme.disclosurePosition);

  return (
    <div
      className={styles.preview}
      data-accent-light={isLightColor(theme.accentColor) ? 'true' : 'false'}
    >
      <h1 className={`st-display ${styles.previewTitle}`}>Your theme applied</h1>

      <GenUISection theme={toGenUITheme(theme)}>
        <section className={sectionClass}>
          <p className="st-code-label">{'// hero banner: split (with image) vs centered (text-only)'}</p>
          <HeroBanner
            data={{
              variant: 'split',
              badge: 'New',
              headline: 'Interfaces that adapt to every user',
              subheadline: 'Personalized zones, generated in real time from your content.',
              primaryCta: { label: 'Get started', url: '#' },
              secondaryCta: { label: 'Learn more', url: '#' },
              imageUrl: heroImg,
            }}
          />
          <div style={{ height: 24 }} />
          <HeroBanner
            data={{
              variant: 'centered',
              headline: 'No image? Designed for it.',
              subheadline: 'The centered variant uses an accent gradient background.',
              primaryCta: { label: 'Explore', url: '#' },
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// tabs feature: per-tab with-image / text-only'}</p>
          <TabsFeature
            data={{
              badge: 'Plans',
              heading: 'Compare coverage',
              description: 'Each tab declares its own layout.',
              tabs: [
                {
                  label: 'Complete',
                  icon: '✦',
                  content: {
                    layout: 'with-image',
                    badge: 'Popular',
                    title: 'Complete protection',
                    description: 'Everything included, one monthly price. This tab renders the with-image layout.',
                    button: { label: 'Choose plan', url: '#' },
                    imageUrl: tabsImg,
                  },
                },
                {
                  label: 'Essential',
                  icon: '○',
                  content: {
                    layout: 'text-only',
                    title: 'Essential coverage',
                    description: 'The text-only layout: single centered column, emphasized typography, not a hole where an image should be.',
                    button: { label: 'Choose plan', url: '#' },
                  },
                },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// steps section: autoplay with progress'}</p>
          <StepsSection
            data={{
              layout: 'with-image',
              autoplay: true,
              interval: 4000,
              steps: [
                { title: 'Connect your content', description: 'Upload documents to the knowledge base.', imageUrl: stepsImg },
                { title: 'Drop a zone', description: 'One component, personalized per segment.', imageUrl: gridImgA },
                { title: 'Measure uplift', description: 'Holdout group proves it works.', imageUrl: gridImgB },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">
            {'// stats banner: the bare grid, then split with narration and movement'}
          </p>
          <StatsBanner
            data={{
              stats: [
                { value: '10M', label: 'Users reached' },
                { value: '99.9%', label: 'Uptime', description: 'last 12 months' },
                { value: '−82%', label: 'LLM cost', description: 'with segment cache' },
                { value: '+34%', label: 'CTR uplift' },
              ],
            }}
          />
          <div style={{ height: 120 }} />
          <StatsBanner
            data={{
              layout: 'split',
              eyebrow: 'Platform',
              title: 'This is the start of something new',
              description:
                'The same type as above, with the narration beside the grid instead of a row of numbers with nothing around them.',
              stats: [
                {
                  value: '500,000',
                  label: 'Monthly active users',
                  change: { direction: 'up', value: '+20.1%', sentiment: 'good' },
                },
                {
                  value: '20,105',
                  label: 'Daily active users',
                  change: { direction: 'down', value: '-2%', sentiment: 'bad' },
                },
                {
                  value: '$523,520',
                  label: 'Monthly recurring revenue',
                  change: { direction: 'up', value: '+8%', sentiment: 'good' },
                },
                {
                  value: '$1,052',
                  label: 'Cost per acquisition',
                  change: { direction: 'down', value: '-2%' },
                },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// testimonial carousel: avatar vs initials fallback'}</p>
          <TestimonialCarousel
            data={{
              testimonials: [
                {
                  quote: 'We rebranded the whole generated UI by overriding six tokens.',
                  name: 'Ada Lombardi',
                  role: 'Design Lead',
                  company: 'Acme',
                  avatarUrl: avatarImg,
                },
                {
                  quote: 'No avatar for this one, initials take over, nothing looks missing.',
                  name: 'Marco Bianchi',
                  role: 'CTO',
                  company: 'Globex',
                },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// pricing cards'}</p>
          <PricingCards
            data={{
              variant: 'compact',
              plans: [
                { name: 'Starter', price: '$0', period: 'mo', features: ['1 zone', 'Community support'], cta: { label: 'Start free', url: '#' } },
                { name: 'Pro', price: '$29', period: 'mo', features: ['Unlimited zones', 'Segment cache', 'Uplift analytics'], highlighted: true, flag: 'Recommended', cta: { label: 'Go Pro', url: '#' } },
                { name: 'Enterprise', price: 'Custom', features: ['Multi-tenant', 'Audit log', 'SLA'], cta: { label: 'Contact us', url: '#' } },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// content grid: per-item with-image / text-only'}</p>
          <ContentGrid
            data={{
              columns: 3,
              items: [
                { layout: 'with-image', category: 'Product', title: 'Designing for generated content', excerpt: 'Why image-optional is the default, not the edge case.', imageUrl: gridImgA, url: '#', date: 'Jun 2026' },
                { layout: 'with-image', category: 'Engineering', title: 'One render per segment', excerpt: 'How the SWR cache cuts LLM costs by orders of magnitude.', imageUrl: gridImgB, url: '#', date: 'Jun 2026' },
                { layout: 'text-only', category: 'Opinion', title: 'The text-only card is a design, not a fallback', excerpt: 'Accent rail, colored category, typography doing the work.', url: '#', date: 'Jun 2026' },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// case studies: with image + metrics vs text-first (degrades)'}</p>
          <CaseStudies
            data={{
              heading: 'Selected work',
              subheading: 'A few projects, and what changed for the people who run them.',
              cases: [
                {
                  title: 'A design system that ships itself',
                  summary: 'We rebuilt the component layer so product teams compose, not copy. Releases stopped waiting on design.',
                  name: 'Elena Rossi',
                  role: 'Head of Product',
                  imageUrl: gridImgA,
                  metrics: [
                    { value: '40%', label: 'Faster delivery', description: 'Feature lead time' },
                    { value: '3.5x', label: 'Reuse', description: 'Components across apps' },
                  ],
                },
                {
                  title: 'Analytics people actually read',
                  summary: 'One narrative dashboard replaced nine reports. No image needed: the case is text-first and the layout reflows around it.',
                  name: 'Marco Bianchi',
                  role: 'Operations Lead',
                  metrics: [
                    { value: '-82%', label: 'Reporting time', description: 'Weekly ops' },
                    { value: '99.9%', label: 'Data uptime', description: 'Last 12 months' },
                  ],
                },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">
            {'// metrics with trend: full, then without the curve, then two metrics only'}
          </p>
          <MetricsTrend
            data={{
              title: 'Powering teams with real-time insight,',
              tail: 'and the months that got us there.',
              metrics: [
                { value: '50,000+', label: 'Projects managed' },
                { value: '99.9%', label: 'Uptime', description: 'last 12 months' },
                { value: '1,200+', label: 'Enterprise clients' },
                { value: '1.2s', label: 'Avg. response time' },
              ],
              series: [
                { label: 'Jan', value: 20 },
                { label: 'Feb', value: 40 },
                { label: 'Mar', value: 36 },
                { label: 'Apr', value: 80 },
                { label: 'May', value: 72 },
                { label: 'Jun', value: 130 },
                { label: 'Jul', value: 160 },
              ],
            }}
          />
          <div style={{ height: 120 }} />
          <MetricsTrend
            data={{
              title: 'The same section with no series to draw.',
              metrics: [
                { value: '340', label: 'Contacts imported' },
                { value: '2', label: 'Automations live' },
                { value: '6', label: 'Seats in use' },
              ],
              series: [],
            }}
          />
          <div style={{ height: 120 }} />
          <MetricsTrend
            data={{
              title: 'Two metrics, which is the floor.',
              metrics: [
                { value: '14', label: 'Days left in trial' },
                { value: '40%', label: 'Onboarding complete' },
              ],
              series: [
                { label: 'Week 1', value: 10 },
                { label: 'Week 2', value: 40 },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">
            {'// comparison bars: full form, then two bars without callout, then no highlight at all'}
          </p>
          <ComparisonBars
            data={{
              title: 'Time to first personalized page',
              subtitle: 'Days from signup to a zone serving real traffic.',
              bars: [
                { label: 'GenUI', value: 4, suffix: 'd', highlighted: true, callout: 'Live in under a week' },
                { label: 'Suite A', value: 11, suffix: 'd' },
                { label: 'Suite B', value: 18, suffix: 'd' },
                { label: 'In-house', value: 45, suffix: 'd' },
              ],
            }}
          />
          <div style={{ height: 120 }} />
          <ComparisonBars
            data={{
              title: 'Cost per thousand renders',
              bars: [
                { label: 'Segment cache', value: 0.4, suffix: '$', highlighted: true },
                { label: 'Per request', value: 2.2, suffix: '$' },
              ],
            }}
          />
          <div style={{ height: 120 }} />
          <ComparisonBars
            data={{
              title: 'Where the reading time goes',
              bars: [
                { label: 'Hero', value: 38, suffix: '%' },
                { label: 'Cards', value: 27, suffix: '%' },
                { label: 'Pricing', value: 21, suffix: '%' },
                { label: 'Footer', value: 14, suffix: '%' },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">
            {'// faq: native details and summary, with the intro and then without'}
          </p>
          <Faq
            data={{
              title: 'Frequently asked questions',
              intro: 'Answers to what people ask most. Open one and the others close, where the browser supports it.',
              items: [
                {
                  question: 'Does this need JavaScript to open?',
                  answer: 'No. It is `details` and `summary`, so it opens, closes and answers the keyboard in server rendered HTML.',
                },
                {
                  question: 'Can an answer carry a link?',
                  answer: 'Yes, and it goes through the same URL whitelist as everything else: a link that was not in your input does not survive.',
                },
                {
                  question: 'Are these questions marked up for search engines?',
                  answer: 'Deliberately not. The zone already declares that a model wrote this content, and claiming the same text is the site official FAQ would say the opposite.',
                },
              ],
            }}
          />
          <div style={{ height: 96 }} />
          <Faq
            data={{
              title: 'The same section with no introduction',
              items: [
                { question: 'What changes without the intro?', answer: 'The header is the title alone, with no gap where a paragraph would have been.' },
                { question: 'How many entries fit?', answer: 'Two to twelve. One is a paragraph wearing a disclosure widget.' },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">
            {'// pros and cons: both sides, then one side only (full width), then no title'}
          </p>
          <ProsCons
            data={{
              title: 'Serverless rendering',
              pros: [
                'Cheap to run: you pay per render, not per idle hour',
                'Scales with traffic spikes **without** capacity planning',
                'Zero configuration to get the first zone live',
              ],
              cons: [
                'Cold starts add latency on the first request',
                'No offline mode for local development',
              ],
            }}
          />
          <div style={{ height: 120 }} />
          <ProsCons
            data={{
              title: 'What the documents actually said',
              prosHeading: 'Documented',
              consHeading: 'Not documented',
              pros: [
                'Two benefits were stated in the source material',
                'Nothing was written to balance the columns',
              ],
              cons: [],
            }}
          />
          <div style={{ height: 120 }} />
          <ProsCons
            data={{
              pros: ['Ships today', 'One dependency'],
              cons: ['Needs a migration', 'No admin UI yet'],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// quote / manifesto: full attribution vs statement-only (degrades)'}</p>
          <QuoteBlock
            data={{
              quote: 'Good software feels obvious in hindsight. Our job is to get to the obvious before anyone else does.',
              author: 'Giulia Conti',
              role: 'Creative Director',
              avatarUrl: avatarImg,
              logoUrl: logo1,
              logoLabel: 'Northwind',
            }}
          />
          <div style={{ height: 64 }} />
          <QuoteBlock
            data={{
              quote: 'We do not sell hours. We sell the difference between before and after.',
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// logo wall: clients (hover reveal) vs technologies (plain grid)'}</p>
          <LogoWall
            data={{
              heading: 'Selected clients',
              ctaLabel: 'See all clients',
              ctaUrl: '#',
              logos: [
                { imageUrl: logo1, alt: 'Northwind', url: '#' },
                { imageUrl: logo2, alt: 'Vertex', url: '#' },
                { imageUrl: logo3, alt: 'Lumen', url: '#' },
                { imageUrl: logo4, alt: 'Fjord', url: '#' },
                { imageUrl: logo5, alt: 'Cobalt', url: '#' },
                { imageUrl: logo6, alt: 'Aster', url: '#' },
              ],
            }}
          />
          <div style={{ height: 64 }} />
          <LogoWall
            data={{
              heading: 'Our stack',
              logos: [
                { imageUrl: logo2, alt: 'Vertex' },
                { imageUrl: logo4, alt: 'Fjord' },
                { imageUrl: logo6, alt: 'Aster' },
              ],
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// buttons variants'}</p>
          <ButtonsComponent
            data={{
              buttons: BUTTON_VARIANTS.map((style) => ({
                label: style === 'expandIcon' ? 'Expand Icon' : style[0].toUpperCase() + style.slice(1),
                style,
                showArrow: style === 'expandIcon',
              })),
              direction: 'horizontal',
              align: 'start',
            }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// bento container'}</p>
          <BentoComponent data={BENTO_SIX} />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// data visualization'}</p>
          <div className={styles.chartsRow}>
            <ChartComponent data={CHART_BAR} />
            <ChartComponent data={CHART_DONUT} />
          </div>
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// skeleton loaders'}</p>
          <div className="genui-zone-skeleton genui-zone-skeleton--bento" aria-hidden="true">
            {[1, 2, 3].map((i) => (
              <div key={i} className="genui-zone-skeleton__card">
                <div className="genui-zone-skeleton__title" />
                <div className="genui-zone-skeleton__text" />
                <div className="genui-zone-skeleton__text genui-zone-skeleton__text--short" />
              </div>
            ))}
          </div>
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">{'// typography'}</p>
          <TextComponent
            data={{
              content: '# Display heading\n\n## Section heading\n\nBody text: readable at 16px with **bold**, *emphasis* and `inline code`.',
              style: 'normal',
            }}
          />
          <TextComponent
            data={{ content: 'Note style: muted with accent rail.', style: 'note' }}
          />
        </section>

        <section className={sectionClass}>
          <p className="st-code-label">
            {'// ai disclosure: the notice a zone shows on generated content'}
          </p>
          <div className="genui-zone__content">
            {noticeFirst && notice}
            <div className="genui-zone-skeleton genui-zone-skeleton--bento">
              {[1, 2, 3].map((card) => (
                <div key={card} className="genui-zone-skeleton__card">
                  <div className="genui-zone-skeleton__title" />
                  <div className="genui-zone-skeleton__text" />
                  <div className="genui-zone-skeleton__text genui-zone-skeleton__text--short" />
                </div>
              ))}
            </div>
            {!noticeFirst && notice}
          </div>
        </section>
      </GenUISection>

      <footer className={styles.credits}>
        Demo photos:{' '}
        {CREDITS.map((credit, i) => (
          <span key={credit.author}>
            <a href={credit.photo} target="_blank" rel="noopener noreferrer" title={`Photo by ${credit.author} (${credit.url})`}>
              {credit.author}
            </a>
            {i < CREDITS.length - 1 ? ' · ' : ''}
          </span>
        ))}{' '}
        on <a href="https://unsplash.com" target="_blank" rel="noopener noreferrer">Unsplash</a>
      </footer>
    </div>
  );
};
