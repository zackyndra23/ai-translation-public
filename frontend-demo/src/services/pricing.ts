import type { ModelId } from './types'

// Prices per 1K tokens (USD). Roughly aligned with public list prices
// at time of writing; demo-only — don't quote these as authoritative.
export const MODEL_PRICING: Record<
  ModelId,
  { input_per_1k: number; output_per_1k: number }
> = {
  'claude-haiku-4-5': { input_per_1k: 0.0008, output_per_1k: 0.004 },
  'claude-sonnet-4-6': { input_per_1k: 0.003, output_per_1k: 0.015 },
  'claude-opus-4-7': { input_per_1k: 0.015, output_per_1k: 0.075 },
  'gpt-4o-mini': { input_per_1k: 0.00015, output_per_1k: 0.0006 },
}

export function computeCostUsd(
  model: ModelId,
  inputTokens: number,
  outputTokens: number,
): number {
  const p = MODEL_PRICING[model]
  return (inputTokens * p.input_per_1k + outputTokens * p.output_per_1k) / 1000
}
