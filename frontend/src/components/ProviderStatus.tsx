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
          ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]'
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
    <div className="flex items-center gap-3">
      {/* Connection status */}
      <div className="flex items-center gap-1.5">
        <StatusDot active={connected} />
        <span className="text-xs text-gray-300 whitespace-nowrap">
          {connected ? (
            <>
              Connected
              {truncatedSession && (
                <span className="text-gray-500 ml-1" title={sessionId}>
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
          <div className="w-px h-4 bg-gray-700" />
          <div className="flex items-center gap-2 overflow-x-auto">
            {providers.map((provider) => (
              <div
                key={provider.name}
                className="flex items-center gap-1 whitespace-nowrap"
                title={`${provider.name}: ${provider.status}`}
              >
                <StatusDot active={provider.available} />
                <span
                  className={`text-xs ${
                    provider.available ? 'text-gray-300' : 'text-gray-500'
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
