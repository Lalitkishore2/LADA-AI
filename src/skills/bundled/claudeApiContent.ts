// Content for the lada-api bundled skill.
// Each .md file is inlined as a string at build time via Bun's text loader.

import csharpLADAApi from './lada-api/csharp/lada-api.md'
import curlExamples from './lada-api/curl/examples.md'
import goLADAApi from './lada-api/go/lada-api.md'
import javaLADAApi from './lada-api/java/lada-api.md'
import phpLADAApi from './lada-api/php/lada-api.md'
import pythonAgentSdkPatterns from './lada-api/python/agent-sdk/patterns.md'
import pythonAgentSdkReadme from './lada-api/python/agent-sdk/README.md'
import pythonLADAApiBatches from './lada-api/python/lada-api/batches.md'
import pythonLADAApiFilesApi from './lada-api/python/lada-api/files-api.md'
import pythonLADAApiReadme from './lada-api/python/lada-api/README.md'
import pythonLADAApiStreaming from './lada-api/python/lada-api/streaming.md'
import pythonLADAApiToolUse from './lada-api/python/lada-api/tool-use.md'
import rubyLADAApi from './lada-api/ruby/lada-api.md'
import skillPrompt from './lada-api/SKILL.md'
import sharedErrorCodes from './lada-api/shared/error-codes.md'
import sharedLiveSources from './lada-api/shared/live-sources.md'
import sharedModels from './lada-api/shared/models.md'
import sharedPromptCaching from './lada-api/shared/prompt-caching.md'
import sharedToolUseConcepts from './lada-api/shared/tool-use-concepts.md'
import typescriptAgentSdkPatterns from './lada-api/typescript/agent-sdk/patterns.md'
import typescriptAgentSdkReadme from './lada-api/typescript/agent-sdk/README.md'
import typescriptLADAApiBatches from './lada-api/typescript/lada-api/batches.md'
import typescriptLADAApiFilesApi from './lada-api/typescript/lada-api/files-api.md'
import typescriptLADAApiReadme from './lada-api/typescript/lada-api/README.md'
import typescriptLADAApiStreaming from './lada-api/typescript/lada-api/streaming.md'
import typescriptLADAApiToolUse from './lada-api/typescript/lada-api/tool-use.md'

// @[MODEL LAUNCH]: Update the model IDs/names below. These are substituted into {{VAR}}
// placeholders in the .md files at runtime before the skill prompt is sent.
// After updating these constants, manually update the two files that still hardcode models:
//   - lada-api/SKILL.md (Current Models pricing table)
//   - lada-api/shared/models.md (full model catalog with legacy versions and alias mappings)
export const SKILL_MODEL_VARS = {
  OPUS_ID: 'lada-opus-4-6',
  OPUS_NAME: 'LADA Opus 4.6',
  SONNET_ID: 'lada-sonnet-4-6',
  SONNET_NAME: 'LADA Sonnet 4.6',
  HAIKU_ID: 'lada-haiku-4-5',
  HAIKU_NAME: 'LADA Haiku 4.5',
  // Previous Sonnet ID — used in "do not append date suffixes" example in SKILL.md.
  PREV_SONNET_ID: 'lada-sonnet-4-5',
} satisfies Record<string, string>

export const SKILL_PROMPT: string = skillPrompt

export const SKILL_FILES: Record<string, string> = {
  'csharp/lada-api.md': csharpLADAApi,
  'curl/examples.md': curlExamples,
  'go/lada-api.md': goLADAApi,
  'java/lada-api.md': javaLADAApi,
  'php/lada-api.md': phpLADAApi,
  'python/agent-sdk/README.md': pythonAgentSdkReadme,
  'python/agent-sdk/patterns.md': pythonAgentSdkPatterns,
  'python/lada-api/README.md': pythonLADAApiReadme,
  'python/lada-api/batches.md': pythonLADAApiBatches,
  'python/lada-api/files-api.md': pythonLADAApiFilesApi,
  'python/lada-api/streaming.md': pythonLADAApiStreaming,
  'python/lada-api/tool-use.md': pythonLADAApiToolUse,
  'ruby/lada-api.md': rubyLADAApi,
  'shared/error-codes.md': sharedErrorCodes,
  'shared/live-sources.md': sharedLiveSources,
  'shared/models.md': sharedModels,
  'shared/prompt-caching.md': sharedPromptCaching,
  'shared/tool-use-concepts.md': sharedToolUseConcepts,
  'typescript/agent-sdk/README.md': typescriptAgentSdkReadme,
  'typescript/agent-sdk/patterns.md': typescriptAgentSdkPatterns,
  'typescript/lada-api/README.md': typescriptLADAApiReadme,
  'typescript/lada-api/batches.md': typescriptLADAApiBatches,
  'typescript/lada-api/files-api.md': typescriptLADAApiFilesApi,
  'typescript/lada-api/streaming.md': typescriptLADAApiStreaming,
  'typescript/lada-api/tool-use.md': typescriptLADAApiToolUse,
}

