<div align="center">

# GenUI Framework

**Generative User Interfaces for Intelligent Web Applications**<br />
_A full-stack framework for building AI-powered, profile-aware, dynamically generated UI components_

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE) [![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue.svg)](https://www.typescriptlang.org/) [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![React 18+](https://img.shields.io/badge/react-18+-61dafb.svg)](https://react.dev/) 
[![DOI](https://zenodo.org/badge/1133794652.svg)](https://doi.org/10.5281/zenodo.18237228)

<div align="center">
  <br />
  <img src="./GenUI.png" alt="genui-framework logo" width="100%" height="auto" />
  <br /><br /><br />
</div>

[Overview](#-overview) • [Usage Guide](#-usage-guide) • [Components](#-components) • [Hooks](#-hooks) • [Theming](#-theming) • [API Reference](#-backend-api-reference) • [Architecture](#️-architecture) 

</div>

---

## 🌟 Overview

GenUI System is a comprehensive framework for building **Generative User Interfaces:** dynamic, AI-driven UI components that adapt to user profiles, behavior, and context. The system combines a React frontend framework with a Python backend to deliver personalized content in real-time.

<div align="center">

#### **Profile-Aware** | **Real-Time Generation** | **RAG-Enhanced** | **Premium Components**

</div>

---

## Key Features

<table>
<tr>
<td width="50%" valign="top">

### 🎨 **Frontend Framework**

- **GenUIZone**: Declarative zones with 22+ configurable props
- **Premium Components**: Glassmorphism bento grids, 8 button variants, charts, styled text
- **Behavior Tracking**: Automatic monitoring of clicks, scrolls, hovers, navigation
- **Profile Persistence**: IndexedDB-based local storage with sync
- **Theme System**: CSS-variable based customization
- **Pinned Content**: Guarantee certain content always displays

</td>
<td width="50%" valign="top">

### 🧠 **Backend Intelligence**

- **Multi-Agent Architecture**: ResponseAgent, ZoneAgent, ProfileAgent, BehaveAgent
- **RAG Integration**: Qdrant vector store with semantic search
- **Profile Learning**: Automatic preference extraction from conversations
- **Contextual Prompting**: Developer-controlled prompt engineering
- **Flexible LLM Support**: OpenAI, Anthropic, any OpenAI-compatible API
- **Debug Metadata**: Confidence scores, reasoning, profile factors

</td>
</tr>
</table>

---

# 📖 Usage Guide

## 🚀 Quick Start

### Installation

**Frontend (React)**

> ⚠️ The npm package is not yet published. Install locally:

```bash
# Clone the repository
git clone https://github.com/vladdo/genui-framework.git
cd genui-framework/frontend

# Install dependencies and build
npm install
npm run build

# Link locally for use in other projects
npm link

# In your project directory:
npm link genui-framework
```

**Backend (Python)**

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Configure your API keys
```

### Environment Configuration

Create a `.env` file in the backend directory:

```env
# Required
OPENAI_API_KEY=your_openai_key

# Optional - RAG
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Optional - Model selection
RESPONSE_MODEL=gpt-4o-mini
ZONE_MODEL=gpt-4o-mini
```

### Start the Backend

```bash
cd backend
uvicorn api.main:app --reload --port 8000
```

### Import Styles in Your App

```tsx
// In your main entry file (e.g., main.tsx or index.tsx)
// If using npm link:
import "genui-framework/dist/styles.css";

// Or copy styles directly from the cloned repo:
// import "./path-to/genui-framework/frontend/dist/styles.css";
```

---

## 🎯 Core Components

### GenUIZone — AI-Powered Content Zones

The `GenUIZone` component automatically fetches personalized content from the backend based on:

- **User Profile**: Stored preferences, interests, demographics
- **Behavior Data**: Click patterns, scroll depth, navigation history
- **Developer Prompts**: Base prompts + context prompts for fine control
- **Pinned Content**: Guaranteed content that always displays

#### Basic Usage

```tsx
import { GenUIZone } from "genui-framework";

<GenUIZone
  apiUrl="http://localhost:8000"
  zoneId="homepage-recommendations"
  basePrompt="Show recommended articles"
  preferredComponentType="bento"
  maxItems={6}
/>;
```

#### Full Props Reference

```tsx
interface GenUIZoneProps {
  // === Required ===
  apiUrl: string; // Backend API URL
  zoneId: string; // Unique zone identifier

  // === Prompt Engineering ===
  basePrompt?: string; // What the zone should display
  contextPrompt?: string; // Additional context for AI (page location, user segment, etc.)

  // === Content Control ===
  pinnedContent?: PinnedContent[]; // Content that MUST be displayed
  preferredComponentType?: "bento" | "chart" | "text" | "buttons";
  maxItems?: number; // Max items to generate (default: 6)

  // === User Context ===
  userId?: string; // User ID for profile lookup
  currentPage?: string; // Current page path
  pageMetadata?: Record<string, unknown>; // Custom page context

  // === Behavior ===
  loadOnMount?: boolean; // Auto-load on mount (default: true)
  refreshInterval?: number; // Auto-refresh in ms (0 = disabled)

  // === Theming ===
  theme?: GenUITheme; // Theme overrides
  className?: string; // CSS class
  style?: React.CSSProperties; // Inline styles

  // === Custom Render States ===
  loadingComponent?: React.ReactNode;
  errorComponent?: React.ReactNode | ((error: Error) => React.ReactNode);
  emptyComponent?: React.ReactNode; // Shown when AI returns empty
  showLoadingSkeleton?: boolean;

  // === Callbacks ===
  onRender?: (components: GenUIComponent[]) => void;
  onError?: (error: Error) => void;

  // === Debug ===
  debug?: boolean; // Shows reasoning, confidence, profile factors
}
```

---

### Pinned Content — Guaranteed Display

Pinned content ensures certain items **always** appear in the zone, regardless of what the AI generates. The AI will include these items alongside its personalized selections.

```tsx
interface PinnedContent {
  type: "link" | "article" | "document" | "custom";
  title: string;
  url?: string;
  description?: string;
  id?: string;
  metadata?: Record<string, unknown>;
}
```

#### Example: Pinned Sponsor Content

```tsx
<GenUIZone
  zoneId="news-feed"
  apiUrl="http://localhost:8000"
  pinnedContent={[
    {
      type: "article",
      title: "Sustainability Report 2024",
      url: "/reports/sustainability-2024",
      description: "Our commitment to the environment",
      metadata: { category: "sustainability", sponsor: true },
    },
    {
      type: "link",
      title: "Investor Relations",
      url: "/investors",
      description: "Financial information and reports",
    },
  ]}
  preferredComponentType="bento"
  maxItems={6} // AI will fill remaining slots with personalized content
/>
```

---

### Context Prompts — Fine-Grained AI Control

Use `contextPrompt` to give the AI detailed instructions about the zone's purpose, available content, and selection criteria.

#### Example: Article Selection with Available Content List

```tsx
const articlesContext = useMemo(() => {
  return articles
    .map(
      (a, i) =>
        `ID ${i}: "${a.title}" (Link: ${a.link}, Img: ${a.src}, Tag: ${a.tag[0]})`
    )
    .join("; ");
}, [articles]);

const contextPrompt = `
  You are an intelligent content curator for a corporate website.
  
  AVAILABLE CONTENT (Use ONLY these items):
  [${articlesContext}]
  
  SELECTION RULES:
  1. Select ${maxItems} items that best match the user's profile and interests.
  2. If user has interest in "sustainability", prioritize content tagged with that topic.
  3. If user role is "investor", prioritize financial and business content.
  4. For new users with no profile, show a diverse mix.
  
  OUTPUT REQUIREMENTS:
  - Return a 'bento' component with cards.
  - Each card MUST use the exact image, title, badge, and link from the input list.
  - Do NOT invent new content.
`;

<GenUIZone
  zoneId="homepage-for-you"
  apiUrl="http://localhost:8000"
  basePrompt="Display personalized article recommendations"
  contextPrompt={contextPrompt}
  preferredComponentType="bento"
  maxItems={6}
/>;
```

---

### Page Metadata — Contextual Awareness

Pass `pageMetadata` to give the AI awareness of the current page context:

```tsx
<GenUIZone
  zoneId="related-content"
  apiUrl="http://localhost:8000"
  currentPage="/products/electric-cars"
  pageMetadata={{
    pageType: "product",
    productCategory: "transportation",
    productId: "ETR-500",
    userSegment: "business",
    region: "europe",
  }}
  basePrompt="Show related products and content"
/>
```

---

### Fallback Content — Client-Side Fallbacks

When the AI returns empty results (e.g., backend unavailable, no matching content), use `emptyComponent` and `errorComponent` to display fallback content:

```tsx
import { GenUIZone, BentoComponent, GenUISection } from "genui-framework";

const fallbackBentoData = {
  cards: articles.slice(0, 6).map((a) => ({
    title: a.title,
    description: a.tag?.[0] || "",
    link: a.link || "#",
    image: a.src,
    badge: a.tag?.[0],
  })),
  columns: 3,
};

const FallbackBento = () => (
  <GenUISection className="genui-layout-complex">
    <BentoComponent data={fallbackBentoData} />
  </GenUISection>
);

<GenUIZone
  zoneId="recommendations"
  apiUrl="http://localhost:8000"
  emptyComponent={<FallbackBento />}
  errorComponent={() => <FallbackBento />}
/>;
```

---

## 🪝 Hooks

### useGenUI — Conversational AI Interface

For chat-based interactions with automatic behavior tracking and profile learning:

```tsx
import { useGenUI } from "genui-framework";

function ChatBot() {
  const {
    query, // Send message to AI
    isLoading, // Loading state
    error, // Last error
    profile, // Current user profile
    updateProfile, // Manual profile update
    clearProfile, // Reset profile
    history, // Conversation history
    clearHistory, // Clear conversation
    behaviorTracker, // Access behavior tracker
    trackInteraction, // Track custom events
    trackNavigation, // Track page navigation
  } = useGenUI({
    apiUrl: "http://localhost:8000",
    userId: getUserId(),
    enablePersistence: true,
    enableBehaviorTracking: true,
    behaviorTrackingOptions: {
      trackClicks: true,
      trackScroll: true,
      trackPageVisits: true,
      trackHover: true,
      hoverThreshold: 500, // ms before hover counts
      scrollDebounce: 100, // ms debounce
      maxEventsPerType: 100, // Memory limit
      enableHeatmapZones: true,
    },
    onProfileUpdate: (profile) => console.log("Profile updated:", profile),
    onError: (error) => console.error("GenUI error:", error),
  });

  const handleSend = async (message: string) => {
    try {
      const response = await query(message);
      // response.text - AI text response
      // response.components - Generated UI components
      // response.sources - Source citations
      // response.suggestedActions - Follow-up suggestions
      // response.profileUpdates - Profile learning data
      // response.meta - Confidence, sentiment, interaction type
    } catch (err) {
      // Handle error
    }
  };

  return <ChatUI onSend={handleSend} history={history} loading={isLoading} />;
}
```

### useZone — Zone-Level Control

For low-level zone control when you need more customization:

```tsx
import { useZone } from "genui-framework";

const {
  components, // Rendered GenUI components
  isLoading, // Loading state
  error, // Error state
  meta, // Render metadata
  pinnedContentIncluded, // Which pinned items were included
  render, // Manually trigger render
  refresh, // Force re-render (clears first)
} = useZone({
  apiUrl: "http://localhost:8000",
  zoneId: "my-zone",
  basePrompt: "Show content",
  loadOnMount: true,
  refreshInterval: 30000, // Auto-refresh every 30s
});

// Access metadata
console.log(meta?.confidence); // 0.87
console.log(meta?.reasoning); // "Selected based on user interests..."
console.log(meta?.profileFactors); // ["interests.technology", "demographic.role"]
console.log(meta?.personalizationApplied); // true
```

---

## 🎨 Components

### BentoComponent — Glassmorphism Grid

A premium card grid with hover animations and responsive layouts:

```tsx
import { BentoComponent } from "genui-framework";

<BentoComponent
  data={{
    cards: [
      {
        title: "Feature One",
        description: "Optional description text",
        image: "/images/feature1.jpg",
        badge: "New", // Top-left badge
        link: "/features/one",
        action: {
          // Optional action button
          label: "Learn More",
          url: "/features/one",
        },
      },
      // ... more cards
    ],
    columns: 3, // 2, 3, or 4
    gap: 16, // Gap in pixels
  }}
/>;
```

### ButtonsComponent — Animated Buttons

8 premium button variants with animated arrows:

```tsx
import { ButtonsComponent } from "genui-framework";

<ButtonsComponent
  data={{
    buttons: [
      {
        label: "Get Started",
        url: "/start",
        style: "shine", // Animated gradient sweep
        showArrow: true, // Arrow shows on all buttons by default
        arrowPlacement: "right", // "left" or "right"
        size: "lg", // "sm" | "md" | "lg"
        borderRadius: "8px", // Custom override
        backgroundColor: "#3b82f6", // Custom override
        textColor: "#ffffff", // Custom override
      },
      {
        label: "Learn More",
        style: "outline",
        showArrow: false, // Explicitly hide arrow
      },
      {
        label: "Contact",
        style: "gooey", // Blob morph on hover
      },
      {
        label: "Explore",
        style: "ringHover", // Ring outline on hover
      },
      {
        label: "Details",
        style: "expandIcon", // Arrow reveals on hover
      },
    ],
    direction: "horizontal", // or "vertical"
    align: "center", // "start" | "center" | "end"
    gap: 12, // Custom gap in pixels
  }}
/>;
```

#### Button Variants

| Variant      | Description                              |
| ------------ | ---------------------------------------- |
| `primary`    | Solid accent color with brightness hover |
| `secondary`  | Semi-transparent with backdrop blur      |
| `outline`    | Transparent with border, fills on hover  |
| `ghost`      | Minimal, text only                       |
| `shine`      | Animated gradient that sweeps across     |
| `gooey`      | Blob morphing effect on hover            |
| `expandIcon` | Arrow icon reveals on hover              |
| `ringHover`  | Ring outline appears on hover            |

### ChartComponent — Data Visualization

```tsx
import { ChartComponent } from "genui-framework";

<ChartComponent
  data={{
    chartType: "bar", // "bar" | "line" | "pie" | "area" | "donut"
    title: "Monthly Sales",
    data: [
      { label: "Jan", value: 100, color: "#3b82f6" },
      { label: "Feb", value: 150 },
      { label: "Mar", value: 200 },
    ],
    xAxis: "Month",
    yAxis: "Sales ($)",
    showLegend: true,
    showGrid: true,
    height: 300,
  }}
/>;
```

### TextComponent — Styled Text

```tsx
import { TextComponent } from "genui-framework";

<TextComponent
  data={{
    content: "This is **markdown** supported text with _emphasis_.",
    style: "normal", // "normal" | "emphasis" | "note" | "heading"
  }}
/>;
```

---

## 🎭 Theming

### GenUITheme Properties

```tsx
interface GenUITheme {
  borderRadius?: string; // Default: '30px'
  primaryColor?: string; // Default: '#fafafa'
  secondaryColor?: string; // Default: '#b2b2b2'
  backgroundColor?: string; // Default: 'transparent'
  textColor?: string;
  accentColor?: string; // Used for buttons, highlights
  fontFamily?: string;
  fontSize?: string;
}
```

### Applying Themes

```tsx
import { GenUISection, GenUIZone } from 'genui-framework';

<GenUISection
  theme={{
    borderRadius: '16px',
    accentColor: '#3b82f6',
    primaryColor: '#1e1e1e',
    textColor: '#ffffff',
    fontFamily: "'Inter', sans-serif",
  }}
>
  <GenUIZone ... />
</GenUISection>
```

### CSS Variables

The framework uses CSS custom properties that you can override:

```css
:root {
  --genui-border-radius: 30px;
  --genui-primary-color: #fafafa;
  --genui-secondary-color: #b2b2b2;
  --genui-accent-color: #3b82f6;
  --genui-text-primary: #ffffff;
  --genui-text-secondary: rgba(255, 255, 255, 0.8);
  --genui-glass-blur: 12px;
  --genui-glass-border: 1px solid rgba(255, 255, 255, 0.1);
}
```

---

## 🔧 Behavior Tracking

The framework automatically tracks user behavior and sends it to the backend for personalization:

| Event Type     | What's Tracked                          |
| -------------- | --------------------------------------- |
| **Clicks**     | Element ID, type, page, coordinates     |
| **Scrolls**    | Depth percentage, direction, velocity   |
| **Hovers**     | Element ID, duration, timeout threshold |
| **Navigation** | Page path, title, timestamp             |
| **Zone Views** | When GenUI zones enter viewport         |

### Manual Tracking

```tsx
const { trackInteraction, trackNavigation } = useGenUI({ ... });

// Track custom element interaction
<button
  onClick={() => {
    trackInteraction('cta-signup', 'button', 'click', {
      source: 'header',
      campaign: 'summer-sale'
    });
  }}
>
  Sign Up
</button>

// Track SPA navigation
function navigateTo(path: string) {
  trackNavigation(path, document.title);
  router.push(path);
}
```

---

## 🌐 Backend API Reference

### POST /api/v1/query — Chat Interface

```http
POST /api/v1/query
Content-Type: application/json

{
  "query": "What products do you recommend?",
  "user_profile": {
    "preferences": { "role": { "value": "investor", "confidence": 0.9 } },
    "interests": { "sustainability": { "value": true, "confidence": 0.8 } },
    "demographic": { "region": { "value": "europe", "confidence": 0.7 } }
  },
  "conversation_history": [
    { "role": "user", "content": "Hello" },
    { "role": "assistant", "content": "Hi! How can I help?" }
  ],
  "behavior_data": {
    "clickCount": 15,
    "maxScrollDepth": 85,
    "userType": "deep_reader",
    "navigationPath": ["/", "/products", "/products/trains"]
  }
}
```

**Response:**

```json
{
  "text": "Based on your interest in sustainability, I recommend...",
  "components": [
    {
      "type": "bento",
      "data": { "cards": [...], "columns": 3 }
    }
  ],
  "sources": [
    { "title": "Sustainability Report", "url": "/reports/sustainability" }
  ],
  "suggested_actions": ["View all products", "Contact sales"],
  "profile_updates": {
    "should_update": true,
    "updates": [
      { "field": "interests.products", "value": "trains", "confidence": 0.75 }
    ]
  },
  "meta": {
    "confidence": 0.92,
    "interaction_type": "question",
    "topics": ["products", "recommendations"],
    "sentiment": "positive"
  }
}
```

### POST /api/v1/zone/render — Zone Rendering

```http
POST /api/v1/zone/render
Content-Type: application/json

{
  "zone_id": "homepage-recommendations",
  "base_prompt": "Show recommended articles for the user",
  "context_prompt": "User is on the homepage, interested in technology and sustainability",
  "pinned_content": [
    { "type": "article", "title": "Annual Report", "url": "/reports/annual" }
  ],
  "preferred_component_type": "bento",
  "max_items": 6,
  "user_profile": { ... },
  "behavior_data": { ... },
  "current_page": "/",
  "page_metadata": { "section": "hero", "campaign": "summer-2024" }
}
```

**Response:**

```json
{
  "zone_id": "homepage-recommendations",
  "components": [
    {
      "type": "bento",
      "data": {
        "cards": [
          { "title": "Annual Report", "link": "/reports/annual", ... },
          { "title": "Green Initiative", "link": "/sustainability", ... }
        ],
        "columns": 3
      }
    }
  ],
  "pinned_content_included": ["/reports/annual"],
  "personalization_applied": true,
  "meta": {
    "confidence": 0.87,
    "reasoning": "Selected sustainability and tech content based on user profile",
    "profile_factors": ["interests.sustainability", "interests.technology"]
  },
  "rendered_at": "2024-01-15T10:30:00Z"
}
```

---

# 🏗️ Architecture

## Project Structure

```
genui-framework/
├── backend/                              # Python FastAPI backend
│   ├── agents/                           # AI agent implementations
│   │   ├── response_agent.py             # Chat response generation
│   │   ├── zone_agent.py                 # Zone content rendering
│   │   ├── profile_agent.py              # Profile learning & extraction
│   │   ├── behave_agent.py               # Behavior analysis
│   │   └── orchestrator.py               # Multi-agent coordination
│   ├── api/                              # REST API endpoints
│   │   ├── main.py                       # FastAPI app, CORS, middleware
│   │   └── zone_router.py                # Zone rendering routes
│   ├── rag/                              # Retrieval-Augmented Generation
│   │   ├── vector_store.py               # Qdrant vector store wrapper
│   │   └── retriever.py                  # Document retrieval & context building
│   ├── config/                           # Configuration
│   │   └── settings.py                   # Environment variables & defaults
│   ├── utils/                            # Shared utilities
│   └── requirements.txt                  # Python dependencies
│
└── frontend/
    └── genui-framework/                  # React component library (npm package)
        ├── src/
        │   ├── components/               # React components
        │   │   ├── GenUISection.tsx      # Theme provider wrapper
        │   │   ├── GenUIZone.tsx         # AI zone container (22 props)
        │   │   ├── BentoComponent.tsx    # Glassmorphism grid
        │   │   ├── ButtonsComponent.tsx  # 8 animated button variants
        │   │   ├── ChartComponent.tsx    # Recharts integration
        │   │   ├── TextComponent.tsx     # Markdown text
        │   │   └── ComponentRenderer.tsx # Dynamic component factory
        │   ├── hooks/                    # React hooks
        │   │   ├── useGenUI.ts           # Chat hook (10 return values)
        │   │   └── useZone.ts            # Zone hook (7 return values)
        │   ├── styles/                   # CSS
        │   │   └── genui.css             # Glassmorphism theme, animations
        │   ├── types/                    # TypeScript definitions
        │   │   └── index.ts              # All exported types
        │   └── utils/                    # Utilities
        │       ├── indexeddb.ts          # Profile & history persistence
        │       └── behaviorTracker.ts    # Event tracking (8 options)
        ├── dist/                         # Built output
        ├── package.json
        └── rollup.config.js
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐              │
│  │ GenUIZone   │    │  useGenUI   │    │ BehaviorTracker │              │
│  │ (zones)     │    │  (chat)     │    │ (analytics)     │              │
│  └──────┬──────┘    └──────┬──────┘    └────────┬────────┘              │
│         │                  │                    │                       │
│         │    ┌─────────────┴─────────────┐      │                       │
│         │    │      IndexedDB            │      │                       │
│         │    │  - User Profile           │◄─────┘                       │
│         │    │  - Conversation History   │                              │
│         │    └─────────────┬─────────────┘                              │
│         │                  │                                            │
│         └────────┬─────────┘                                            │
│                  │                                                      │
│                  ▼                                                      │
│   HTTP POST /api/v1/zone/render  or  /api/v1/query                      │
│   { zone_id, prompts, user_profile, behavior_data, pinned_content }     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              BACKEND (FastAPI)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐                                                       │
│  │    Router    │                                                       │
│  │  zone_router │                                                       │
│  └──────┬───────┘                                                       │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │                        AGENT SYSTEM                         │        │
│  │                                                             │        │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │        │
│  │  │ ZoneAgent    │  │ResponseAgent │  │ ProfileAgent │       │        │
│  │  │ (zone render)│  │ (chat)       │  │ (learning)   │       │        │
│  │  └──────┬───────┘  └──────────────┘  └──────────────┘       │        │
│  │         │                                                   │        │
│  │         ▼                                                   │        │
│  │  ┌──────────────┐  ┌──────────────┐                         │        │
│  │  │ RAG System   │  │   LLM API    │                         │        │
│  │  │ (Qdrant)     │  │  (OpenAI)    │                         │        │
│  │  └──────────────┘  └──────────────┘                         │        │
│  │                                                             │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                    JSON Response: { components, meta, ... }
```

## Agent Responsibilities

| Agent             | File                | Purpose                                               |
| ----------------- | ------------------- | ----------------------------------------------------- |
| **ResponseAgent** | `response_agent.py` | Generates chat responses with optional UI components  |
| **ZoneAgent**     | `zone_agent.py`     | Renders zone content based on prompts + profile + RAG |
| **ProfileAgent**  | `profile_agent.py`  | Extracts user preferences from conversations          |
| **BehaveAgent**   | `behave_agent.py`   | Analyzes behavior patterns for UI adjustments         |
| **Orchestrator**  | `orchestrator.py`   | Coordinates multi-agent workflows                     |

## Frontend Module Summary

| Module          | Purpose                     | Key Exports                                                                                                               |
| --------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **components/** | React UI components         | `GenUIZone`, `BentoComponent`, `ButtonsComponent`, `ChartComponent`, `TextComponent`, `ComponentRenderer`, `GenUISection` |
| **hooks/**      | React hooks for state & API | `useGenUI`, `useZone`                                                                                                     |
| **types/**      | TypeScript definitions      | `GenUITheme`, `BentoCard`, `ButtonDef`, `ButtonVariant`, `UserProfile`, `GenUIResponse`, etc.                             |
| **utils/**      | Utilities                   | `BehaviorTracker`, profile/history persistence functions                                                                  |
| **styles/**     | CSS                         | Glassmorphism theme, animations, responsive layouts                                                                       |

---

## 🍕 Powered by datapizza-ai

GenUI's backend agent system is built on top of **[datapizza-ai](https://github.com/datapizza-labs/datapizza-ai)**<br />
A Python framework for building reliable Gen AI solutions without overhead.

### Why datapizza-ai?

- **Integration with AI Providers**: Seamlessly connect with OpenAI, Google VertexAI, Anthropic, Mistral, and more
- **Complex workflows, minimal code**: Design, automate, and scale powerful agent workflows without boilerplate
- **Retrieval-Augmented Generation (RAG)**: Built-in support for Qdrant, Milvus vector stores
- **Up to 40% less debugging time**: Trace and log every LLM/tool call with inputs/outputs
- **MCP Support**: Model Context Protocol integration for advanced tool usage

---

## 📄 License
This project is licensed under the Apache 2.0 License. 
See the [LICENSE](LICENSE) file for details.

---

<div align="center">

**GenUI System**
 _Intelligent interfaces that adapt to every user_

Built with ❤️ for the personalized web

</div>
