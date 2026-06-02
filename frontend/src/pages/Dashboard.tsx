import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, type CrimeStats } from '../api/client';

export default function Dashboard() {
  const [stats, setStats] = useState<CrimeStats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch(() => setError('Unable to connect to API. Start the backend server.'));
  }, []);

  const typeData = stats
    ? Object.entries(stats.by_type).map(([name, value]) => ({ name, value }))
    : [];

  const districtData = stats
    ? Object.entries(stats.by_district).map(([name, value]) => ({ name, value }))
    : [];

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Intelligence Dashboard</h2>
          <p>Real-time crime analytics and investigative overview</p>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Total Crimes</span>
          <span className="stat-value">{stats?.total_crimes ?? '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Open Cases</span>
          <span className="stat-value accent">{stats?.open_cases ?? '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Districts</span>
          <span className="stat-value">{stats ? Object.keys(stats.by_district).length : '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Crime Types</span>
          <span className="stat-value">{stats ? Object.keys(stats.by_type).length : '—'}</span>
        </div>
      </div>

      <div className="chart-grid">
        <div className="panel">
          <h3>Crimes by Type</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={typeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
              <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="panel">
          <h3>Crimes by District</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={districtData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#94a3b8" fontSize={11} angle={-20} textAnchor="end" height={60} />
              <YAxis stroke="#94a3b8" fontSize={12} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
              <Bar dataKey="value" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
