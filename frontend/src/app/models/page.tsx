'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { WSClient } from '@/lib/ws-client';
import { cn } from '@/lib/utils';
import { 
  Cpu, 
  Zap, 
  Brain, 
  Sparkles, 
  Code2, 
  Search,
  CheckCircle2,
  XCircle,
  Server,
  Cloud
} from 'lucide-react';
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

const TIER_INFO: Record<Tier, { 
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  color: string;
  bgColor: string;
}> = {
  fast: {
    icon: Zap,
    description: 'Quick responses, simple tasks',
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10 border-emerald-500/20',
  },
  balanced: {
    icon: Cpu,
    description: 'General purpose, good quality',
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10 border-blue-500/20',
  },
  smart: {
    icon: Brain,
    description: 'Complex analysis, detailed responses',
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/10 border-purple-500/20',
  },
  reasoning: {
    icon: Sparkles,
    description: 'Multi-step reasoning, evaluation',
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10 border-amber-500/20',
  },
  coding: {
    icon: Code2,
    description: 'Code generation and debugging',
    color: 'text-cyan-400',
    bgColor: 'bg-cyan-500/10 border-cyan-500/20',
  },
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
// Model Card Component
// ---------------------------------------------------------------------------

function ModelCard({ model }: { model: ExtendedModelInfo }) {
  const tier = (model.tier || 'balanced') as Tier;
  const tierInfo = TIER_INFO[tier];
  const TierIcon = tierInfo.icon;
  
  return (
    <div className={cn(
      "group relative p-4 rounded-xl border transition-all duration-200",
      "bg-zinc-900/50 border-zinc-800/50",
      "hover:bg-zinc-800/50 hover:border-zinc-700/50",
      "hover:shadow-lg hover:shadow-black/20"
    )}>
      {/* Status indicator */}
      <div className="absolute top-3 right-3">
        {model.available !== false ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
        ) : (
          <XCircle className="w-4 h-4 text-red-400" />
        )}
      </div>

      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <div className={cn(
          "p-2 rounded-lg",
          tierInfo.bgColor
        )}>
          <TierIcon className={cn("w-4 h-4", tierInfo.color)} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-zinc-100 truncate pr-6">
            {model.name}
          </h3>
          <p className="text-xs text-zinc-500 font-mono truncate">
            {model.id}
          </p>
        </div>
      </div>

      {/* Provider */}
      <div className="flex items-center gap-2 mb-3">
        {model.local ? (
          <Server className="w-3.5 h-3.5 text-zinc-500" />
        ) : (
          <Cloud className="w-3.5 h-3.5 text-zinc-500" />
        )}
        <span className="text-sm text-zinc-400">{model.provider}</span>
        {model.local && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-medium">
            LOCAL
          </span>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="p-2 rounded-lg bg-zinc-800/50">
          <div className="text-xs text-zinc-500 mb-0.5">Context</div>
          <div className="text-sm font-mono text-zinc-300">
            {formatContextWindow(model.contextWindow)}
          </div>
        </div>
        <div className="p-2 rounded-lg bg-zinc-800/50">
          <div className="text-xs text-zinc-500 mb-0.5">Input</div>
          <div className="text-sm font-mono text-zinc-300">
            {formatCost(model.cost?.input)}
          </div>
        </div>
        <div className="p-2 rounded-lg bg-zinc-800/50">
          <div className="text-xs text-zinc-500 mb-0.5">Output</div>
          <div className="text-sm font-mono text-zinc-300">
            {formatCost(model.cost?.output)}
          </div>
        </div>
      </div>

      {/* Tier badge */}
      <div className={cn(
        "absolute bottom-0 left-0 right-0 h-1 rounded-b-xl",
        tier === 'fast' && "bg-emerald-500/50",
        tier === 'balanced' && "bg-blue-500/50",
        tier === 'smart' && "bg-purple-500/50",
        tier === 'reasoning' && "bg-amber-500/50",
        tier === 'coding' && "bg-cyan-500/50"
      )} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
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

  // Stats
  const stats = useMemo(() => ({
    total: models.length,
    available: models.filter(m => m.available !== false).length,
    local: models.filter(m => m.local).length,
    cloud: models.filter(m => !m.local).length,
  }), [models]);

  // ---- Render -------------------------------------------------------------

  return (
    <div className="min-h-screen bg-zinc-950 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-zinc-100 mb-2">Models</h1>
          <p className="text-zinc-400">
            Browse and explore all AI models available through LADA.
          </p>
        </div>

        {/* Stats cards */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Total Models', value: stats.total, color: 'text-zinc-100' },
            { label: 'Available', value: stats.available, color: 'text-emerald-400' },
            { label: 'Local', value: stats.local, color: 'text-blue-400' },
            { label: 'Cloud', value: stats.cloud, color: 'text-purple-400' },
          ].map((stat, i) => (
            <div 
              key={i}
              className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/50"
            >
              <div className="text-2xl font-bold mb-1" style={{ color: stat.color.replace('text-', '') }}>
                <span className={stat.color}>{stat.value}</span>
              </div>
              <div className="text-sm text-zinc-500">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          {/* All button */}
          <button
            onClick={() => setActiveTier('all')}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
              activeTier === 'all'
                ? "bg-indigo-600 text-white"
                : "bg-zinc-800/50 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
            )}
          >
            All
            <span className={cn(
              "text-xs px-1.5 py-0.5 rounded",
              activeTier === 'all' ? "bg-white/20" : "bg-zinc-700"
            )}>
              {models.length}
            </span>
          </button>

          {/* Tier buttons */}
          {TIERS.map((tier) => {
            const info = TIER_INFO[tier];
            const TierIcon = info.icon;
            const count = models.filter((m) => m.tier === tier).length;
            
            return (
              <button
                key={tier}
                onClick={() => setActiveTier(tier)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                  activeTier === tier
                    ? cn(info.bgColor, info.color, "border")
                    : "bg-zinc-800/50 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                )}
              >
                <TierIcon className="w-4 h-4" />
                <span className="capitalize">{tier}</span>
                <span className={cn(
                  "text-xs px-1.5 py-0.5 rounded",
                  activeTier === tier ? "bg-white/10" : "bg-zinc-700"
                )}>
                  {count}
                </span>
              </button>
            );
          })}

          {/* Search */}
          <div className="ml-auto relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search models..."
              className={cn(
                "pl-10 pr-4 py-2 w-64 rounded-lg text-sm",
                "bg-zinc-800/50 border border-zinc-700/50",
                "text-zinc-200 placeholder:text-zinc-500",
                "focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50"
              )}
            />
          </div>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="flex items-center gap-3 text-zinc-400">
              <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              Connecting to LADA...
            </div>
          </div>
        )}

        {/* No results */}
        {!loading && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20">
            <Search className="w-12 h-12 text-zinc-700 mb-4" />
            <p className="text-zinc-400">No models found matching your filters.</p>
          </div>
        )}

        {/* Model grid */}
        {!loading && filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map((model) => (
              <ModelCard key={model.id} model={model} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
