'use client';

import React from 'react';

interface Provider {
  name: string;
  status: string;
  available: boolean;
}

interface ProviderStatusProps {
  connected: boolean;
  sessionId?: string;
  providers?: Provider[];
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
        active
          ? 'bg-[var(--accent-hover)] shadow-[0_0_6px_rgba(25,187,147,0.5)]'
          : 'bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.4)]'
      }`}
    />
  );
}

export default function ProviderStatus({
  connected,
  sessionId,
  providers,
}: ProviderStatusProps) {
  const truncatedSession = sessionId
    ? sessionId.length > 8
      ? sessionId.slice(0, 8)
      : sessionId
    : null;

  return (
    <div className="flex items-center gap-3 text-xs">
      {/* Connection status */}
      <div className="flex items-center gap-1.5 rounded-full border border-[var(--border-color)] bg-[var(--surface-2)]/70 px-2.5 py-1">
        <StatusDot active={connected} />
        <span className="text-[var(--text-dim)] whitespace-nowrap">
          {connected ? (
            <>
              Connected
              {truncatedSession && (
                <span className="text-[var(--text-faint)] ml-1" title={sessionId}>
                  ({truncatedSession})
                </span>
              )}
            </>
          ) : (
            <span className="text-red-300">Disconnected</span>
          )}
        </span>
      </div>

      {/* Provider list */}
      {providers && providers.length > 0 && (
        <>
          <div className="w-px h-4 bg-[var(--border-color)]" />
          <div className="flex items-center gap-2 overflow-x-auto">
            {providers.map((provider) => (
              <div
                key={provider.name}
                className="flex items-center gap-1 whitespace-nowrap rounded-full border border-[var(--border-color)] bg-[var(--surface)]/75 px-2.5 py-1"
                title={`${provider.name}: ${provider.status}`}
              >
                <StatusDot active={provider.available} />
                <span
                  className={`text-xs ${
                    provider.available ? 'text-[var(--text-dim)]' : 'text-[var(--text-faint)]'
                  }`}
                >
                  {provider.name}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
