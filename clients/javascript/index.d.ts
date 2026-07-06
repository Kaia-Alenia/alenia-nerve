import { EventEmitter } from 'events';

export interface NexusClientOptions {
  retryInterval?: number;
  configPath?: string;
  authToken?: string;
}

export declare interface NexusClient {
  on(event: 'connect', listener: () => void): this;
  on(event: 'reconnect', listener: () => void): this;
  on(event: 'disconnect', listener: () => void): this;
  on(event: 'message', listener: (message: any) => void): this;
  on(event: 'error', listener: (err: Error) => void): this;
}

export class NexusClient extends EventEmitter {
  retryInterval: number;
  configPath: string;
  authToken: string | null;
  clientId: string | null;
  isWindows: boolean;
  address: string | { host: string; port: number };
  socket: any;
  closed: boolean;
  connecting: boolean;

  constructor(options?: NexusClientOptions);

  connect(clientId: string): Promise<void>;
  disconnect(): void;
  send(to: string, payload: any): void;
  broadcast(payload: any): void;
  listClients(): Promise<string[]>;
  list_clients(): Promise<string[]>;
  listen(
    callback: (message: any) => void,
    onReconnect?: () => void
  ): void;
}

export function loadExternalConfig(configPath?: string): Record<string, any>;
