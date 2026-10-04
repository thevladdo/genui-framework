/**
 * GenUI Framework
 * React framework for Generative User Interfaces
 * 
 * @package genui-framework
 * @version 1.0.0
 */

import './styles/genui.css';

// Components
export {
  GenUISection,
  GenUIZone,
  TextComponent,
  BentoComponent,
  ChartComponent,
  ButtonsComponent,
  TabsFeature,
  StepsSection,
  StatsBanner,
  TestimonialCarousel,
  PricingCards,
  ContentGrid,
  HeroBanner,
  CaseStudies,
  ComparisonBars,
  MetricsTrend,
  Faq,
  ProsCons,
  QuoteBlock,
  LogoWall,
  ComponentRenderer,
  ComponentErrorBoundary,
  GenUIDisclosureNotice,
} from './components';

export type {
  GenUIDisclosureNoticeProps,
  TextComponentProps,
  BentoComponentProps,
  ChartComponentProps,
  ButtonsComponentProps,
  ComponentRendererProps,
} from './components';

// Hooks
export {
  useGenUI,
  useZone
} from './hooks';

// Component Registry (custom design-system components)
export {
  registerGenUIComponent,
  getRegisteredGenUIComponent,
  getRegisteredGenUIComponentNames,
  BUILTIN_TYPES,
} from './registry';

export type {
  GenUICustomComponentDef,
  GenUIRegisteredComponent,
  GenUIRegisteredComponentProps,
} from './registry';

// Types
export type {
  // Theme
  GenUITheme,
  GenUISectionProps,
  
  // Component Data
  TextComponentData,
  BentoCard,
  BentoComponentData,
  ChartDataPoint,
  ChartComponentData,
  ButtonDef,
  ButtonsComponentData,
  ImageLayout,
  CTALink,
  FeatureTab,
  TabsFeatureData,
  StepItem,
  StepsSectionData,
  StatChange,
  StatItem,
  MovingStat,
  StatsBannerData,
  TestimonialItem,
  TestimonialCarouselData,
  PricingPlan,
  PricingCardsData,
  ContentGridItem,
  ContentGridData,
  HeroBannerData,
  CaseStudyMetric,
  CaseStudyItem,
  CaseStudiesData,
  ComparisonBar,
  ComparisonBarsData,
  TrendPoint,
  MetricsTrendData,
  FaqEntry,
  FaqData,
  ProsConsData,
  QuoteData,
  LogoItem,
  LogoWallData,
  ComponentType,
  ComponentData,
  GenUIComponent,
  
  // API Response
  ProfileUpdate,
  ProfileUpdateInstruction,
  BehaviorMeta,
  SanitizationReport,
  ChatSessionMeta,
  ResponseMeta,
  GenUIResponse,
  
  // User Profile
  UserPreference,
  UserProfile,
  
  // Hook Types
  BehaviorTrackerOptions,
  PrivacyLevel,
  UseGenUIOptions,
  UseGenUIReturn,

  // AI content disclosure
  GenUIDisclosure,
  GenUIDisclosureOptions,
  GenUIDisclosurePosition,
  GenUIProvenance,
} from './types';

// Utilities
export {
  initDB,
  getProfile,
  saveProfile,
  createEmptyProfile,
  profileScope,
  applyProfileUpdates,
  clearProfile,
  profileToApiFormat,
  getConversationHistory,
  addToHistory,
  clearHistory,
  BehaviorTracker,
  initBehaviorTracker,
  getBehaviorTracker,
  stopBehaviorTracker,
  GenUIError,
  DEFAULT_CHAT_DISCLOSURE_TEXT,
  DEFAULT_DISCLOSURE_TEXT,
  digitalSourceType,
  disclosureJsonLd,
  noticeComesFirst,
  parseDisclosure,
  sendGenUIEvents,
} from './utils';

export type {
  GenUIEvent,
  BehaviorRecord,
  ClickEvent,
  ScrollEvent,
  PageVisit,
  HoverEvent,
  ElementInteraction,
} from './utils';

export { GenUISection as default } from './components';
