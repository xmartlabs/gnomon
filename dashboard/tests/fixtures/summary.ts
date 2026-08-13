export function makeSummary(overrides: Record<string, any> = {}) {
  const base = {
    context: {
      date_range: ["2026-01-01", "2026-06-30"],
      total_sessions: 171,
      total_prompts: 1167,
      sources: ["claude"],
      client_version: "0.3.0",
      window_months: 6,
    },
    planning_ratio_explore_to_doing: 0.82,
    errors: { error_recovery_ratio: 0.98, error_rate_per_100_tools: 2.6 },
    iteration_depth: { mean: 2.3, median: 2, p90: 5, max: 89, files_over_15x: 3 },
    churn: {
      git_churn_total: 8159072,
      tool_churn_edit_write: 104990,
      active_hours: 120,
      actions_per_prompt: 14,
    },
    orchestration: { fanout_median: 3.5, delegate_actions: 42 },
    compounding_writes: 91,
    ecosystem: { skills_distinct: 12, mcp_servers_distinct: 4 },
    progression_monthly: [
      {
        month: "2026-05",
        prompts: 500,
        sessions: 80,
        tool_calls: 7000,
        active_days: 12,
        models: [["claude-opus-4-8", 4000]],
        top_model: "claude-opus-4-8",
        tokens_input: 1e6,
        tokens_output: 2e6,
        tokens_cache_read: 5e8,
        tokens_cache_creation: 1e7,
        tokens_total: 513_000_000,
      },
      {
        month: "2026-06",
        prompts: 1077,
        sessions: 157,
        tool_calls: 15472,
        active_days: 14,
        models: [
          ["claude-opus-4-8", 24849],
          ["claude-fable-5", 1794],
        ],
        top_model: "claude-opus-4-8",
        tokens_input: 9_643_595,
        tokens_output: 21_017_872,
        tokens_cache_read: 5_575_354_211,
        tokens_cache_creation: 117_107_983,
        tokens_total: 5_723_123_661,
      },
    ],
    // Exact per-model monthly tokens (summary.py `monthly_noticed_stats`). Newer
    // summaries carry this; metrics prefer it over the invocation-share estimate.
    noticed_stats_monthly: [
      {
        month: "2026-05",
        range_start: "2026-05-01",
        range_end: "2026-05-31",
        token_usage: {
          total_input: 1e6,
          total_output: 2e6,
          total_cache_read: 5e8,
          total_cache_creation: 1e7,
          by_model: [
            {
              model_id: "claude-opus-4-8",
              model: "Opus 4.8",
              input: 1e6,
              output: 2e6,
              cache_read: 5e8,
              cache_creation: 1e7,
            },
          ],
        },
      },
      {
        month: "2026-06",
        range_start: "2026-06-01",
        range_end: "2026-06-30",
        token_usage: {
          total_input: 9_643_595,
          total_output: 21_017_872,
          total_cache_read: 5_575_354_211,
          total_cache_creation: 117_107_983,
          by_model: [
            {
              model_id: "claude-opus-4-8",
              model: "Opus 4.8",
              input: 9_000_000,
              output: 20_000_000,
              cache_read: 5.5e9,
              cache_creation: 1.1e8,
            },
            {
              model_id: "claude-fable-5",
              model: "Fable 5",
              input: 643_595,
              output: 1_017_872,
              cache_read: 75_354_211,
              cache_creation: 7_107_983,
            },
          ],
        },
      },
    ],
    profile: {
      aq: {
        aq_0_100: 93,
        tier: "Elite",
        pillars: [
          {
            name: "Breadth",
            weight: 30,
            score: 27.0,
            axes: [{ name: "Discipline", weight: 10, score: 1.2, signals: {} }],
          },
          { name: "Craft", weight: 35, score: 33.0, axes: [] },
          { name: "Efficiency", weight: 20, score: 18.0, axes: [] },
          { name: "Savvy", weight: 15, score: 15.0, axes: [] },
        ],
      },
      archetype: { title: "Blueprint, then bulldozer", quote: "Plan wide, then grind narrow" },
      scores: {
        execution: { value: 8.5, gloss: "How much you ship, how fast", subs: [] },
        planning: { value: 10.0, gloss: "Think before you build", subs: [] },
        engineering: { value: 8.6, gloss: "How clean your work is", subs: [] },
      },
      model_usage: [
        {
          model_id: "claude-opus-4-8",
          model: "Opus 4.8",
          count: 24849,
          pct: 0.8,
          tokens_input: 9_000_000,
          tokens_output: 20_000_000,
          tokens_cache_read: 5e9,
          tokens_cache_creation: 1e8,
        },
        {
          model_id: "claude-fable-5",
          model: "Fable 5",
          count: 1794,
          pct: 0.2,
          tokens_input: 600_000,
          tokens_output: 1_000_000,
          tokens_cache_read: 5e8,
          tokens_cache_creation: 1e7,
        },
      ],
    },
    token_usage: {
      total_input: 9_643_595,
      total_output: 21_017_872,
      total_cache_read: 5_575_354_211,
      total_cache_creation: 117_107_983,
      by_model: [
        {
          model_id: "claude-opus-4-8",
          model: "Opus 4.8",
          input: 9_000_000,
          output: 20_000_000,
          cache_read: 5e9,
          cache_creation: 1e8,
        },
      ],
    },
  };
  return deepMerge(base, overrides);
}

function deepMerge(base: any, over: any): any {
  if (Array.isArray(over) || typeof over !== "object" || over === null) return over;
  const out = { ...base };
  for (const k of Object.keys(over)) {
    out[k] = k in base ? deepMerge(base[k], over[k]) : over[k];
  }
  return out;
}
