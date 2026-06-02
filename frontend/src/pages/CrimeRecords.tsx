import { type FormEvent, useEffect, useRef, useState } from 'react';
import { api, type CrimeRecord } from '../api/client';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

export default function CrimeRecords() {
  const [records, setRecords] = useState<CrimeRecord[]>([]);
  const [error, setError] = useState('');
  const [uploadMsg, setUploadMsg] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [summary, setSummary] = useState<{ summary: string; repeat_offenders: { name: string; case_count: number }[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function loadRecords() {
    api.getCrimes()
      .then(setRecords)
      .catch(() => setError('Unable to load crime records.'));
  }

  useEffect(() => {
    loadRecords();
  }, []);

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    const form = new FormData();
    form.append('file', file);
    setUploadMsg('Uploading...');

    try {
      const res = await fetch(`${API_BASE}/ingest/upload`, { method: 'POST', body: form });
      const data = await res.json();
      setUploadMsg(`Ingested ${data.records_ingested ?? 0} records`);
      loadRecords();
    } catch {
      setUploadMsg('Upload failed');
    }
  }

  async function showSummary(id: number) {
    setSelected(id);
    try {
      const res = await fetch(`${API_BASE}/crimes/${id}/summary`);
      setSummary(await res.json());
    } catch {
      setSummary(null);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Crime Records</h2>
          <p>FIR database — searchable crime intelligence records</p>
        </div>
        <form onSubmit={handleUpload} className="upload-form">
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.pdf" />
          <button type="submit">Upload</button>
        </form>
      </header>

      {error && <div className="alert">{error}</div>}
      {uploadMsg && <div className="alert success">{uploadMsg}</div>}

      <div className="records-layout">
        <div className="panel table-panel">
          <table>
            <thead>
              <tr>
                <th>FIR Number</th>
                <th>Type</th>
                <th>District</th>
                <th>Police Station</th>
                <th>Status</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr
                  key={record.id}
                  className={selected === record.id ? 'selected' : ''}
                  onClick={() => showSummary(record.id)}
                >
                  <td className="mono">{record.fir_number}</td>
                  <td>{record.crime_type}</td>
                  <td>{record.district}</td>
                  <td>{record.police_station || '—'}</td>
                  <td>
                    <span className={`status-pill ${record.status}`}>{record.status}</span>
                  </td>
                  <td>{record.incident_date || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {records.length === 0 && !error && <p className="empty-state">No records found.</p>}
        </div>

        {summary && (
          <div className="panel summary-panel">
            <h3>Case Summary</h3>
            <p>{summary.summary}</p>
            {summary.repeat_offenders.length > 0 && (
              <div className="evidence-trail">
                <strong>Repeat Offender Alert</strong>
                <ul>
                  {summary.repeat_offenders.map((o) => (
                    <li key={o.name}>
                      {o.name} — linked to {o.case_count} cases
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
