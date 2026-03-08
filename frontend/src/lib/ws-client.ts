// ---------------------------------------------------------------------------
// LADA Reconnecting WebSocket Client
// ---------------------------------------------------------------------------

import type {
  ClientMessage,
  ServerMessage,
  ServerMessageType,
  ServerMessageByType,
  MessageId,
} from '@/types/ws-protocol';

// ---- Types ----------------------------------------------------------------

type MessageHandler = (msg: ServerMessage) => void;
type ConnectHandler = () => void;
type DisconnectHandler = (ev: CloseEvent) => void;

export interface WSClientOptions {
  /** Full WebSocket URL. Defaults to ws://127.0.0.1:5000/ws */
  url?: string;
  /** Delay in ms before attempting reconnect. Default 3000 */
  reconnectDelay?: number;
  /** Interval in ms between keep-alive pings. Default 30000 */
  pingInterval?: number;
  /** Whether to reconnect automatically. Default true */
  autoReconnect?: boolean;
}

// ---- Helpers --------------------------------------------------------------

let _idCounter = 0;

/** Generate a simple unique message id */
export function generateId(): MessageId {
  _idCounter += 1;
  return `${Date.now()}-${_idCounter}`;
}

// ---- WSClient class -------------------------------------------------------

export class WSClient {
  // Config
  private readonly url: string;
  private readonly reconnectDelay: number;
  private readonly pingInterval: number;
  private autoReconnect: boolean;

  // State
  private ws: WebSocket | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _sessionId: string | null = null;
  private _connected = false;

  // Listeners
  private messageHandlers: Set<MessageHandler> = new Set();
  private connectHandlers: Set<ConnectHandler> = new Set();
  private disconnectHandlers: Set<DisconnectHandler> = new Set();

  constructor(options: WSClientOptions = {}) {
    this.url = options.url ?? 'ws://127.0.0.1:5000/ws';
    this.reconnectDelay = options.reconnectDelay ?? 3000;
    this.pingInterval = options.pingInterval ?? 30000;
    this.autoReconnect = options.autoReconnect ?? true;
  }

  // ---- Public getters -----------------------------------------------------

  /** The session id assigned by the server, or null if not yet connected */
  get sessionId(): string | null {
    return this._sessionId;
  }

  /** Whether the underlying WebSocket is currently open */
  get connected(): boolean {
    return this._connected;
  }

  // ---- Connection lifecycle -----------------------------------------------

  /** Open (or re-open) the WebSocket connection. */
  connect(): void {
    // Clean up any previous socket
    this.cleanup();

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this._connected = true;
      this.startPing();

      // Request model list immediately after connecting
      this.send({
        type: 'system',
        id: generateId(),
        data: { action: 'models' },
      });

      this.connectHandlers.forEach((h) => h());
    };

    this.ws.onmessage = (event: MessageEvent) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(event.data as string) as ServerMessage;
      } catch {
        // Ignore malformed frames
        return;
      }

      // Track session id
      if (msg.type === 'system.connected') {
        this._sessionId = msg.data.session_id;
      }

      this.messageHandlers.forEach((h) => h(msg));
    };

    this.ws.onclose = (ev: CloseEvent) => {
      this._connected = false;
      this.stopPing();
      this.disconnectHandlers.forEach((h) => h(ev));
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      // The browser will fire `onclose` right after `onerror`, which takes
      // care of reconnect scheduling -- nothing else needed here.
    };
  }

  /** Gracefully close the connection without auto-reconnecting. */
  disconnect(): void {
    this.autoReconnect = false;
    this.cleanup();
  }

  // ---- Sending messages ---------------------------------------------------

  /** Send a typed client message over the socket. */
  send(msg: ClientMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WSClient] Cannot send -- socket is not open');
      return;
    }
    this.ws.send(JSON.stringify(msg));
  }

  /** Convenience: send a chat message and return its id. */
  sendChat(message: string, stream = true, model?: string): MessageId {
    const id = generateId();
    this.send({
      type: 'chat',
      id,
      data: { message, stream, model },
    });
    return id;
  }

  // ---- Event registration -------------------------------------------------

  /** Register a handler that receives every parsed ServerMessage. */
  onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => {
      this.messageHandlers.delete(handler);
    };
  }

  /**
   * Register a handler for a specific ServerMessage type.
   * Returns an unsubscribe function.
   */
  onMessageType<T extends ServerMessageType>(
    type: T,
    handler: (msg: ServerMessageByType<T>) => void,
  ): () => void {
    const wrapped: MessageHandler = (msg) => {
      if (msg.type === type) {
        handler(msg as ServerMessageByType<T>);
      }
    };
    this.messageHandlers.add(wrapped);
    return () => {
      this.messageHandlers.delete(wrapped);
    };
  }

  /** Register a handler called when the WebSocket connection opens. */
  onConnect(handler: ConnectHandler): () => void {
    this.connectHandlers.add(handler);
    return () => {
      this.connectHandlers.delete(handler);
    };
  }

  /** Register a handler called when the WebSocket connection closes. */
  onDisconnect(handler: DisconnectHandler): () => void {
    this.disconnectHandlers.add(handler);
    return () => {
      this.disconnectHandlers.delete(handler);
    };
  }

  // ---- Internals ----------------------------------------------------------

  private cleanup(): void {
    this.stopPing();
    this.clearReconnectTimer();

    if (this.ws) {
      // Detach handlers so we don't fire reconnect logic on intentional close
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;

      if (
        this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING
      ) {
        this.ws.close();
      }
      this.ws = null;
    }

    this._connected = false;
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      this.send({ type: 'ping' });
    }, this.pingInterval);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (!this.autoReconnect) return;
    this.clearReconnectTimer();
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, this.reconnectDelay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
