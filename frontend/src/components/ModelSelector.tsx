'use client';

import React, { useMemo } from 'react';

interface Model {
  id: string;
  name: string;
  provider?: string;
  available?: boolean;
  tier?: string;
}

interface ModelSelectorProps {
  models: Model[];
  selectedModel: string;
  onSelect: (modelId: string) => void;
}

const TIER_ORDER = ['fast', 'balanced', 'smart', 'reasoning', 'coding'];

const TIER_LABELS: Record<string, string> = {
  fast: 'Fast',
  balanced: 'Balanced',
  smart: 'Smart',
  reasoning: 'Reasoning',
  coding: 'Coding',
};

export default function ModelSelector({
  models,
  selectedModel,
  onSelect,
}: ModelSelectorProps) {
  const hasTiers = useMemo(
    () => models.some((m) => m.tier),
    [models]
  );

  const groupedByTier = useMemo(() => {
    if (!hasTiers) return null;

    const groups: Record<string, Model[]> = {};
    const ungrouped: Model[] = [];

    for (const model of models) {
      if (model.tier) {
        if (!groups[model.tier]) {
          groups[model.tier] = [];
        }
        groups[model.tier].push(model);
      } else {
        ungrouped.push(model);
      }
    }

    return { groups, ungrouped };
  }, [models, hasTiers]);

  const renderModelOption = (model: Model) => {
    const label = model.provider
      ? `${model.name} (${model.provider})`
      : model.name;

    return (
      <option
        key={model.id}
        value={model.id}
        disabled={model.available === false}
      >
        {label}
        {model.available === false ? ' (unavailable)' : ''}
      </option>
    );
  };

  return (
    <div className="relative">
      <select
        value={selectedModel}
        onChange={(e) => onSelect(e.target.value)}
        className="appearance-none w-full bg-gray-800 text-gray-200 text-sm border border-gray-700 rounded-lg px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 hover:border-gray-600 transition-colors cursor-pointer"
      >
        {/* Auto option always first */}
        <option value="auto">Auto (Best Available)</option>

        {hasTiers && groupedByTier ? (
          <>
            {/* Render tier groups in defined order */}
            {TIER_ORDER.map((tier) => {
              const tierModels = groupedByTier.groups[tier];
              if (!tierModels || tierModels.length === 0) return null;

              return (
                <optgroup
                  key={tier}
                  label={TIER_LABELS[tier] || tier}
                >
                  {tierModels.map(renderModelOption)}
                </optgroup>
              );
            })}

            {/* Render any tiers not in the predefined order */}
            {Object.keys(groupedByTier.groups)
              .filter((tier) => !TIER_ORDER.includes(tier))
              .map((tier) => (
                <optgroup
                  key={tier}
                  label={TIER_LABELS[tier] || tier.charAt(0).toUpperCase() + tier.slice(1)}
                >
                  {groupedByTier.groups[tier].map(renderModelOption)}
                </optgroup>
              ))}

            {/* Ungrouped models */}
            {groupedByTier.ungrouped.length > 0 && (
              <optgroup label="Other">
                {groupedByTier.ungrouped.map(renderModelOption)}
              </optgroup>
            )}
          </>
        ) : (
          /* Flat list when no tier info */
          models.map(renderModelOption)
        )}
      </select>

      {/* Custom dropdown arrow */}
      <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
        <svg
          className="h-4 w-4 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </div>
    </div>
  );
}
