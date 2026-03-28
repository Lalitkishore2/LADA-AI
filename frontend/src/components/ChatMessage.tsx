'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Sparkles, ExternalLink, Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

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
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={cn(
      "group flex gap-4 py-4 animate-slide-up",
      isUser ? "flex-row-reverse" : ""
    )}>
      {/* Avatar */}
      <div className={cn(
        "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
        isUser 
          ? "bg-gradient-to-br from-indigo-500 to-purple-600" 
          : "bg-gradient-to-br from-emerald-500 to-teal-600"
      )}>
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Sparkles className="w-4 h-4 text-white" />
        )}
      </div>

      {/* Content */}
      <div className={cn("flex-1 min-w-0", isUser ? "text-right" : "")}>
        {/* Role label */}
        <div className={cn(
          "text-xs font-medium mb-1",
          isUser ? "text-indigo-400" : "text-emerald-400"
        )}>
          {isUser ? 'You' : 'LADA'}
          {!isUser && model && (
            <span className="text-zinc-500 font-normal ml-2">
              via {model}
            </span>
          )}
        </div>

        {/* Message content */}
        <div className={cn(
          "rounded-2xl px-4 py-3 inline-block text-left",
          isUser 
            ? "bg-gradient-to-br from-indigo-600/80 to-purple-600/80 text-white max-w-[85%]" 
            : "bg-zinc-900 border border-zinc-800 text-zinc-100 w-full"
        )}>
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
                          className="bg-zinc-800 text-emerald-400 px-1.5 py-0.5 rounded text-xs font-mono"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }

                    return (
                      <div className="relative my-3 group/code">
                        {match && (
                          <div className="absolute top-0 left-0 px-3 py-1 text-[10px] text-zinc-500 uppercase tracking-wider bg-zinc-950 rounded-tl-lg rounded-br font-medium">
                            {match[1]}
                          </div>
                        )}
                        <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 pt-8 overflow-x-auto">
                          <code
                            className={`text-xs font-mono leading-relaxed text-zinc-200 ${className || ''}`}
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
                      <p className="mb-3 last:mb-0 leading-relaxed text-sm text-zinc-200">
                        {children}
                      </p>
                    );
                  },
                  ul({ children }) {
                    return (
                      <ul className="list-disc list-inside mb-3 space-y-1.5 text-sm text-zinc-200">
                        {children}
                      </ul>
                    );
                  },
                  ol({ children }) {
                    return (
                      <ol className="list-decimal list-inside mb-3 space-y-1.5 text-sm text-zinc-200">
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
                        className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 inline-flex items-center gap-1"
                      >
                        {children}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    );
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-2 border-indigo-500/50 pl-4 my-3 text-zinc-400 italic">
                        {children}
                      </blockquote>
                    );
                  },
                  table({ children }) {
                    return (
                      <div className="overflow-x-auto my-3 rounded-lg border border-zinc-800">
                        <table className="min-w-full text-sm">
                          {children}
                        </table>
                      </div>
                    );
                  },
                  th({ children }) {
                    return (
                      <th className="border-b border-zinc-800 px-4 py-2 bg-zinc-900 text-left font-semibold text-zinc-300">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="border-b border-zinc-800/50 px-4 py-2 text-zinc-300">
                        {children}
                      </td>
                    );
                  },
                  h1({ children }) {
                    return <h1 className="text-xl font-bold text-zinc-100 mb-3 mt-4">{children}</h1>;
                  },
                  h2({ children }) {
                    return <h2 className="text-lg font-semibold text-zinc-100 mb-2 mt-3">{children}</h2>;
                  },
                  h3({ children }) {
                    return <h3 className="text-base font-semibold text-zinc-200 mb-2 mt-3">{children}</h3>;
                  },
                }}
              />
              {streaming && (
                <span className="inline-block w-2 h-4 ml-1 bg-emerald-400 animate-pulse-soft rounded-sm" />
              )}
            </div>
          )}
        </div>

        {/* Actions (copy button) */}
        {!isUser && !streaming && content && (
          <div className="flex items-center gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span className="text-emerald-400">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>
        )}

        {/* Sources */}
        {!isUser && sources && sources.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {sources.map((source, idx) => (
              <a
                key={idx}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                  "inline-flex items-center gap-1.5 px-3 py-1.5",
                  "bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 hover:border-zinc-700",
                  "rounded-full text-xs text-zinc-400 hover:text-zinc-200 transition-all"
                )}
                title={source.title}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 flex-shrink-0" />
                <span className="truncate max-w-[150px]">{source.title}</span>
                <span className="text-zinc-600">• {source.domain}</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
