/**
 * Nerve — Decentralized Nervous System for Local Sockets.
 * Javascript client library types.
 *
 * Built by Alenia Studios.
 * License: GNU General Public License v3 (GPL v3)
 */
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

export class NerveLanClient {
  baseUrl: string;
  constructor(baseUrl?: string);
  lanStatus(): Promise<Record<string, any>>;
  lanScan(options?: { target_ip?: string; timeout?: number; subnet_fallback?: boolean }): Promise<Record<string, any>>;
  lanConnect(ip: string, options?: { name?: string; token?: string }): Promise<Record<string, any>>;
  lanSend(filePath: string, to: string): Promise<Record<string, any>>;
  lanAudit(limit?: number): Promise<Record<string, any>>;
  packNrv(sourcePath: string, outputPath: string, password: string): Promise<Record<string, any>>;
  unpackNrv(nrvPath: string, outputDir: string, password: string): Promise<Record<string, any>>;
}

export function lanStatus(baseUrl?: string): Promise<Record<string, any>>;
export function lanScan(
  options?: { target_ip?: string; timeout?: number; subnet_fallback?: boolean },
  baseUrl?: string
): Promise<Record<string, any>>;
export function lanConnect(
  ip: string,
  options?: { name?: string; token?: string },
  baseUrl?: string
): Promise<Record<string, any>>;
export function lanSend(filePath: string, to: string, baseUrl?: string): Promise<Record<string, any>>;
export function lanAudit(limit?: number, baseUrl?: string): Promise<Record<string, any>>;
export function packNrv(
  sourcePath: string,
  outputPath: string,
  password: string,
  baseUrl?: string
): Promise<Record<string, any>>;
export function unpackNrv(
  nrvPath: string,
  outputDir: string,
  password: string,
  baseUrl?: string
): Promise<Record<string, any>>;
