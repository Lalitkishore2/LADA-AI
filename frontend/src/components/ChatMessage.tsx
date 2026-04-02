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
  onUseAsPrompt?: (content: string, role: 'user' | 'assistant') => void;
  onResend?: (content: string) => void;
  onRegenerate?: () => void;
}

export default function ChatMessage({
  role,
  content,
  model,
  sources,
  streaming = false,
  onUseAsPrompt,
  onResend,
  onRegenerate,
}: ChatMessageProps) {
  const isUser = role === 'user';
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={cn(
      "group flex gap-3 py-2 animate-slide-up",
      isUser ? "flex-row-reverse" : ""
    )}>
      {/* Avatar */}
      <div className={cn(
        "flex-shrink-0 w-[26px] h-[26px] rounded-md flex items-center justify-center",
        isUser 
          ? "bg-[#233447] border border-white/10" 
          : "bg-[linear-gradient(145deg,var(--accent),var(--accent-dark))] shadow-[0_6px_16px_rgba(16,163,127,.25)]"
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
          isUser ? "text-[#b8d6ff]" : "text-[var(--text-dim)]"
        )}>
          {isUser ? 'You' : 'LADA'}
          {!isUser && model && (
            <span className="text-[var(--text-faint)] font-normal ml-2">
              via {model}
            </span>
          )}
        </div>

        {/* Message content */}
        <div className={cn(
          "rounded-2xl px-4 py-3 inline-block text-left leading-relaxed",
          isUser 
            ? "bg-[#233447] border border-white/10 text-[#dce9ff] max-w-[78%] rounded-br-md" 
            : "bg-[rgba(17,25,35,.66)] border border-white/10 text-[var(--text)] w-full backdrop-blur rounded-bl-md"
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
                          className="bg-[var(--surface-3)] text-sky-300 px-1.5 py-0.5 rounded text-xs font-mono"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }

                    return (
                      <div className="relative my-3 group/code">
                        {match && (
                          <div className="absolute top-0 left-0 px-3 py-1 text-[10px] text-[var(--text-faint)] uppercase tracking-wider bg-[var(--surface)] rounded-tl-lg rounded-br font-medium">
                            {match[1]}
                          </div>
                        )}
                        <pre className="bg-[#0f1722] border border-[var(--border-color)] rounded-lg p-4 pt-8 overflow-x-auto">
                          <code
                            className={`text-xs font-mono leading-relaxed text-[var(--text)] ${className || ''}`}
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
                      <p className="mb-3 last:mb-0 leading-relaxed text-sm text-[var(--text)]">
                        {children}
                      </p>
                    );
                  },
                  ul({ children }) {
                    return (
                      <ul className="list-disc list-inside mb-3 space-y-1.5 text-sm text-[var(--text)]">
                        {children}
                      </ul>
                    );
                  },
                  ol({ children }) {
                    return (
                      <ol className="list-decimal list-inside mb-3 space-y-1.5 text-sm text-[var(--text)]">
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
                        className="text-[var(--accent-hover)] hover:text-[#7de5cb] underline underline-offset-2 inline-flex items-center gap-1"
                      >
                        {children}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    );
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-2 border-[var(--accent)] pl-4 my-3 text-[var(--text-dim)] italic">
                        {children}
                      </blockquote>
                    );
                  },
                  table({ children }) {
                    return (
                      <div className="overflow-x-auto my-3 rounded-lg border border-[var(--border-color)]">
                        <table className="min-w-full text-sm">
                          {children}
                        </table>
                      </div>
                    );
                  },
                  th({ children }) {
                    return (
                      <th className="border-b border-[var(--border-color)] px-4 py-2 bg-[var(--surface-2)] text-left font-semibold text-[var(--text-dim)]">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="border-b border-[var(--border-color)]/60 px-4 py-2 text-[var(--text-dim)]">
                        {children}
                      </td>
                    );
                  },
                  h1({ children }) {
                    return <h1 className="text-xl font-bold text-[var(--text)] mb-3 mt-4">{children}</h1>;
                  },
                  h2({ children }) {
                    return <h2 className="text-lg font-semibold text-[var(--text)] mb-2 mt-3">{children}</h2>;
                  },
                  h3({ children }) {
                    return <h3 className="text-base font-semibold text-[var(--text)] mb-2 mt-3">{children}</h3>;
                  },
                }}
              />
              {streaming && (
                <span className="inline-block w-2 h-4 ml-1 bg-[var(--accent-hover)] animate-pulse-soft rounded-sm" />
              )}
            </div>
          )}
        </div>

        {/* Message actions */}
        {!streaming && !!content && (
          <div className={cn(
            "flex items-center gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity",
            isUser ? "justify-end" : ""
          )}>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 text-xs text-[var(--text-faint)] hover:text-[var(--text-dim)] transition-colors"
              title="Copy message"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3 text-[var(--accent-hover)]" />
                  <span className="text-[var(--accent-hover)]">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy</span>
                </>
              )}
            </button>

            {onUseAsPrompt && (
              <button
                onClick={() => onUseAsPrompt(content, role)}
                className="text-xs text-[var(--text-faint)] hover:text-[var(--text-dim)] transition-colors"
                title="Use this message in prompt"
              >
                Use in prompt
              </button>
            )}

            {isUser && onResend && (
              <button
                onClick={() => onResend(content)}
                className="text-xs text-[var(--text-faint)] hover:text-[var(--text-dim)] transition-colors"
                title="Resend this message"
              >
                Resend
              </button>
            )}

            {!isUser && onRegenerate && (
              <button
                onClick={onRegenerate}
                className="text-xs text-[var(--text-faint)] hover:text-[var(--text-dim)] transition-colors"
                title="Regenerate this answer"
              >
                Regenerate
              </button>
            )}
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
                  "bg-[var(--surface-2)] hover:bg-[var(--surface-3)] border border-[var(--border-color)] hover:border-[var(--accent)]/60",
                  "rounded-full text-xs text-[var(--text-dim)] hover:text-[#c8f9eb] transition-all"
                )}
                title={source.title}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-hover)] flex-shrink-0" />
                <span className="truncate max-w-[150px]">{source.title}</span>
                <span className="text-[var(--text-faint)]">• {source.domain}</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
