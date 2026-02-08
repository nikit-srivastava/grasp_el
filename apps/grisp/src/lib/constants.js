/* global __API_BASE__ __COPYRIGHT__ */
import { base } from '$app/paths';

/**
 * Copyright text, set at build time via the COPYRIGHT env var.
 * Defaults to 'University of Freiburg'.
 */
export const COPYRIGHT = __COPYRIGHT__;

/**
 * API base URL, set at build time via the API_BASE env var.
 *
 *   API_BASE=/api                          (default – same origin, reverse proxy)
 *   API_BASE=http://localhost:6790         (direct, dev)
 *   API_BASE=https://example.com/my/api    (custom prefix)
 *
 * Relative paths are prefixed with BASE_PATH, so BASE_PATH=/v1 + API_BASE=/api
 * results in /v1/api. Absolute URLs are used as-is.
 */
const RAW_API_BASE = __API_BASE__.replace(/\/+$/, '');
const API_BASE = /^https?:\/\//.test(RAW_API_BASE) ? RAW_API_BASE : `${base}${RAW_API_BASE}`;

export const getApiBase = () => API_BASE;

export const wsEndpoint = () => {
  if (/^https?:\/\//.test(API_BASE)) {
    return API_BASE.replace(/^http/, 'ws') + '/live';
  }
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${window.location.host}${API_BASE}/live`;
};

export const configEndpoint = () => `${API_BASE}/config`;
export const kgEndpoint = () => `${API_BASE}/knowledge_graphs`;
