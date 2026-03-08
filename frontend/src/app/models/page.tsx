'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { WSClient } from '@/lib/ws-client';
import type { ServerMessage, ModelInfo } from '@/types/ws-protocol';

// ---------------------------------------------------------------------------
// Extended model info with the cost/context fields from models.json
// ---------------------------------------------------------------------------

interface ExtendedModelInfo extends ModelInfo {
  contextWindow?: number;
  maxTokens?: number;
  cost?: { input: number; output: number };
  reasoning?: boolean;
  local?: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIERS = ['fast', 'balanced', 'smart', 'reasoning', 'coding'] as const;
type Tier = (typeof TIERS)[number];

const TIER_DESCRIPTIONS: Record<Tier, string> = {
  fast: 'Simple queries, greetings, short answers',
  balanced: 'General queries, moderate complexity',
  smart: 'Complex explanations, how-to, analysis',
  reasoning: 'Multi-step reasoning, comparison, evaluation',
  coding: 'Code generation, debugging, implementation',
};

const TIER_COLORS: Record<Tier, string> = {
  fast: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  balanced: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  smart: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  reasoning: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  coding: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatContextWindow(tokens?: number): string {
  if (!tokens) return '-';
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(0)}K`;
  return String(tokens);
}

function formatCost(perMillion?: number): string {
  if (perMillion === undefined || perMillion === null) return '-';
  if (perMillion === 0) return 'Free';
  return `$${perMillion.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ModelsPage() {
  const [models, setModels] = useState<ExtendedModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTier, setActiveTier] = useState<Tier | 'all'>('all');
  const [search, setSearch] = useState('');

  // ---- Fetch models from WS on mount ------------------------------------

  useEffect(() => {
    const client = new WSClient();

    client.onMessage((msg: ServerMessage) => {
      if (msg.type === 'system.models') {
        const raw = msg.data.models as ExtendedModelInfo[];
        setModels(raw);
        setLoading(false);
      }
    });

    client.connect();

    return () => {
      client.disconnect();
    };
  }, []);

  // ---- Filtering ---------------------------------------------------------

  const filtered = useMemo(() => {
    let result = models;

    if (activeTier !== 'all') {
      result = result.filter((m) => m.tier === activeTier);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (m) =>
          m.name.toLowerCase().includes(q) ||
          m.provider.toLowerCase().includes(q) ||
          m.id.toLowerCase().includes(q),
      );
    }

    return result;
  }, [models, activeTier, search]);

  // Group by tier for display
  const grouped = useMemo(() => {
    const groups: Record<string, ExtendedModelInfo[]> = {};
    for (const model of filtered) {
      const tier = model.tier || 'other';
      if (!groups[tier]) groups[tier] = [];
      groups[tier].push(model);
    }
    return groups;
  }, [filtered]);

  // Order of tier sections
  const tierOrder = activeTier === 'all' ? [...TIERS] : [activeTier];

  // ---- Render -------------------------------------------------------------

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-1">Model Browser</h1>
      <p className="text-[var(--text-secondary)] text-sm mb-6">
        Browse all AI models available through LADA&apos;s multi-provider system.
      </p>

      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        {/* Tier buttons */}
        <button
          onClick={() => setActiveTier('all')}
          className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
            activeTier === 'all'
              ? 'bg-indigo-600 text-white border-indigo-500'
              : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)] hover:border-gray-500'
          }`}
        >
          All ({models.length})
        </button>

        {TIERS.map((tier) => {
          const count = models.filter((m) => m.tier === tier).length;
          return (
            <button
              key={tier}
              onClick={() => setActiveTier(tier)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                activeTier === tier
                  ? TIER_COLORS[tier]
                  : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)] hover:border-gray-500'
              }`}
            >
              {tier.charAt(0).toUpperCase() + tier.slice(1)} ({count})
            </button>
          );
        })}

        {/* Search */}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search models..."
          className="ml-auto bg-[var(--bg-tertiary)] text-[var(--text-primary)] placeholder-[var(--text-secondary)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-56"
        />
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="text-[var(--text-secondary)] text-sm">
            Connecting to LADA backend...
          </div>
        </div>
      )}

      {/* No results */}
      {!loading && filtered.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <div className="text-[var(--text-secondary)] text-sm">
            No models found matching your filters.
          </div>
        </div>
      )}

      {/* Model sections grouped by tier */}
      {!loading &&
        tierOrder.map((tier) => {
          const tierModels = grouped[tier];
          if (!tierModels || tierModels.length === 0) return null;

          return (
            <section key={tier} className="mb-8">
              <div className="flex items-center gap-3 mb-3">
                <h2 className="text-lg font-semibold capitalize">{tier}</h2>
                <span className="text-xs text-[var(--text-secondary)]">
                  {TIER_DESCRIPTIONS[tier as Tier]}
                </span>
              </div>

              {/* Table */}
              <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-xs uppercase tracking-wider">
                      <th className="text-left px-4 py-3 font-medium">Status</th>
                      <th className="text-left px-4 py-3 font-medium">Model</th>
                      <th className="text-left px-4 py-3 font-medium">Provider</th>
                      <th className="text-right px-4 py-3 font-medium">Context</th>
                      <th className="text-right px-4 py-3 font-medium">Input $/M</th>
                      <th className="text-right px-4 py-3 font-medium">Output $/M</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {tierModels.map((model) => (
                      <tr
                        key={model.id}
                        className="hover:bg-[var(--bg-tertiary)] transition-colors"
                      >
                        {/* Available dot */}
                        <td className="px-4 py-3">
                          <span
                            className={`inline-block w-2.5 h-2.5 rounded-full ${
                              model.available !== false
                                ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.4)]'
                                : 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]'
                            }`}
                            title={
                              model.available !== false
                                ? 'Available'
                                : 'Unavailable'
                            }
                          />
                        </td>

                        {/* Name */}
                        <td className="px-4 py-3">
                          <div className="font-medium text-[var(--text-primary)]">
                            {model.name}
                          </div>
                          <div className="text-xs text-[var(--text-secondary)] font-mono mt-0.5">
                            {model.id}
                          </div>
                        </td>

                        {/* Provider */}
                        <td className="px-4 py-3 text-[var(--text-secondary)]">
                          {model.provider}
                          {model.local && (
                            <span className="ml-1.5 text-[10px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">
                              local
                            </span>
                          )}
                        </td>

                        {/* Context window */}
                        <td className="px-4 py-3 text-right text-[var(--text-secondary)] font-mono">
                          {formatContextWindow(model.contextWindow)}
                        </td>

                        {/* Cost input */}
                        <td className="px-4 py-3 text-right text-[var(--text-secondary)] font-mono">
                          {formatCost(model.cost?.input)}
                        </td>

                        {/* Cost output */}
                        <td className="px-4 py-3 text-right text-[var(--text-secondary)] font-mono">
                          {formatCost(model.cost?.output)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
    </div>
  );
}
