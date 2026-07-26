/**
 * The console tools in one place.
 */

import type { RoutePath } from "../hooks/useHashRoute";

export interface ConsoleTool {
  path: RoutePath;
  label: string;
  blurb: string;
}

export const CONSOLE_TOOLS: ConsoleTool[] = [
  {
    path: "/preview",
    label: "Segment Preview",
    blurb: "Watch the LLM curate per audience",
  },
  {
    path: "/zones",
    label: "Zones",
    blurb: "Draft, preview and approve a zone",
  },
  {
    path: "/audit",
    label: "Audit",
    blurb: "What was shown to whom",
  },
  {
    path: "/policy",
    label: "Content Policy",
    blurb: "Banned terms, per tenant",
  },
  {
    path: "/studio",
    label: "Content Studio",
    blurb: "Feed and test the knowledge base",
  },
  {
    path: "/measure",
    label: "Measurement",
    blurb: "Uplift, CTR and significance",
  },
];
