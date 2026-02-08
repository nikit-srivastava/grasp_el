import { base } from '$app/paths';

export const APP_COLORS = Object.freeze({
  uniBlue: '#344A9A',
  uniDarkBlue: '#000149',
  uniRed: '#C1002A',
  uniGray: '#B4B4B4',
  uniGreen: '#00A082',
  uniYellow: '#BEAA3C',
  uniPink: '#A35394',
  surface: '#FFFFFF'
});

export const BRAND_LINKS = Object.freeze({
  chair: 'https://ad.cs.uni-freiburg.de',
  repo: 'https://github.com/ad-freiburg/grasp',
  methodPaper: 'https://ad-publications.cs.uni-freiburg.de/ISWC_grasp_WB_2025.pdf',
  systemPaper: 'https://ad-publications.cs.uni-freiburg.de/ISWC_grasp_demo_WB_2025.pdf',
  entityLinkingPaper:
    'https://ad-publications.cs.uni-freiburg.de/SEMTAB_entity_linking_grasp_WB_2025.pdf',
  evaluation: 'https://grasp.cs.uni-freiburg.de/evaluate/',
  data: 'https://ad-publications.cs.uni-freiburg.de/grasp/'
});

/* global __API_BASE__ */

/**
 * API base URL, set at build time via the API_BASE env var.
 *
 *   API_BASE=/api                          (default – same origin, reverse proxy)
 *   API_BASE=http://localhost:6789         (direct, dev)
 *   API_BASE=https://example.com/my/api    (custom prefix)
 *
 * Relative paths are prefixed with BASE_PATH, so BASE_PATH=/v1 + API_BASE=/api
 * results in /v1/api. Absolute URLs are used as-is.
 */
const RAW_API_BASE = __API_BASE__.replace(/\/+$/, '');
const API_BASE = /^https?:\/\//.test(RAW_API_BASE) ? RAW_API_BASE : `${base}${RAW_API_BASE}`;

export const getApiBase = () => API_BASE;

export const TASKS = Object.freeze([
  {
    id: 'sparql-qa',
    name: 'SPARQL QA',
    tooltip:
      'Answer questions by generating a corresponding SPARQL query over one or more knowledge graphs.'
  },
  {
    id: 'general-qa',
    name: 'General QA',
    tooltip:
      'Answer questions by retrieving relevant information from knowledge graphs.'
  },
  {
    id: 'cea',
    name: 'Cell Entity Annotation',
    tooltip:
      'Upload a CSV table to annotate each cell with corresponding knowledge graph entities.'
  }
]);

export const QLEVER_HOSTS = Object.freeze([
  'qlever.cs.uni-freiburg.de',
  'qlever.informatik.uni-freiburg.de',
  'qlever.dev'
]);

export const endpointFor = (path) => `${getApiBase()}${path}`;

export const wsEndpoint = () => {
  if (/^https?:\/\//.test(API_BASE)) {
    return API_BASE.replace(/^http/, 'ws') + '/live';
  }
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${window.location.host}${API_BASE}/live`;
};

export const configEndpoint = () => endpointFor('/config');
export const kgEndpoint = () => endpointFor('/knowledge_graphs');
export const saveSharedStateEndpoint = () => endpointFor('/save');
export const loadSharedStateEndpoint = (id) => endpointFor(`/load/${encodeURIComponent(id)}`);
export const sharePathForId = (id) => {
  const trimmed = typeof id === 'string' ? id.trim() : '';
  if (!trimmed) return '';
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  return `${origin}${base}/share/${trimmed}`;
};
