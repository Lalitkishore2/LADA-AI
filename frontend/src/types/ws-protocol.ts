// ---------------------------------------------------------------------------
// LADA WebSocket Protocol Types
// Matches the Python FastAPI backend at /ws
// ---------------------------------------------------------------------------

// ---- Shared / Utility Types -----------------------------------------------

/** Unique message identifier (UUID or similar) */
export type MessageId = string;

/** Information about a single AI model exposed by the backend */
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  tier: string;
  available: boolean;
}

/** A source reference returned alongside a chat response */
export interface Source {
  title: string;
  url: string;
  snippet?: string;
}

// ---- Client -> Server Messages --------------------------------------------

export interface ClientChatMessage {
  type: 'chat';
  id: MessageId;
  data: {
    message: string;
    stream: boolean;
    model?: string;
  };
}

export interface ClientAgentMessage {
  type: 'agent';
  id: MessageId;
  data: {
    agent: string;
    action: string;
    params: Record<string, unknown>;
  };
}

export interface ClientSystemMessage {
  type: 'system';
  id: MessageId;
  data: {
    action: 'status' | 'models' | 'clear_history';
  };
}

export interface ClientPingMessage {
  type: 'ping';
}

/** Discriminated union of every message the client can send. */
export type ClientMessage =
  | ClientChatMessage
  | ClientAgentMessage
  | ClientSystemMessage
  | ClientPingMessage;

// ---- Server -> Client Messages --------------------------------------------

export interface ServerConnectedMessage {
  type: 'system.connected';
  data: {
    session_id: string;
  };
}

export interface ServerModelsMessage {
  type: 'system.models';
  data: {
    models: ModelInfo[];
  };
}

export interface ServerStatusMessage {
  type: 'system.status';
  data: Record<string, unknown>;
}

export interface ServerAckMessage {
  type: 'system.ack';
}

export interface ServerChatStartMessage {
  type: 'chat.start';
  id: MessageId;
}

export interface ServerChatChunkMessage {
  type: 'chat.chunk';
  id: MessageId;
  data: {
    chunk: string;
  };
}

export interface ServerChatSourcesMessage {
  type: 'chat.sources';
  id: MessageId;
  data: {
    sources: Source[];
  };
}

export interface ServerChatDoneMessage {
  type: 'chat.done';
  id: MessageId;
  data: {
    model: string;
  };
}

export interface ServerChatResponseMessage {
  type: 'chat.response';
  id: MessageId;
  data: {
    content: string;
    model: string;
  };
}

export interface ServerErrorMessage {
  type: 'error';
  id: MessageId;
  data: {
    message: string;
  };
}

export interface ServerPongMessage {
  type: 'pong';
}

/** Discriminated union of every message the server can send. */
export type ServerMessage =
  | ServerConnectedMessage
  | ServerModelsMessage
  | ServerStatusMessage
  | ServerAckMessage
  | ServerChatStartMessage
  | ServerChatChunkMessage
  | ServerChatSourcesMessage
  | ServerChatDoneMessage
  | ServerChatResponseMessage
  | ServerErrorMessage
  | ServerPongMessage;

// ---- Convenience helpers --------------------------------------------------

/** Extract the literal `type` string from a ServerMessage variant */
export type ServerMessageType = ServerMessage['type'];

/** Look up the ServerMessage variant whose `type` equals T */
export type ServerMessageByType<T extends ServerMessageType> = Extract<
  ServerMessage,
  { type: T }
>;
