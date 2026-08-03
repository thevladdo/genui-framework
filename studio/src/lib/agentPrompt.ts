/**
 * The prompt this page hands to an outside AI assistant, and where to send it.
 */

export interface AgentTarget {
  id: string;
  name: string;
  color: string;
  home: string;
  query?: string;
}

/**
 * Only the products whose prefill parameter is known are given one.
 * The others open on their own page: the prompt is on the clipboard either.
 */
export const AGENTS: readonly AgentTarget[] = [
  {
    id: "chatgpt",
    name: "ChatGPT",
    color: "#10a37f",
    home: "https://chatgpt.com/",
    query: "https://chatgpt.com/?q=",
  },
  {
    id: "claude",
    name: "Claude",
    color: "#d97757",
    home: "https://claude.ai/new",
    query: "https://claude.ai/new?q=",
  },
  {
    id: "perplexity",
    name: "Perplexity",
    color: "#20808d",
    home: "https://www.perplexity.ai/",
    query: "https://www.perplexity.ai/search?q=",
  },
  {
    id: "gemini",
    name: "Gemini",
    color: "#4285f4",
    home: "https://gemini.google.com/app",
  },
  { id: "grok", name: "Grok", color: "#cbd5e1", home: "https://grok.com/" },
  {
    id: "copilot",
    name: "Copilot",
    color: "#0078d4",
    home: "https://copilot.microsoft.com/",
  },
];

export const MAX_PREFILL_CHARS = 6000;

export const agentUrl = (agent: AgentTarget, prompt: string): string => {
  if (!agent.query) return agent.home;
  const encoded = encodeURIComponent(prompt);
  if (encoded.length > MAX_PREFILL_CHARS) return agent.home;
  return `${agent.query}${encoded}`;
};

export const prefills = (agent: AgentTarget, prompt: string): boolean =>
  agentUrl(agent, prompt) !== agent.home;

export const buildAgentPrompt = (types: readonly string[]): string => `\
I am filling in a zone configuration for GenUI Studio. A zone is one band of a
page whose content an LLM composes for each audience, out of material I supply.
I will paste your answer into four fields, so it has to be ready to paste.

FIRST, ASK ME THIS AND WAIT FOR MY ANSWER, in my language:
"Do you want this built around a real site (give me the URL and I will look it
up) or a plausible invented scenario, just to test?" Write nothing else until I
answer.

THEN output exactly four fenced code blocks, in this order, each with its field
name as the heading above it and nothing but the value inside it:

1. zone_id - a short lowercase slug with hyphens.
2. base_prompt - the standing instruction for this zone: what it is for, which
   component types to use and how to choose between them. It is reused for
   every visitor, so it must describe the job, never one specific person.
3. context_prompt - where the band sits on the page, plus what is known about
   the account right now: plan, seats, recent activity, the goal of the
   quarter. Do not describe the visitor's role, interests, engagement or
   browsing style here: those are the audiences I configure on the page
   itself, one column each, and the same config is rendered against all of
   them. Writing one of them into the context would flatten the comparison.
4. pinned_content - a JSON array and nothing else.

WHAT THE FRAMEWORK ENFORCES, so write a config that survives it:
- Every URL in the rendered output must already exist in what I supply. The
  renderer cannot invent a link or an image: a component asked for an image it
  does not have degrades to its text-only shape instead.
- Every number shown as content (a stat value, a price, a chart point, a
  comparison bar) must appear verbatim in what I supply. Do not ask the
  renderer for figures that are not in pinned_content or context_prompt.
- Component types available: ${types.join(", ")}.

PINNED CONTENT:
- Item shape: {"type": "image" | "link" | "article" | "custom", "title": "...",
  "url": "https://...", "description": "what it is for",
  "metadata": { ... optional ... }. "url" is required for image and link.
- Include at least 10 images as real Unsplash photo URLs, in the form
  https://images.unsplash.com/photo-<id>?q=80&w=1080&fit=max . Use photo ids
  you are confident exist, and verify them if you can browse: a URL that 404s
  renders as a broken image, which is worse than no image.
- Cover the shapes the components need: wide photos for cards, steps and case
  studies, square portraits at w=400 for testimonial avatars.
- Say in each description what the image is for, so the renderer places it well.
- Add a few non-image items too: a pricing or documentation link, an
  integration the user has not connected yet, and one "custom" item carrying
  plan status in its metadata.

WRITE INTO THE BASE PROMPT, explicitly: that images come only from pinned
content and are never invented, which component types take an image and which
are text-only by design, that each render should compose two or three
components and vary the choice from the previous one, and that prices, URLs
and figures are never invented.

Keep the three texts coherent: the situation in context_prompt should be the
reason base_prompt asks for those components.
`;
