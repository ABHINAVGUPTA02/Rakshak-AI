const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  return response.json();
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  getStats: () => request<CrimeStats>('/analytics/stats'),
  getHotspots: () => request<Hotspot[]>('/analytics/hotspots'),
  getCrimes: () => request<CrimeRecord[]>('/crimes'),
  getNetwork: () => request<NetworkGraph>('/graph/network'),
  chat: (message: string, language = 'en') =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, language }),
    }),
};

export interface CrimeStats {
  total_crimes: number;
  by_type: Record<string, number>;
  by_district: Record<string, number>;
  open_cases: number;
}

export interface Hotspot {
  district: string;
  latitude: number;
  longitude: number;
  crime_count: number;
}

export interface CrimeRecord {
  id: number;
  fir_number: string;
  crime_type: string;
  description: string | null;
  district: string;
  police_station: string | null;
  status: string;
  incident_date: string | null;
}

export interface NetworkGraph {
  nodes: { id: string; label: string; type: string }[];
  edges: { source: string; target: string; relationship: string }[];
}

export interface ChatResponse {
  reply: string;
  evidence: { source: string; detail: string }[];
  suggested_queries: string[];
}
