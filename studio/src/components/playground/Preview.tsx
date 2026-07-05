/**
 * Live preview canvas.
 * Renders the REAL package components inside a GenUISection.
 */

import {
  BentoComponent,
  ButtonsComponent,
  ChartComponent,
  ContentGrid,
  GenUISection,
  HeroBanner,
  PricingCards,
  StatsBanner,
  StepsSection,
  TabsFeature,
  TestimonialCarousel,
  TextComponent,
} from 'genui-framework';
import styles from './Playground.module.css';
import { isLightColor, toGenUITheme, type StudioTheme } from '../../lib/theme';

import heroImg from '../../../stock-img/milad-fakurian-61bq5E8i0WM-unsplash.jpg';
import tabsImg from '../../../stock-img/puscas-adryan-OLADYT0pz6o-unsplash.jpg';
import stepsImg from '../../../stock-img/egor-litvinov-t0OY8pONcf8-unsplash.jpg';
import gridImgA from '../../../stock-img/3d-render-lv_WRGCQJVc-unsplash.jpg';
import gridImgB from '../../../stock-img/brotherhood-studio--psmFP4VC8A-unsplash.jpg';
import avatarImg from '../../../stock-img/kir-3WUiwmyoNEw-unsplash.jpg';

const BUTTON_VARIANTS = [
  'primary', 'secondary', 'outline', 'ghost',
  'shine', 'gooey', 'expandIcon', 'ringHover',
] as const;

const BENTO_DATA = {
  cards: [
    {
      title: 'Bento Caption Rail',
      description: 'Featured surface with badge and hover motion.',
      badge: 'Featured',
      image: gridImgA,
    },
    {
      title: 'Frosted Glass Content',
      description: 'Standard surface: blur follows the slider.',
    },
    {
      title: 'Text-Only Degradation',
      description: 'No image? Accent gradient, never an empty box.',
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
          <p className="st-code-label">{'// stats banner'}</p>
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
          <p className="st-code-label">{'// containers'}</p>
          <BentoComponent data={BENTO_DATA} />
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
