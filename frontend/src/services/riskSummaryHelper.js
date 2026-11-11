/**
 * RouteWise Risk Summary Normalization Helper.
 *
 * Reconciles the dual API summary response shapes:
 * 1. Historical API shape (from /corridor/risk/{date}):
 *    {
 *      high_risk_count: number,
 *      medium_risk_count: number,
 *      low_risk_count: number,
 *      unknown_count: number,
 *      total_segments: number,
 *      ...
 *    }
 *
 * 2. Live API shape (from /live/risk):
 *    {
 *      Low: number,
 *      Medium: number,
 *      High: number,
 *      UNKNOWN: number
 *    }
 *
 * Returns a canonical normalized object providing both naming conventions:
 * {
 *   high_risk_count: number,
 *   medium_risk_count: number,
 *   low_risk_count: number,
 *   unknown_count: number,
 *   total: number,
 *   High: number,
 *   Medium: number,
 *   Low: number,
 *   UNKNOWN: number,
 * }
 */

export function normalizeRiskSummary(summary) {
  if (!summary || typeof summary !== 'object') {
    return {
      high_risk_count: 0,
      medium_risk_count: 0,
      low_risk_count: 0,
      unknown_count: 0,
      total: 0,
      High: 0,
      Medium: 0,
      Low: 0,
      UNKNOWN: 0,
    };
  }

  // Extract High count from either shape
  const high = Number(
    summary.high_risk_count ??
    summary.High ??
    summary.high ??
    0
  );

  // Extract Medium count from either shape
  const medium = Number(
    summary.medium_risk_count ??
    summary.Medium ??
    summary.medium ??
    summary.med_risk_count ??
    0
  );

  // Extract Low count from either shape
  const low = Number(
    summary.low_risk_count ??
    summary.Low ??
    summary.low ??
    0
  );

  // Extract Unknown count from either shape
  const unknown = Number(
    summary.unknown_count ??
    summary.UNKNOWN ??
    summary.Unknown ??
    summary.unknown ??
    0
  );

  const total = high + medium + low + unknown;

  return {
    ...summary,
    high_risk_count: high,
    medium_risk_count: medium,
    low_risk_count: low,
    unknown_count: unknown,
    total,
    High: high,
    Medium: medium,
    Low: low,
    UNKNOWN: unknown,
  };
}

