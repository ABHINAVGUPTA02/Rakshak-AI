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

const EDGE_COLORS: Record<string, string> = {
  INVOLVED_IN: '#3b82f6',
  CO_SUSPECT: '#dc2626',
  USES_PHONE: '#06b6d4',
  FINANCIAL_LINK: '#eab308',
  HAS_TRANSACTION: '#f59e0b',
  PAID_FROM: '#ca8a04',
  PAID_TO: '#ca8a04',
  CALL_RECORD: '#8b5cf6',
  CALLER: '#0ea5e9',
  RECEIVER: '#0ea5e9',
  HAS_PHONE: '#0891b2',
};

const LAYERS: { key: string; label: string; types: string[] }[] = [
  { key: 'cases', label: 'Cases & people', types: ['crime', 'person'] },
  { key: 'comms', label: 'Phones & calls', types: ['phone', 'call'] },
  { key: 'financial', label: 'Money trail', types: ['transaction', 'account'] },
  { key: 'other', label: 'Other evidence', types: ['email', 'vehicle', 'property', 'document'] },
];

const NODE_RADIUS: Record<string, number> = {
  crime: 20,
  person: 14,
  phone: 11,
  call: 11,
  transaction: 11,
  account: 10,
  email: 10,
  vehicle: 10,
  property: 10,
  document: 10,
};

type PositionedNode = GraphNode & { x: number; y: number; shortLabel: string };

function truncate(text: string, max: number): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean.length <= max) return clean;
  return clean.slice(0, max - 1) + '…';
}

function shortLabelFor(node: GraphNode): string {
  const lines = node.label.split('\n');
  if (node.type === 'crime') {
    const fir = lines[0] || node.meta?.fir_number || 'Case';
    return truncate(fir, 10);
  }
  if (node.type === 'person') return truncate(node.label, 11);
  if (node.type === 'phone') {
    const digits = node.label.replace(/\D/g, '');
    return digits.length >= 4 ? `•${digits.slice(-4)}` : '••••';
  }
  if (node.type === 'account') return truncate(node.label, 8);
  if (node.type === 'transaction') return truncate(node.label, 8);
  return truncate(lines[0] || node.label, 8);
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
  const iterations = 80;

  for (let iter = 0; iter < iterations; iter += 1) {
    for (let i = 0; i < result.length; i += 1) {
      for (let j = i + 1; j < result.length; j += 1) {
        const a = result[i];
        const b = result[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.hypot(dx, dy) || 0.01;
        const need = minGap + NODE_RADIUS[a.type] + NODE_RADIUS[b.type];
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
  const adj = buildAdjacency(edges);

  const cols = Math.max(1, Math.ceil(Math.sqrt(crimes.length)));
  const rows = Math.max(1, Math.ceil(crimes.length / cols));
  const clusterW = 240;
  const clusterH = 200;
  const pad = 70;
  const w = pad * 2 + cols * clusterW;
  const h = pad * 2 + rows * clusterH;

  const pos = new Map<string, { x: number; y: number }>();
  const crimeIndex = new Map(crimes.map((c, i) => [c.id, i]));

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

  const placed = new Set<string>(crimeIds);

  for (const [crimeId, groups] of byCrime) {
    const center = pos.get(crimeId);
    if (!center) continue;

    const uniquePersons = [...new Set(groups.persons)];
    uniquePersons.forEach((pid, i) => {
      if (pos.has(pid)) return;
      const n = uniquePersons.length;
      const angle = Math.PI * 0.55 + (i / Math.max(n, 1)) * Math.PI * 0.9;
      pos.set(pid, {
        x: center.x + Math.cos(angle) * 72,
        y: center.y + Math.sin(angle) * 58,
      });
      placed.add(pid);
    });

    const uniqueArtifacts = [...new Set(groups.artifacts)];
    uniqueArtifacts.forEach((aid, i) => {
      if (pos.has(aid)) return;
      const n = uniqueArtifacts.length;
      const angle = -Math.PI / 2 + (i / Math.max(n, 1)) * Math.PI * 0.85;
      pos.set(aid, {
        x: center.x + Math.cos(angle) * 98,
        y: center.y + Math.sin(angle) * 72,
      });
      placed.add(aid);
    });
  }

  for (const node of nodes) {
    if (pos.has(node.id)) continue;

    const neighbors = [...(adj.get(node.id) ?? [])];
    const crimeNeighbors = neighbors.filter((id) => crimeIds.has(id));

    if (crimeNeighbors.length > 0) {
      let sx = 0;
      let sy = 0;
      for (const cid of crimeNeighbors) {
        const p = pos.get(cid);
        if (p) {
          sx += p.x;
          sy += p.y;
        }
      }
      const cx = sx / crimeNeighbors.length;
      const cy = sy / crimeNeighbors.length;
      const idx = crimeIndex.get(crimeNeighbors[0]) ?? 0;
      const angle = (idx % 5) * 1.2;
      pos.set(node.id, {
        x: cx + Math.cos(angle) * 40,
        y: cy + Math.sin(angle) * 40,
      });
    } else {
      const i = placed.size;
      pos.set(node.id, {
        x: w / 2 + Math.cos(i) * 120,
        y: h / 2 + Math.sin(i) * 90,
      });
    }
    placed.add(node.id);
  }

  let positioned: PositionedNode[] = nodes.map((node) => ({
    ...node,
    ...pos.get(node.id)!,
    shortLabel: shortLabelFor(node),
  }));

  positioned = resolveCollisions(positioned, 12, { w, h, pad: 40 });

  return { nodes: positioned, w, h };
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
  const [hoverNode, setHoverNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<PositionedNode | null>(null);

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
  const positions = layout.nodes;
  const posMap = Object.fromEntries(positions.map((n) => [n.id, n]));

  function toggleLayer(key: string) {
    setActiveLayers((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    setSelectedNode(null);
  }

  const insights = graph.insights ?? {};
  const focusId = selectedNode?.id ?? hoverNode;

  const connectedToFocus = useMemo(() => {
    if (!focusId) return new Set<string>();
    const ids = new Set<string>([focusId]);
    for (const edge of filtered.edges) {
      if (edge.source === focusId) ids.add(edge.target);
      if (edge.target === focusId) ids.add(edge.source);
    }
    return ids;
  }, [focusId, filtered.edges]);

  const detailNode = selectedNode ?? (hoverNode ? posMap[hoverNode] ?? null : null);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Investigation Network</h2>
          <p>Hover or click a node for details — labels stay minimal to avoid overlap</p>
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
              <strong>{insights.shared_phones}</strong> shared phone(s) across cases
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
              onChange={() => toggleLayer(layer.key)}
            />
            {layer.label}
          </label>
        ))}
      </div>

      <div className="panel network-panel">
        {loading ? (
          <p className="empty-state">Loading graph…</p>
        ) : positions.length === 0 ? (
          <p className="empty-state">
            No graph data yet. Upload crime data, then click <strong>Rebuild graph</strong>.
          </p>
        ) : (
          <div className="network-wrap">
            <svg
              viewBox={`0 0 ${layout.w} ${layout.h}`}
              className="network-svg"
              role="img"
              aria-label="Investigation network graph"
            >
              <rect x={0} y={0} width={layout.w} height={layout.h} fill="transparent" />

              {filtered.edges.map((edge, i) => {
                const source = posMap[edge.source];
                const target = posMap[edge.target];
                if (!source || !target) return null;
                const isHover = hoverEdge === i;
                const isConnected =
                  focusId && (edge.source === focusId || edge.target === focusId);
                const dimmed = focusId && !isConnected;
                const color = EDGE_COLORS[edge.relationship] || '#475569';
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
                      stroke={color}
                      strokeWidth={isHover || isConnected ? 2.5 : 1.2}
                      strokeOpacity={dimmed ? 0.12 : isHover || isConnected ? 0.9 : 0.35}
                      strokeDasharray={edge.relationship === 'CO_SUSPECT' ? '5 4' : undefined}
                    />
                    {(isHover || isConnected) && edge.label && (
                      <text
                        x={(source.x + target.x) / 2}
                        y={(source.y + target.y) / 2 - 6}
                        fill={color}
                        fontSize={10}
                        textAnchor="middle"
                        className="edge-label"
                      >
                        {edge.label}
                      </text>
                    )}
                  </g>
                );
              })}

              {positions.map((node) => {
                const r = NODE_RADIUS[node.type] ?? 10;
                const isFocused = focusId === node.id;
                const isNeighbor = focusId != null && connectedToFocus.has(node.id) && !isFocused;
                const dimmed = focusId != null && !connectedToFocus.has(node.id);
                const showFullLabel = isFocused;

                return (
                  <g
                    key={node.id}
                    className="graph-node"
                    style={{ cursor: 'pointer', opacity: dimmed ? 0.25 : 1 }}
                    onMouseEnter={() => setHoverNode(node.id)}
                    onMouseLeave={() => setHoverNode(null)}
                    onClick={() => setSelectedNode(selectedNode?.id === node.id ? null : node)}
                  >
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={isFocused ? r + 4 : r}
                      fill={NODE_COLORS[node.type] || '#94a3b8'}
                      stroke={isFocused ? '#f8fafc' : isNeighbor ? '#94a3b8' : 'transparent'}
                      strokeWidth={isFocused ? 2.5 : 1.5}
                    />
                    {showFullLabel && (
                      <g className="node-label-group">
                        <rect
                          x={node.x - 52}
                          y={node.y - r - 28}
                          width={104}
                          height={node.type === 'crime' && node.label.includes('\n') ? 34 : 20}
                          rx={4}
                          className="node-label-bg"
                        />
                        <text
                          x={node.x}
                          y={node.y - r - 14}
                          fill="#f1f5f9"
                          fontSize={10}
                          textAnchor="middle"
                          fontWeight={node.type === 'crime' ? 600 : 400}
                        >
                          {node.label.split('\n').map((line, idx) => (
                            <tspan key={idx} x={node.x} dy={idx === 0 ? 0 : 13}>
                              {truncate(line, 16)}
                            </tspan>
                          ))}
                        </text>
                      </g>
                    )}
                    {!showFullLabel && (
                      <text
                        x={node.x}
                        y={node.y + 4}
                        fill="#0f172a"
                        fontSize={node.type === 'crime' ? 9 : 8}
                        textAnchor="middle"
                        fontWeight={700}
                        pointerEvents="none"
                      >
                        {node.shortLabel}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>

            {detailNode && (
              <aside className="graph-detail">
                {selectedNode && (
                  <button
                    type="button"
                    className="graph-detail-close"
                    onClick={() => setSelectedNode(null)}
                    aria-label="Close"
                  >
                    ×
                  </button>
                )}
                <span
                  className="graph-detail-type"
                  style={{ background: NODE_COLORS[detailNode.type] }}
                >
                  {detailNode.type}
                </span>
                <h3>{detailNode.label.replace('\n', ' · ')}</h3>
                {detailNode.meta?.crime_type && (
                  <p>{detailNode.meta.crime_type}</p>
                )}
                {detailNode.meta?.district && (
                  <p className="graph-detail-meta">{detailNode.meta.district}</p>
                )}
                <p className="graph-detail-hint">
                  {selectedNode ? 'Click × or node again to deselect' : 'Click node to pin details'}
                </p>
              </aside>
            )}
          </div>
        )}

        <div className="legend">
          <span><i style={{ background: NODE_COLORS.crime }} /> Case</span>
          <span><i style={{ background: NODE_COLORS.person }} /> Person</span>
          <span><i style={{ background: NODE_COLORS.phone }} /> Phone</span>
          <span><i style={{ background: NODE_COLORS.account }} /> Account</span>
          <span className="legend-dash">Click a node to focus · dashed = co-suspect</span>
        </div>
      </div>
    </div>
  );
}
