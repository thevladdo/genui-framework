/**
 * Measurement dashboard: response types and the pure logic that turns /events/stats numbers into a verdict.
 */

// /api/v1/events/stats response
export type ArmName = "personalized" | "control" | "none";

export interface ArmStats {
  impression?: number;
  click?: number;
  ctr: number | null;
}

export interface Significance {
  method: string;
  z_score: number;
  p_value: number;
  significant_95: boolean;
  sample_warning: boolean;
}

export interface EventStats {
  zone_id: string;
  arms: Partial<Record<ArmName, ArmStats>>;
  uplift_percent: number | null;
  significance: Significance | null;
  holdout_percent?: number;
}

// /api/v1/zone/cache/stats response
export interface CacheStats {
  backend: "redis" | "memory";
  redis: string;
  fresh_ttl: number;
  stale_ttl: number;
  memory_entries: number;
  enabled: boolean;
}

// /api/v1/zone/warmup response
export interface WarmupEntryResult {
  zone_id: string;
  segment?: string;
  success: boolean;
  error?: string;
}

export interface WarmupResult {
  results: WarmupEntryResult[];
  warmed: number;
  failed: number;
  warmed_at: string;
}

// Formatters
const PLACEHOLDER = "–";

export const formatCount = (n?: number): string =>
  n == null ? PLACEHOLDER : n.toLocaleString("en-US");

/** CTR arrives as a fraction (0.0523): render as a percentage, one decimal. */
export const formatCtr = (ctr: number | null | undefined): string =>
  ctr == null ? PLACEHOLDER : `${(ctr * 100).toFixed(1)}%`;

/** Uplift arrives already in percent; keep the sign explicit. */
export const formatUplift = (uplift: number | null | undefined): string =>
  uplift == null
    ? PLACEHOLDER
    : `${uplift > 0 ? "+" : ""}${uplift.toFixed(1)}%`;

/** Never print fake precision: below 0.001 the exact digits are noise. */
export const formatPValue = (p: number): string =>
  p < 0.001 ? "p < 0.001" : `p = ${p.toFixed(3)}`;

// Verdict
export type VerdictTone = "muted" | "warning" | "success" | "neutral";

export interface Verdict {
  tone: VerdictTone;
  label: string;
  detail: string;
}

const totalImpressions = (stats: EventStats): number =>
  Object.values(stats.arms).reduce(
    (sum, arm) => sum + (arm?.impression ?? 0),
    0,
  );

/**
 * The single honest reading of an /events/stats payload.
 *
 * Order matters: the sample warning is checked BEFORE significant_95,
 * so an early lucky streak can never be presented as proof.
 */
export const verdict = (stats: EventStats): Verdict => {
  if (Object.keys(stats.arms).length === 0 || totalImpressions(stats) === 0) {
    return {
      tone: "muted",
      label: "No data yet",
      detail:
        "No impressions recorded for this zone. GenUI zones emit impressions and clicks automatically; check that events are flowing to POST /events.",
    };
  }

  if (!stats.arms.personalized || !stats.arms.control) {
    const holdout =
      stats.holdout_percent != null
        ? ` The control arm comes from the holdout (currently ${stats.holdout_percent}% of traffic).`
        : "";
    return {
      tone: "neutral",
      label: "Uplift not measurable yet",
      detail: `Measuring uplift needs both a personalized and a control arm with traffic.${holdout}`,
    };
  }

  if (!stats.significance) {
    return {
      tone: "muted",
      label: "Not testable yet",
      detail:
        "The z-test cannot run yet: an arm has zero impressions, or there are no clicks at all to compare.",
    };
  }

  const { p_value, significant_95, sample_warning } = stats.significance;

  if (sample_warning) {
    return {
      tone: "warning",
      label: "Preliminary: sample too small",
      detail: `An arm is below 100 impressions (${formatPValue(
        p_value,
      )}). Treat any difference as noise until the sample grows${
        significant_95
          ? ": the test alone would pass, but the sample cannot back it"
          : ""
      }.`,
    };
  }

  if (significant_95) {
    return {
      tone: "success",
      label: "Statistically significant",
      detail: `${formatPValue(
        p_value,
      )}, below the 0.05 threshold: the CTR difference between arms is unlikely to be chance.`,
    };
  }

  return {
    tone: "neutral",
    label: "No significant difference yet",
    detail: `${formatPValue(
      p_value,
    )}: the CTR difference between arms is compatible with chance so far.`,
  };
};
