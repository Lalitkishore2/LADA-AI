"use client";

import { ArrowUp, Bot, Check, ChevronDown, Paperclip, Mic, MicOff, Square, Sparkles } from "lucide-react";
import { useState, useRef, useCallback, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { motion, AnimatePresence } from "framer-motion";

interface UseAutoResizeTextareaProps {
  minHeight: number;
  maxHeight?: number;
}

function useAutoResizeTextarea({ minHeight, maxHeight }: UseAutoResizeTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      if (reset) {
        textarea.style.height = `${minHeight}px`;
        return;
      }

      textarea.style.height = `${minHeight}px`;
      const newHeight = Math.max(
        minHeight,
        Math.min(textarea.scrollHeight, maxHeight ?? Number.POSITIVE_INFINITY)
      );
      textarea.style.height = `${newHeight}px`;
    },
    [minHeight, maxHeight]
  );

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = `${minHeight}px`;
    }
  }, [minHeight]);

  useEffect(() => {
    const handleResize = () => adjustHeight();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [adjustHeight]);

  return { textareaRef, adjustHeight };
}

// Provider icons
const OPENAI_ICON = (
  <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor">
    <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.8956zm16.0993 3.8558L12.6 8.3829l2.02-1.1638a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.4066-.6567zm2.0107-3.0231l-.142-.0852-4.7783-2.7582a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.1408 1.6465 4.4708 4.4708 0 0 1 .5765 3.0137zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z" />
  </svg>
);

const GEMINI_ICON = (
  <svg viewBox="0 0 24 24" className="w-4 h-4">
    <defs>
      <linearGradient id="gemini-gradient" x1="0%" y1="100%" x2="68.73%" y2="30.395%">
        <stop offset="0%" stopColor="#1C7DFF" />
        <stop offset="52.021%" stopColor="#1C69FF" />
        <stop offset="100%" stopColor="#F0DCD6" />
      </linearGradient>
    </defs>
    <path
      d="M12 24A14.304 14.304 0 000 12 14.304 14.304 0 0012 0a14.305 14.305 0 0012 12 14.305 14.305 0 00-12 12"
      fill="url(#gemini-gradient)"
    />
  </svg>
);

const ANTHROPIC_ICON = (
  <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor">
    <path d="M13.827 3.52h3.603L24 20h-3.603l-6.57-16.48zm-7.258 0h3.767L16.906 20h-3.674l-1.343-3.461H5.017l-1.344 3.46H0L6.57 3.522zm4.132 9.959L8.453 7.687 6.205 13.48H10.7z" />
  </svg>
);

const OLLAMA_ICON = (
  <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor">
    <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="2" />
    <circle cx="12" cy="12" r="4" />
  </svg>
);

const GROQ_ICON = (
  <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" fill="none" strokeWidth="2" />
  </svg>
);

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  tier?: string;
}

interface AnimatedAIInputProps {
  models: ModelInfo[];
  selectedModel: string;
  onModelChange: (modelId: string) => void;
  onSend: (message: string) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

const getProviderIcon = (provider: string) => {
  const p = provider.toLowerCase();
  if (p.includes("openai") || p.includes("gpt")) return OPENAI_ICON;
  if (p.includes("gemini") || p.includes("google")) return GEMINI_ICON;
  if (p.includes("claude") || p.includes("anthropic")) return ANTHROPIC_ICON;
  if (p.includes("ollama")) return OLLAMA_ICON;
  if (p.includes("groq")) return GROQ_ICON;
  return <Bot className="w-4 h-4" />;
};

const getTierColor = (tier?: string) => {
  switch (tier?.toLowerCase()) {
    case "fast":
      return "text-green-400";
    case "balanced":
      return "text-blue-400";
    case "smart":
      return "text-purple-400";
    case "reasoning":
      return "text-orange-400";
    case "coding":
      return "text-cyan-400";
    default:
      return "text-gray-400";
  }
};

export function AnimatedAIInput({
  models,
  selectedModel,
  onModelChange,
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
  placeholder = "Ask LADA anything...",
}: AnimatedAIInputProps) {
  const [value, setValue] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 56,
    maxHeight: 200,
  });

  const currentModel = models.find((m) => m.id === selectedModel) || {
    id: selectedModel,
    name: selectedModel,
    provider: "auto",
  };

  // Group models by provider
  const modelsByProvider = models.reduce((acc, model) => {
    const provider = model.provider || "Other";
    if (!acc[provider]) acc[provider] = [];
    acc[provider].push(model);
    return acc;
  }, {} as Record<string, ModelInfo[]>);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && value.trim() && !disabled && !isStreaming) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!value.trim() || disabled || isStreaming) return;
    onSend(value.trim());
    setValue("");
    adjustHeight(true);
  };

  const toggleRecording = () => {
    setIsRecording(!isRecording);
    // Voice recording logic would go here
  };

  return (
    <div className="w-full max-w-3xl mx-auto px-4">
      <div className="bg-zinc-900/80 backdrop-blur-xl rounded-2xl border border-zinc-800/50 shadow-2xl overflow-hidden">
        <div className="relative flex flex-col">
          {/* Textarea */}
          <div className="overflow-y-auto" style={{ maxHeight: "200px" }}>
            <Textarea
              value={value}
              placeholder={placeholder}
              className={cn(
                "w-full rounded-2xl rounded-b-none px-4 py-4 bg-transparent border-none",
                "text-zinc-100 placeholder:text-zinc-500 resize-none",
                "focus-visible:ring-0 focus-visible:ring-offset-0",
                "min-h-[56px] text-base"
              )}
              ref={textareaRef}
              onKeyDown={handleKeyDown}
              onChange={(e) => {
                setValue(e.target.value);
                adjustHeight();
              }}
              disabled={disabled}
            />
          </div>

          {/* Bottom bar */}
          <div className="h-12 bg-zinc-900/50 flex items-center px-3 gap-2">
            {/* Model selector */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className={cn(
                    "flex items-center gap-1.5 h-8 px-2 text-xs rounded-lg",
                    "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
                    "focus-visible:ring-1 focus-visible:ring-offset-0 focus-visible:ring-indigo-500"
                  )}
                >
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={selectedModel}
                      initial={{ opacity: 0, y: -5 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 5 }}
                      transition={{ duration: 0.15 }}
                      className="flex items-center gap-1.5"
                    >
                      {getProviderIcon(currentModel.provider)}
                      <span className="max-w-[120px] truncate">{currentModel.name}</span>
                      <ChevronDown className="w-3 h-3 opacity-50" />
                    </motion.div>
                  </AnimatePresence>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className={cn(
                  "min-w-[220px] max-h-[400px] overflow-y-auto",
                  "border-zinc-800 bg-zinc-900/95 backdrop-blur-xl"
                )}
              >
                {/* Auto option */}
                <DropdownMenuItem
                  onSelect={() => onModelChange("auto")}
                  className="flex items-center justify-between gap-2 text-zinc-300 hover:text-zinc-100 hover:bg-zinc-800/50"
                >
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <span>Auto (Best Available)</span>
                  </div>
                  {selectedModel === "auto" && <Check className="w-4 h-4 text-indigo-400" />}
                </DropdownMenuItem>
                <DropdownMenuSeparator className="bg-zinc-800" />

                {/* Models grouped by provider */}
                {Object.entries(modelsByProvider).map(([provider, providerModels]) => (
                  <div key={provider}>
                    <DropdownMenuLabel className="text-zinc-500 text-xs uppercase tracking-wider">
                      {provider}
                    </DropdownMenuLabel>
                    {providerModels.map((model) => (
                      <DropdownMenuItem
                        key={model.id}
                        onSelect={() => onModelChange(model.id)}
                        className="flex items-center justify-between gap-2 text-zinc-300 hover:text-zinc-100 hover:bg-zinc-800/50"
                      >
                        <div className="flex items-center gap-2">
                          {getProviderIcon(model.provider)}
                          <span className="truncate">{model.name}</span>
                          {model.tier && (
                            <span className={cn("text-[10px] uppercase", getTierColor(model.tier))}>
                              {model.tier}
                            </span>
                          )}
                        </div>
                        {selectedModel === model.id && <Check className="w-4 h-4 text-indigo-400" />}
                      </DropdownMenuItem>
                    ))}
                  </div>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <div className="h-4 w-px bg-zinc-800" />

            {/* Attachment */}
            <label
              className={cn(
                "rounded-lg p-2 cursor-pointer transition-colors",
                "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
              )}
            >
              <input type="file" className="hidden" disabled={disabled} />
              <Paperclip className="w-4 h-4" />
            </label>

            {/* Voice */}
            <button
              type="button"
              onClick={toggleRecording}
              className={cn(
                "rounded-lg p-2 transition-colors",
                isRecording
                  ? "text-red-400 bg-red-500/20 hover:bg-red-500/30"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
              )}
              disabled={disabled}
            >
              {isRecording ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>

            <div className="flex-1" />

            {/* Send/Stop button */}
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                className={cn(
                  "rounded-lg p-2 transition-all",
                  "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                )}
              >
                <Square className="w-4 h-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSend}
                disabled={!value.trim() || disabled}
                className={cn(
                  "rounded-lg p-2 transition-all",
                  value.trim() && !disabled
                    ? "bg-indigo-600 text-white hover:bg-indigo-500"
                    : "bg-zinc-800 text-zinc-600 cursor-not-allowed"
                )}
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Keyboard hint */}
      <div className="flex justify-center mt-2">
        <span className="text-xs text-zinc-600">
          Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">Enter</kbd> to send,{" "}
          <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">Shift+Enter</kbd> for new line
        </span>
      </div>
    </div>
  );
}

export default AnimatedAIInput;
