import { listSkillCommandsForAgents as listSkillCommandsForAgentsImpl } from "lada/plugin-sdk/command-auth";

type ListSkillCommandsForAgents =
  typeof import("lada/plugin-sdk/command-auth").listSkillCommandsForAgents;

export function listSkillCommandsForAgents(
  ...args: Parameters<ListSkillCommandsForAgents>
): ReturnType<ListSkillCommandsForAgents> {
  return listSkillCommandsForAgentsImpl(...args);
}

