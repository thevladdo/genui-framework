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
// Generic Component Type
// ============================================

export type ComponentType = "text" | "bento" | "chart" | "buttons";

export type ComponentData =
  | TextComponentData
  | BentoComponentData
  | ChartComponentData
  | ButtonsComponentData;

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

export interface ResponseMeta {
  confidence: number;
  interactionType: "question" | "statement" | "command" | "feedback";
  topics: string[];
  sentiment: "positive" | "neutral" | "negative";
  behavior?: BehaviorMeta;
}

export interface GenUIResponse {
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

export interface BehaviorTrackerOptions {
  trackClicks?: boolean;
  trackScroll?: boolean;
  trackPageVisits?: boolean;
  trackHover?: boolean;
  hoverThreshold?: number;
  scrollDebounce?: number;
  maxEventsPerType?: number;
  enableHeatmapZones?: boolean;
}

export interface UseGenUIOptions {
  /** Backend API URL */
  apiUrl: string;
  /** User ID for profile management */
  userId?: string;
  /** Enable IndexedDB persistence */
  enablePersistence?: boolean;
  /** Enable behavior tracking (default: true) */
  enableBehaviorTracking?: boolean;
  /** Behavior tracker configuration */
  behaviorTrackingOptions?: BehaviorTrackerOptions;
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
    metadata?: Record<string, unknown>
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
