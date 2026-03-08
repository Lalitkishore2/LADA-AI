'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Source {
  url: string;
  title: string;
  domain: string;
}

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  sources?: Source[];
  streaming?: boolean;
}

export default function ChatMessage({
  role,
  content,
  model,
  sources,
  streaming = false,
}: ChatMessageProps) {
  const isUser = role === 'user';

  return (
    <div
      className={`flex w-full mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[80%] md:max-w-[70%] ${
          isUser ? 'order-1' : 'order-1'
        }`}
      >
        {/* Message bubble */}
        <div
          className={`px-4 py-3 rounded-2xl ${
            isUser
              ? 'bg-gradient-to-br from-indigo-600 to-purple-600 text-white rounded-br-md'
              : 'bg-gray-800 text-gray-100 rounded-bl-md border border-gray-700'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {content}
            </p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match && !className;

                    if (isInline) {
                      return (
                        <code
                          className="bg-gray-900 text-emerald-400 px-1.5 py-0.5 rounded text-xs font-mono"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }

                    return (
                      <div className="relative my-3">
                        {match && (
                          <div className="absolute top-0 right-0 px-2 py-1 text-[10px] text-gray-400 uppercase tracking-wider bg-gray-950 rounded-bl rounded-tr">
                            {match[1]}
                          </div>
                        )}
                        <pre className="bg-gray-950 border border-gray-700 rounded-lg p-4 overflow-x-auto">
                          <code
                            className={`text-xs font-mono leading-relaxed text-gray-200 ${className || ''}`}
                            {...props}
                          >
                            {children}
                          </code>
                        </pre>
                      </div>
                    );
                  },
                  p({ children }) {
                    return (
                      <p className="mb-2 last:mb-0 leading-relaxed text-sm">
                        {children}
                      </p>
                    );
                  },
                  ul({ children }) {
                    return (
                      <ul className="list-disc list-inside mb-2 space-y-1 text-sm">
                        {children}
                      </ul>
                    );
                  },
                  ol({ children }) {
                    return (
                      <ol className="list-decimal list-inside mb-2 space-y-1 text-sm">
                        {children}
                      </ol>
                    );
                  },
                  a({ href, children }) {
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2"
                      >
                        {children}
                      </a>
                    );
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-2 border-indigo-500 pl-3 my-2 text-gray-300 italic">
                        {children}
                      </blockquote>
                    );
                  },
                  table({ children }) {
                    return (
                      <div className="overflow-x-auto my-2">
                        <table className="min-w-full text-sm border border-gray-700">
                          {children}
                        </table>
                      </div>
                    );
                  },
                  th({ children }) {
                    return (
                      <th className="border border-gray-700 px-3 py-1.5 bg-gray-900 text-left font-semibold">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="border border-gray-700 px-3 py-1.5">
                        {children}
                      </td>
                    );
                  },
                }}
              />
              {streaming && (
                <span className="inline-block w-2 h-4 ml-1 bg-gray-300 animate-pulse rounded-sm" />
              )}
            </div>
          )}
        </div>

        {/* Sources */}
        {!isUser && sources && sources.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2 px-1">
            {sources.map((source, idx) => (
              <a
                key={idx}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-full text-xs text-gray-300 hover:text-white transition-colors"
                title={source.title}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 flex-shrink-0" />
                <span className="truncate max-w-[150px]">{source.title}</span>
                <span className="text-gray-500">{source.domain}</span>
              </a>
            ))}
          </div>
        )}

        {/* Model label */}
        {!isUser && model && (
          <div className="mt-1 px-1">
            <span className="text-[11px] text-gray-500">{model}</span>
          </div>
        )}
      </div>
    </div>
  );
}
