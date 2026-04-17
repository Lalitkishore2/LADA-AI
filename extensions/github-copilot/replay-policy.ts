export function buildGithubCopilotReplayPolicy(modelId?: string) {
  return (modelId?.toLowerCase() ?? "").includes("lada")
    ? {
        dropThinkingBlocks: true,
      }
    : {};
}

