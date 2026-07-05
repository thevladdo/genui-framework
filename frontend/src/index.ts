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
  ComponentRenderer,
  ComponentErrorBoundary,
} from './components';

export type {
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
  GenUIProviderProps,
  
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
  StatItem,
  StatsBannerData,
  TestimonialItem,
  TestimonialCarouselData,
  PricingPlan,
  PricingCardsData,
  ContentGridItem,
  ContentGridData,
  HeroBannerData,
  ComponentType,
  ComponentData,
  GenUIComponent,
  
  // API Response
  ProfileUpdate,
  ProfileUpdateInstruction,
  BehaviorMeta,
  ResponseMeta,
  GenUIResponse,
  
  // User Profile
  UserPreference,
  UserProfile,
  
  // Hook Types
  BehaviorTrackerOptions,
  UseGenUIOptions,
  UseGenUIReturn,
} from './types';

// Utilities
export {
  initDB,
  getProfile,
  saveProfile,
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
} from './utils';

export type {
  BehaviorRecord,
  ClickEvent,
  ScrollEvent,
  PageVisit,
  HoverEvent,
  ElementInteraction,
} from './utils';

export { GenUISection as default } from './components';
