import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, type GraphEdge, type GraphNode, type NetworkGraph } from '../api/client';

const NODE_COLORS: Record<string, string> = {
  crime: '#ef4444',
  person: '#3b82f6',
  phone: '#06b6d4',
  email: '#ec4899',
  vehicle: '#64748b',
  account: '#eab308',
  property: '#f97316',
  document: '#14b8a6',
  transaction: '#f59e0b',
  call: '#8b5cf6',
};

/** Distinct color + style per relationship type (always visible on graph). */
const REL_STYLES: Record<
  string,
  { color: string; dash?: string; width: number; legend: string }
> = {
  INVOLVED_IN: { color: '#3b82f6', width: 2.5, legend: 'Person → case (role on line)' },
  CO_SUSPECT: { color: '#dc2626', dash: '8 4', width: 2.5, legend: 'Co-suspect' },
  SHARED_PERSON: { color: '#7c3aed', dash: '4 4', width: 2, legend: 'Same person across cases' },
  SHARED_PHONE: { color: '#0891b2', dash: '4 4', width: 2, legend: 'Same phone across cases' },
  SHARED_ACCOUNT: { color: '#ca8a04', dash: '4 4', width: 2, legend: 'Same account across cases' },
  USES_PHONE: { color: '#06b6d4', width: 2, legend: 'Phone in case' },
  HAS_PHONE: { color: '#0284c7', width: 1.8, legend: 'Person has phone' },
  USES_EMAIL: { color: '#ec4899', width: 2, legend: 'Email in case' },
  HAS_EMAIL: { color: '#db2777', width: 1.8, legend: 'Person has email' },
  INVOLVES_VEHICLE: { color: '#64748b', width: 2, legend: 'Vehicle' },
  FINANCIAL_LINK: { color: '#eab308', width: 2, legend: 'Bank / UPI' },
  INVOLVES_PROPERTY: { color: '#f97316', width: 2, legend: 'Property' },
  USES_DOCUMENT: { color: '#14b8a6', width: 2, legend: 'Document' },
  HAS_DOCUMENT: { color: '#0d9488', width: 1.8, legend: 'Person has document' },
  HAS_TRANSACTION: { color: '#f59e0b', width: 2, legend: 'Transaction' },
  PAID_FROM: { color: '#d97706', width: 1.8, legend: 'Paid from' },
  PAID_TO: { color: '#b45309', width: 1.8, legend: 'Paid to' },
  CALL_RECORD: { color: '#8b5cf6', width: 2, legend: 'Call log' },
  CALLER: { color: '#0ea5e9', width: 1.8, legend: 'Caller' },
  RECEIVER: { color: '#6366f1', width: 1.8, legend: 'Receiver' },
};

const LAYERS: { key: string; label: string; types: string[] }[] = [
  { key: 'cases', label: 'Cases & people', types: ['crime', 'person'] },
  { key: 'comms', label: 'Phones & calls', types: ['phone', 'call'] },
  { key: 'financial', label: 'Money trail', types: ['transaction', 'account'] },
  { key: 'other', label: 'Other evidence', types: ['email', 'vehicle', 'property', 'document'] },
];

const NODE_RADIUS: Record<string, number> = {
  crime: 22,
  person: 16,
  phone: 12,
  call: 12,
  transaction: 12,
  account: 11,
  email: 11,
  vehicle: 11,
  property: 11,
  document: 11,
};

type PositionedNode = GraphNode & {
  x: number;
  y: number;
  labelBelow: boolean;
  displayLines: string[];
};

function wrapLabel(text: string, maxLen: number): string[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean.length <= maxLen) return [clean];
  const words = clean.split(' ');
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    if ((cur + ' ' + w).trim().length <= maxLen) {
      cur = (cur + ' ' + w).trim();
    } else {
      if (cur) lines.push(cur);
      cur = w;
    }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 2);
}

function displayLinesFor(node: GraphNode): string[] {
  const raw = node.label.split('\n');
  if (node.type === 'crime') {
    const fir = raw[0] || 'Case';
    const ctype = raw[1] || node.meta?.crime_type;
    return ctype ? [fir, ctype] : [fir];
  }
  if (node.type === 'person') {
    return wrapLabel(node.label, 22);
  }
  if (node.type === 'phone') return [node.label];
  return wrapLabel(raw[0] || node.label, 16);
}

function buildAdjacency(edges: GraphEdge[]): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  for (const { source, target } of edges) {
    if (!adj.has(source)) adj.set(source, new Set());
    if (!adj.has(target)) adj.set(target, new Set());
    adj.get(source)!.add(target);
    adj.get(target)!.add(source);
  }
  return adj;
}

function resolveCollisions(
  nodes: PositionedNode[],
  minGap: number,
  bounds: { w: number; h: number; pad: number },
): PositionedNode[] {
  const result = nodes.map((n) => ({ ...n }));
  for (let iter = 0; iter < 100; iter += 1) {
    for (let i = 0; i < result.length; i += 1) {
      for (let j = i + 1; j < result.length; j += 1) {
        const a = result[i];
        const b = result[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.hypot(dx, dy) || 0.01;
        const labelPad = 28;
        const need = minGap + NODE_RADIUS[a.type] + NODE_RADIUS[b.type] + labelPad;
        if (dist < need) {
          const push = (need - dist) / 2;
          const ux = dx / dist;
          const uy = dy / dist;
          a.x -= ux * push;
          a.y -= uy * push;
          b.x += ux * push;
          b.y += uy * push;
        }
      }
    }
    for (const n of result) {
      n.x = Math.max(bounds.pad, Math.min(bounds.w - bounds.pad, n.x));
      n.y = Math.max(bounds.pad, Math.min(bounds.h - bounds.pad, n.y));
    }
  }
  return result;
}

function computeLayout(nodes: GraphNode[], edges: GraphEdge[]): { nodes: PositionedNode[]; w: number; h: number } {
  const crimes = nodes.filter((n) => n.type === 'crime');
  const crimeIds = new Set(crimes.map((c) => c.id));

  const cols = Math.max(1, Math.ceil(Math.sqrt(crimes.length)));
  const rows = Math.max(1, Math.ceil(crimes.length / cols));
  const clusterW = 300;
  const clusterH = 260;
  const pad = 90;
  const w = pad * 2 + cols * clusterW;
  const h = pad * 2 + rows * clusterH;

  const pos = new Map<string, { x: number; y: number }>();

  crimes.forEach((crime, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    pos.set(crime.id, {
      x: pad + col * clusterW + clusterW / 2,
      y: pad + row * clusterH + clusterH / 2,
    });
  });

  const byCrime = new Map<string, { persons: string[]; artifacts: string[] }>();
  for (const crime of crimes) {
    byCrime.set(crime.id, { persons: [], artifacts: [] });
  }

  for (const edge of edges) {
    const { source, target, relationship } = edge;
    if (relationship === 'INVOLVED_IN') {
      if (crimeIds.has(target) && source.startsWith('person:')) {
        byCrime.get(target)?.persons.push(source);
      }
      if (crimeIds.has(source) && target.startsWith('person:')) {
        byCrime.get(source)?.persons.push(target);
      }
    }
    for (const cid of crimeIds) {
      if (source === cid && !crimeIds.has(target) && !target.startsWith('person:')) {
        byCrime.get(cid)?.artifacts.push(target);
      }
      if (target === cid && !crimeIds.has(source) && !source.startsWith('person:')) {
        byCrime.get(cid)?.artifacts.push(source);
      }
    }
  }

  for (const [crimeId, groups] of byCrime) {
    const center = pos.get(crimeId);
    if (!center) continue;

    const uniquePersons = [...new Set(groups.persons)];
    uniquePersons.forEach((pid, i) => {
      if (pos.has(pid)) return;
      const n = uniquePersons.length;
      const angle = Math.PI * 0.5 + (i / Math.max(n, 1)) * Math.PI;
      pos.set(pid, {
        x: center.x + Math.cos(angle) * 88,
        y: center.y + Math.sin(angle) * 72,
      });
    });

    const uniqueArtifacts = [...new Set(groups.artifacts)];
    uniqueArtifacts.forEach((aid, i) => {
      if (pos.has(aid)) return;
      const n = uniqueArtifacts.length;
      const angle = -Math.PI / 2 + (i / Math.max(n, 1)) * Math.PI * 0.9;
      pos.set(aid, {
        x: center.x + Math.cos(angle) * 118,
        y: center.y + Math.sin(angle) * 88,
      });
    });
  }

  const adj = buildAdjacency(edges);
  let fallback = 0;
  for (const node of nodes) {
    if (pos.has(node.id)) continue;
    const neighbors = [...(adj.get(node.id) ?? [])].filter((id) => crimeIds.has(id));
    if (neighbors.length >= 2) {
      let sx = 0;
      let sy = 0;
      for (const cid of neighbors) {
        const p = pos.get(cid);
        if (p) {
          sx += p.x;
          sy += p.y;
        }
      }
      pos.set(node.id, { x: sx / neighbors.length, y: sy / neighbors.length });
    } else if (neighbors.length === 1) {
      const c = pos.get(neighbors[0])!;
      pos.set(node.id, { x: c.x, y: c.y - 100 });
    } else {
      pos.set(node.id, {
        x: w / 2 + Math.cos(fallback) * 140,
        y: h / 2 + Math.sin(fallback) * 100,
      });
      fallback += 1;
    }
  }

  let positioned: PositionedNode[] = nodes.map((node, idx) => ({
    ...node,
    ...pos.get(node.id)!,
    labelBelow: idx % 2 === 0,
    displayLines: displayLinesFor(node),
  }));

  positioned = resolveCollisions(positioned, 16, { w, h, pad: 50 });

  return { nodes: positioned, w, h };
}

function edgeStyle(relationship: string) {
  return (
    REL_STYLES[relationship] ?? {
      color: '#64748b',
      width: 1.5,
      legend: relationship.replace(/_/g, ' ').toLowerCase(),
    }
  );
}

export default function NetworkGraph() {
  const [graph, setGraph] = useState<NetworkGraph>({ nodes: [], edges: [], insights: {} });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [activeLayers, setActiveLayers] = useState<Set<string>>(
    () => new Set(LAYERS.map((l) => l.key)),
  );
  const [hoverEdge, setHoverEdge] = useState<number | null>(null);

  const loadGraph = useCallback(() => {
    setLoading(true);
    api
      .getNetwork()
      .then(setGraph)
      .catch(() => setError('Unable to load network graph. Ensure Neo4j is running.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  async function handleSync() {
    setSyncing(true);
    setError('');
    try {
      await api.syncGraph();
      loadGraph();
    } catch {
      setError('Graph sync failed. Is Neo4j running?');
    } finally {
      setSyncing(false);
    }
  }

  const activeTypes = useMemo(() => {
    const types = new Set<string>();
    for (const layer of LAYERS) {
      if (activeLayers.has(layer.key)) {
        layer.types.forEach((t) => types.add(t));
      }
    }
    return types;
  }, [activeLayers]);

  const filtered = useMemo(() => {
    const nodes = graph.nodes.filter((n) => activeTypes.has(n.type));
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
    return { nodes, edges };
  }, [graph, activeTypes]);

  const layout = useMemo(
    () => computeLayout(filtered.nodes, filtered.edges),
    [filtered.nodes, filtered.edges],
  );
  const posMap = Object.fromEntries(layout.nodes.map((n) => [n.id, n]));

  const activeRelTypes = useMemo(() => {
    const set = new Set<string>();
    for (const e of filtered.edges) set.add(e.relationship);
    return [...set].sort();
  }, [filtered.edges]);

  const insights = graph.insights ?? {};

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Criminal Network Graph</h2>
          <p>Colored lines show relationship types; labels on nodes and links define who connects to what</p>
        </div>
        <button type="button" className="sync-btn" onClick={handleSync} disabled={syncing}>
          {syncing ? 'Rebuilding…' : 'Rebuild graph'}
        </button>
      </header>

      {error && <div className="alert">{error}</div>}

      {insights.cases != null && insights.cases > 0 && (
        <div className="graph-insights">
          <span><strong>{insights.cases}</strong> cases</span>
          <span><strong>{insights.people}</strong> people</span>
          <span><strong>{insights.phones}</strong> phones</span>
          {insights.shared_phones ? (
            <span className="insight-highlight">
              <strong>{insights.shared_phones}</strong> shared phone(s)
            </span>
          ) : null}
        </div>
      )}

      <div className="graph-filters">
        {LAYERS.map((layer) => (
          <label key={layer.key} className="layer-toggle">
            <input
              type="checkbox"
              checked={activeLayers.has(layer.key)}
              onChange={() => {
                setActiveLayers((prev) => {
                  const next = new Set(prev);
                  if (next.has(layer.key)) next.delete(layer.key);
                  else next.add(layer.key);
                  return next;
                });
              }}
            />
            {layer.label}
          </label>
        ))}
      </div>

      {activeRelTypes.length > 0 && (
        <div className="rel-legend">
          <span className="rel-legend-title">Relationships</span>
          {activeRelTypes.map((rel) => {
            const st = edgeStyle(rel);
            return (
              <span key={rel} className="rel-legend-item" title={st.legend}>
                <svg width={28} height={10} aria-hidden>
                  <line
                    x1={0}
                    y1={5}
                    x2={28}
                    y2={5}
                    stroke={st.color}
                    strokeWidth={st.width}
                    strokeDasharray={st.dash}
                  />
                </svg>
                {st.legend}
              </span>
            );
          })}
        </div>
      )}

      <div className="panel network-panel">
        {loading ? (
          <p className="empty-state">Loading graph…</p>
        ) : layout.nodes.length === 0 ? (
          <p className="empty-state">
            No graph data. Upload data, then click <strong>Rebuild graph</strong>.
          </p>
        ) : (
          <div className="network-wrap">
            <svg
              viewBox={`0 0 ${layout.w} ${layout.h}`}
              className="network-svg network-svg-detailed"
              role="img"
              aria-label="Criminal network graph"
            >
              <defs>
                {activeRelTypes.map((rel) => {
                  const st = edgeStyle(rel);
                  return (
                    <marker
                      key={rel}
                      id={`arrow-${rel}`}
                      markerWidth={8}
                      markerHeight={8}
                      refX={7}
                      refY={4}
                      orient="auto"
                    >
                      <path d="M0,0 L8,4 L0,8 Z" fill={st.color} />
                    </marker>
                  );
                })}
              </defs>

              {filtered.edges.map((edge, i) => {
                const source = posMap[edge.source];
                const target = posMap[edge.target];
                if (!source || !target) return null;
                const st = edgeStyle(edge.relationship);
                const isHover = hoverEdge === i;
                const mx = (source.x + target.x) / 2;
                const my = (source.y + target.y) / 2;
                const directed = [
                  'INVOLVED_IN',
                  'HAS_PHONE',
                  'HAS_EMAIL',
                  'HAS_DOCUMENT',
                  'PAID_FROM',
                  'PAID_TO',
                  'CALLER',
                  'RECEIVER',
                  'HAS_TRANSACTION',
                  'CALL_RECORD',
                ].includes(edge.relationship);

                return (
                  <g
                    key={`${edge.source}-${edge.target}-${edge.relationship}-${i}`}
                    onMouseEnter={() => setHoverEdge(i)}
                    onMouseLeave={() => setHoverEdge(null)}
                  >
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      stroke={st.color}
                      strokeWidth={isHover ? st.width + 1 : st.width}
                      strokeOpacity={isHover ? 1 : 0.85}
                      strokeDasharray={st.dash}
                      markerEnd={directed ? `url(#arrow-${edge.relationship})` : undefined}
                    />
                    {edge.label && (
                      <g>
                        <rect
                          x={mx - 36}
                          y={my - 9}
                          width={72}
                          height={16}
                          rx={3}
                          className="edge-label-bg"
                        />
                        <text
                          x={mx}
                          y={my + 3}
                          fill={st.color}
                          fontSize={10}
                          fontWeight={isHover ? 700 : 600}
                          textAnchor="middle"
                          className="edge-label-text"
                        >
                          {edge.label}
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}

              {layout.nodes.map((node) => {
                const r = NODE_RADIUS[node.type] ?? 12;
                const lines = node.displayLines;
                const lineH = 13;
                const boxH = lines.length * lineH + 8;
                const boxW = Math.min(140, Math.max(72, ...lines.map((l) => l.length * 6.5)));
                const below = node.labelBelow;
                const labelY = below ? node.y + r + 10 : node.y - r - boxH - 6;

                return (
                  <g key={node.id} className="graph-node-detailed">
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={r}
                      fill={NODE_COLORS[node.type] || '#94a3b8'}
                      stroke="#1e293b"
                      strokeWidth={2}
                      opacity={0.95}
                    />
                    <rect
                      x={node.x - boxW / 2}
                      y={labelY}
                      width={boxW}
                      height={boxH}
                      rx={5}
                      className="node-label-bg"
                    />
                    <text
                      x={node.x}
                      y={labelY + 14}
                      fill="#f8fafc"
                      fontSize={node.type === 'crime' ? 11 : 10}
                      textAnchor="middle"
                      fontWeight={node.type === 'crime' ? 700 : 500}
                    >
                      {lines.map((line, idx) => (
                        <tspan key={idx} x={node.x} dy={idx === 0 ? 0 : lineH}>
                          {line}
                        </tspan>
                      ))}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        )}

        <div className="legend">
          <span><i style={{ background: NODE_COLORS.crime }} /> Case</span>
          <span><i style={{ background: NODE_COLORS.person }} /> Person</span>
          <span><i style={{ background: NODE_COLORS.phone }} /> Phone</span>
          <span><i style={{ background: NODE_COLORS.account }} /> Account</span>
          <span><i style={{ background: NODE_COLORS.transaction }} /> Transaction</span>
          <span><i style={{ background: NODE_COLORS.call }} /> Call</span>
        </div>
      </div>
    </div>
  );
}
