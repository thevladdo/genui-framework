/**
 * GenUI Framework TypeScript Definitions
 * Core types for the Generative UI system
 */

// ============================================
// Theme & Styling Types
// ============================================

export interface GenUITheme {
  /** Number of slides visible in carousel (default: 4) */
  carouselNumOfSlides?: number;
  /** Auto-rotate carousel (default: false) */
  carouselAutoRotate?: boolean;
  /** Border radius for components (default: '30px') */
  borderRadius?: string;
  /** Primary color (default: '#fafafa') */
  primaryColor?: string;
  /** Secondary color (default: '#b2b2b2') */
  secondaryColor?: string;
  /** Background color (default: 'transparent') */
  backgroundColor?: string;
  /** Text color */
  textColor?: string;
  /** Accent color for highlights */
  accentColor?: string;
  /** Font family */
  fontFamily?: string;
  /** Base font size */
  fontSize?: string;
  /** Glassmorphism backdrop blur, e.g. '20px' (default from CSS: 20px) */
  glassBlur?: string;
  /** Spacing scale: multiplies every --genui-spacing-* token (default: 'base') */
  spacingScale?: "sm" | "base" | "lg";
  /** Color mode: emits data-theme on the section (default: dark via :root) */
  mode?: "light" | "dark";
  /** Surface hierarchy overrides (page -> card -> raised element) */
  surface1?: string;
  surface2?: string;
  surface3?: string;
  /** Text color on accent-colored surfaces (buttons, pills) */
  textOnAccent?: string;
  /** Radius scale: small elements (chips, inputs). borderRadius covers md */
  radiusSm?: string;
  /** Radius scale: large containers (heroes, panels) */
  radiusLg?: string;
  /** Radius scale: pills/avatars (e.g. '999px', or '0px' for square brands) */
  radiusFull?: string;
  /** Heading font weight for section components (default: 700) */
  fontWeightHeading?: string;
}

// ============================================
// Component Data Types
// ============================================

/** Text component data */
export interface TextComponentData {
  content: string;
  style?: "normal" | "emphasis" | "note" | "heading";
}

/** Single card in a Bento grid */
export interface BentoCard {
  title: string;
  description?: string;
  icon?: string;
  link?: string;
  image?: string;
  /** Optional badge text */
  badge?: string;
  /** Optional action button */
  action?: {
    label: string;
    onClick?: () => void;
    url?: string;
  };
  /** Opaque host data, passed through verbatim (never camelized) */
  metadata?: Record<string, unknown>;
}

/** Bento grid component data */
export interface BentoComponentData {
  cards: BentoCard[];
  columns?: 2 | 3 | 4;
  /** Gap between cards in pixels */
  gap?: number;
}

/** Single data point for charts */
export interface ChartDataPoint {
  label: string;
  value: number;
  /** Optional color for this data point */
  color?: string;
}

/** Chart component data */
export interface ChartComponentData {
  chartType: "bar" | "line" | "pie" | "area" | "donut";
  title?: string;
  data: ChartDataPoint[];
  xAxis?: string;
  yAxis?: string;
  /** Show legend (default: true for pie/donut) */
  showLegend?: boolean;
  /** Show grid lines */
  showGrid?: boolean;
  /** Chart height in pixels */
  height?: number;
}

/** Button variant styles */
export type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "shine" // Animated gradient shine
  | "gooey" // Blob animation on hover
  | "expandIcon" // Reveals arrow on hover
  | "ringHover"; // Ring outline on hover

/** Single button definition */
export interface ButtonDef {
  label: string;
  url?: string;
  onClick?: () => void;
  /** Button style variant - AI can choose any combination */
  style?: ButtonVariant;
  /** Show arrow icon (right side by default) */
  showArrow?: boolean;
  /** Arrow placement (only when showArrow is true) */
  arrowPlacement?: "left" | "right";
  /** Custom border radius override */
  borderRadius?: string;
  /** Custom background color override */
  backgroundColor?: string;
  /** Custom text color override */
  textColor?: string;
  /** Disabled state */
  disabled?: boolean;
  /** Size variant */
  size?: "sm" | "md" | "lg";
}

/** Buttons component data */
export interface ButtonsComponentData {
  buttons: ButtonDef[];
  /** Layout direction */
  direction?: "horizontal" | "vertical";
  /** Alignment */
  align?: "start" | "center" | "end";
  /** Gap between buttons in pixels */
  gap?: number;
}

// ============================================
// Enterprise section components
// ============================================

/**
 * Image-optional pattern (shared): components with an image render it
 * when layout is "with-image"; with "text-only" they CHANGE SHAPE
 * (accent gradients, emphasized typography) instead of leaving a hole.
 * The backend schema enforces coherence (text-only => no imageUrl needed).
 */
export type ImageLayout = "with-image" | "text-only";

export interface CTALink {
  label: string;
  url?: string;
}

/** One tab of a TabsFeature section */
export interface FeatureTab {
  label: string;
  /** Short icon: emoji or 1-2 chars (no icon library dependency) */
  icon?: string;
  content: {
    layout: ImageLayout;
    badge?: string;
    title: string;
    description?: string;
    button?: CTALink;
    imageUrl?: string;
  };
}

export interface TabsFeatureData {
  badge?: string;
  heading: string;
  description?: string;
  tabs: FeatureTab[];
}

export interface StepItem {
  title: string;
  description?: string;
  imageUrl?: string;
}

export interface StepsSectionData {
  layout: ImageLayout;
  steps: StepItem[];
  /** Auto-advance through steps */
  autoplay?: boolean;
  /** Milliseconds per step when autoplaying */
  interval?: number;
}

export interface StatItem {
  value: string;
  label: string;
  description?: string;
}

export interface StatsBannerData {
  stats: StatItem[];
  columns?: 2 | 3 | 4;
}

export interface TestimonialItem {
  quote: string;
  name: string;
  role?: string;
  company?: string;
  avatarUrl?: string;
}

export interface TestimonialCarouselData {
  testimonials: TestimonialItem[];
  autoplay?: boolean;
  interval?: number;
}

export interface PricingPlan {
  name: string;
  price: string;
  period?: string;
  description?: string;
  features: string[];
  cta?: CTALink;
  highlighted?: boolean;
  /** Badge on the highlighted plan, e.g. "Recommended" */
  flag?: string;
}

export interface PricingCardsData {
  plans: PricingPlan[];
  /** compact: cards only; detailed: cards + feature comparison table */
  variant?: "compact" | "detailed";
}

export interface ContentGridItem {
  layout: ImageLayout;
  title: string;
  category?: string;
  excerpt?: string;
  imageUrl?: string;
  url?: string;
  date?: string;
}

export interface ContentGridData {
  items: ContentGridItem[];
  columns?: 2 | 3 | 4;
}

export interface HeroBannerData {
  /** split: text+image 50/50 · centered: text over image/gradient · minimal: text only */
  variant: "split" | "centered" | "minimal";
  badge?: string;
  headline: string;
  subheadline?: string;
  primaryCta?: CTALink;
  secondaryCta?: CTALink;
  imageUrl?: string;
}

export interface CaseStudyMetric {
  value: string;
  label: string;
  description?: string;
}

export interface CaseStudyItem {
  title: string;
  summary?: string;
  name?: string;
  role?: string;
  imageUrl?: string;
  metrics?: CaseStudyMetric[];
}

export interface CaseStudiesData {
  heading?: string;
  subheading?: string;
  cases: CaseStudyItem[];
}

export interface QuoteData {
  quote: string;
  author?: string;
  role?: string;
  avatarUrl?: string;
  logoUrl?: string;
  logoLabel?: string;
}

export interface LogoItem {
  imageUrl: string;
  alt: string;
  url?: string;
}

export interface LogoWallData {
  heading?: string;
  logos: LogoItem[];
  ctaLabel?: string;
  ctaUrl?: string;
}

// ============================================
// Generic Component Type
// ============================================

export type ComponentType =
  | "text"
  | "bento"
  | "chart"
  | "buttons"
  | "tabs_feature"
  | "steps_section"
  | "stats_banner"
  | "testimonial_carousel"
  | "pricing_cards"
  | "content_grid"
  | "hero_banner"
  | "case_studies"
  | "quote"
  | "logo_wall";

export type ComponentData =
  | TextComponentData
  | BentoComponentData
  | ChartComponentData
  | ButtonsComponentData
  | TabsFeatureData
  | StepsSectionData
  | StatsBannerData
  | TestimonialCarouselData
  | PricingCardsData
  | ContentGridData
  | HeroBannerData
  | CaseStudiesData
  | QuoteData
  | LogoWallData;

export interface GenUIComponent {
  type: ComponentType;
  data: ComponentData;
  /** Optional layout hints */
  layout?: {
    width?: string;
    maxWidth?: string;
    margin?: string;
    padding?: string;
  };
}

// ============================================
// API Response Types
// ============================================

export interface ProfileUpdate {
  field: string;
  value: unknown;
  confidence: number;
  source: string;
  timestamp: string;
}

export interface ProfileUpdateInstruction {
  shouldUpdate: boolean;
  updates: ProfileUpdate[];
}

export interface BehaviorMeta {
  engagementScore: number;
  userType: "explorer" | "focused" | "scanner" | "deep_reader" | "casual";
  sessionSummary: string;
  insightsCount: number;
  uiAdjustments: Array<{
    type: string;
    target: string;
    suggestion: string;
  }>;
}

/**
 * What the backend guarantee chain removed from the model's output
 * (validate → URL whitelist → numeric grounding → content policy).
 * Same shape for zone renders and /query responses.
 */
export interface SanitizationReport {
  /** URLs stripped because they were not present in the input */
  removedUrls: string[];
  /** Human-readable summaries of components dropped by validation */
  droppedComponents: string[];
  /** Displayed numbers removed because they did not trace to the input */
  removedNumbers: string[];
  /** Banned terms (per-tenant content policy) that were dropped/redacted */
  policyViolations: string[];
}

export interface ResponseMeta {
  confidence: number;
  interactionType: "question" | "statement" | "command" | "feedback";
  topics: string[];
  sentiment: "positive" | "neutral" | "negative";
  behavior?: BehaviorMeta;
  /** Present when the backend reports what its guarantee chain removed */
  sanitization?: SanitizationReport;
}

export interface GenUIResponse {
  /** Component contract version of the responding backend (undefined on older backends) */
  contractVersion?: number;
  text: string;
  components: GenUIComponent[];
  sources: Array<{ title: string; url: string }>;
  suggestedActions: string[];
  profileUpdates: ProfileUpdateInstruction;
  meta: ResponseMeta;
}

// ============================================
// User Profile Types
// ============================================

export interface UserPreference {
  value: unknown;
  confidence: number;
  updatedAt: string;
}

export interface UserProfile {
  userId: string;
  preferences: Record<string, UserPreference>;
  interests: Record<string, UserPreference>;
  context: Record<string, UserPreference>;
  demographic: Record<string, UserPreference>;
  behavior: Record<string, UserPreference>;
  createdAt: string;
  updatedAt: string;
}

// ============================================
// Hook Types
// ============================================

export type { PrivacyLevel } from "../utils/privacy";
import type { PrivacyLevel } from "../utils/privacy";

export interface BehaviorTrackerOptions {
  trackClicks?: boolean;
  trackScroll?: boolean;
  trackPageVisits?: boolean;
  trackHover?: boolean;
  hoverThreshold?: number;
  scrollDebounce?: number;
  maxEventsPerType?: number;
  enableHeatmapZones?: boolean;
  /** Capture contract: 'strict' | 'balanced' (default) | 'off' — see README */
  privacy?: PrivacyLevel;
  /** false = never track, true = track (overrides DNT/GPC), unset = no consent gating */
  consent?: boolean;
}

export interface UseGenUIOptions {
  /** Backend API URL */
  apiUrl: string;
  /** Client API key (sent as X-API-Key). Required when the backend has CLIENT_API_KEYS configured */
  apiKey?: string;
  /**
   * Signed user identity token (sent as X-User-Token). Required alongside
   * userId when the backend has USER_TOKEN_SECRETS configured; mint it
   * server-side with sign_user_token() and pass it to the client.
   */
  userToken?: string;
  /** User ID for profile management */
  userId?: string;
  /** Enable IndexedDB persistence */
  enablePersistence?: boolean;
  /** Enable behavior tracking (default: true) */
  enableBehaviorTracking?: boolean;
  /** Behavior tracker configuration */
  behaviorTrackingOptions?: BehaviorTrackerOptions;
  /**
   * Privacy level of the behavior tracker (default: 'balanced' — text
   * PII-redacted, form fields never captured, DNT/GPC honored).
   * 'strict' = structural signals only; 'off' = raw capture (explicit choice).
   */
  privacy?: PrivacyLevel;
  /**
   * Consent hook for your CMP: pass false until the user consents (nothing is
   * tracked), true once granted (overrides DNT/GPC). Unset = no consent gating.
   */
  consent?: boolean;
  /** Callback when profile is updated */
  onProfileUpdate?: (profile: UserProfile) => void;
  /** Callback on API error */
  onError?: (error: Error) => void;
}

export interface UseGenUIReturn {
  /** Send a query to the backend */
  query: (text: string) => Promise<GenUIResponse>;
  /** Current loading state */
  isLoading: boolean;
  /** Last error if any */
  error: Error | null;
  /** Current user profile */
  profile: UserProfile | null;
  /** Manually update profile */
  updateProfile: (updates: Partial<UserProfile>) => void;
  /** Clear profile data */
  clearProfile: () => void;
  /** Conversation history */
  history: Array<{ role: "user" | "assistant"; content: string }>;
  /** Clear conversation history */
  clearHistory: () => void;
  /** Behavior tracker instance */
  behaviorTracker: unknown | null;
  /** Track a custom element interaction */
  trackInteraction: (
    elementId: string,
    elementType: string,
    interactionType: "click" | "hover" | "focus" | "scroll-into-view",
    metadata?: Record<string, unknown>,
  ) => void;
  /** Track navigation to a new page/route */
  trackNavigation: (path: string, title?: string) => void;
}

// ============================================
// Provider Props
// ============================================

export interface GenUISectionProps {
  /** Child components */
  children?: React.ReactNode;
  /** Theme configuration */
  theme?: GenUITheme;
  /** API URL for backend */
  apiUrl?: string;
  /** Custom class name */
  className?: string;
  /** Custom styles */
  style?: React.CSSProperties;
}

export interface GenUIProviderProps {
  children: React.ReactNode;
  theme?: GenUITheme;
  apiUrl: string;
  userId?: string;
}
