import { transcribeFirstAudio as transcribeFirstAudioImpl } from "lada/plugin-sdk/media-runtime";

type TranscribeFirstAudio = typeof import("lada/plugin-sdk/media-runtime").transcribeFirstAudio;

export async function transcribeFirstAudio(
  ...args: Parameters<TranscribeFirstAudio>
): ReturnType<TranscribeFirstAudio> {
  return await transcribeFirstAudioImpl(...args);
}

