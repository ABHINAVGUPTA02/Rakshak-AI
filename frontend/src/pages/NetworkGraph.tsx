import { useEffect, useState } from 'react';
import { api, type NetworkGraph } from '../api/client';

const NODE_COLORS: Record<string, string> = {
  crime: '#ef4444',
  person: '#3b82f6',
  location: '#22c55e',
  policestation: '#f59e0b',
  crimetype: '#a855f7',
};

export default function NetworkGraph() {
  const [graph, setGraph] = useState<NetworkGraph>({ nodes: [], edges: [] });
  const [error, setError] = useState('');

  useEffect(() => {
    api.getNetwork()
      .then(setGraph)
      .catch(() => setError('Unable to load network graph. Ensure Neo4j is running.'));
  }, []);

  const positions = graph.nodes.map((node, i) => {
    const angle = (i / Math.max(graph.nodes.length, 1)) * 2 * Math.PI;
    const radius = 140 + (i % 3) * 30;
    return {
      ...node,
      x: 300 + Math.cos(angle) * radius,
      y: 250 + Math.sin(angle) * radius,
    };
  });

  const posMap = Object.fromEntries(positions.map((n) => [n.id, n]));

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Criminal Network Graph</h2>
          <p>Knowledge graph — crimes, persons, locations, police stations, crime types</p>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <div className="panel network-panel">
        {graph.nodes.length === 0 ? (
          <p className="empty-state">No graph data yet. Start Neo4j and sync crimes from the API.</p>
        ) : (
          <svg viewBox="0 0 600 500" className="network-svg">
            {graph.edges.map((edge, i) => {
              const source = posMap[edge.source];
              const target = posMap[edge.target];
              if (!source || !target) return null;
              return (
                <g key={i}>
                  <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke="#475569" strokeWidth={1.5} />
                  <text
                    x={(source.x + target.x) / 2}
                    y={(source.y + target.y) / 2}
                    fill="#64748b"
                    fontSize={9}
                    textAnchor="middle"
                  >
                    {edge.relationship}
                  </text>
                </g>
              );
            })}
            {positions.map((node) => (
              <g key={node.id}>
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.type === 'crime' ? 18 : node.type === 'crimetype' ? 16 : 14}
                  fill={NODE_COLORS[node.type] || '#94a3b8'}
                  opacity={0.85}
                />
                <text x={node.x} y={node.y + 30} fill="#e2e8f0" fontSize={10} textAnchor="middle">
                  {node.label.length > (node.type === 'person' ? 22 : 16)
                    ? node.label.slice(0, node.type === 'person' ? 20 : 14) + '…'
                    : node.label}
                </text>
              </g>
            ))}
          </svg>
        )}

        <div className="legend">
          <span><i style={{ background: NODE_COLORS.crime }} /> Crime</span>
          <span><i style={{ background: NODE_COLORS.person }} /> Person</span>
          <span><i style={{ background: NODE_COLORS.location }} /> Location</span>
          <span><i style={{ background: NODE_COLORS.policestation }} /> Police Station</span>
          <span><i style={{ background: NODE_COLORS.crimetype }} /> Crime Type</span>
        </div>
      </div>
    </div>
  );
}
