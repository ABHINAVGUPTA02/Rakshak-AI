import { type FormEvent, useEffect, useRef, useState } from 'react';
import { api, type CrimeRecord } from '../api/client';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

interface UploadResult {
  type: string;
  records_ingested?: number;
  records_skipped?: number;
  extraction_method?: string;
  characters_extracted?: number;
  text_preview?: string;
  parsed_fields?: Record<string, string | number | null>;
  warnings?: string[];
  message?: string;
  success?: boolean;
  graph_synced?: boolean;
  record?: { fir_number: string; crime_type: string; district: string };
}

function formatUploadMessage(data: UploadResult): string {
  if (data.type === 'unsupported') {
    return data.message || 'Unsupported file type';
  }

  const ingested = data.records_ingested ?? 0;
  const parts: string[] = [];

  if (data.type === 'document') {
    parts.push(`Extracted via ${data.extraction_method || 'unknown'} (${data.characters_extracted ?? 0} chars)`);
    parts.push(`Ingested ${ingested} FIR record(s)`);
    if (data.record) {
      parts.push(`Saved: ${data.record.fir_number} — ${data.record.crime_type}, ${data.record.district}`);
    }
  } else {
    parts.push(`Ingested ${ingested} record(s)`);
    if (data.records_skipped) {
      parts.push(`${data.records_skipped} skipped (duplicate or missing FIR number)`);
    }
  }

  if (data.warnings?.length) {
    parts.push(`Note: ${data.warnings.join(' ')}`);
  }

  return parts.join('. ');
}

export default function CrimeRecords() {
  const [records, setRecords] = useState<CrimeRecord[]>([]);
  const [error, setError] = useState('');
  const [uploadMsg, setUploadMsg] = useState('');
  const [uploadOk, setUploadOk] = useState<boolean | null>(null);
  const [uploadDetail, setUploadDetail] = useState('');
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
    setUploadMsg('Processing...');
    setUploadDetail('');
    setUploadOk(null);
    setError('');

    try {
      const res = await fetch(`${API_BASE}/ingest/upload`, { method: 'POST', body: form });
      const data: UploadResult = await res.json();
      if (!res.ok) {
        setUploadMsg('Upload failed');
        setUploadOk(false);
        setError(data.message || 'Server rejected the upload');
        return;
      }
      const ingested = data.records_ingested ?? 0;
      setUploadOk(data.success ?? ingested > 0);
      setUploadMsg(formatUploadMessage(data));
      if (data.text_preview) {
        setUploadDetail(data.text_preview);
      }
      loadRecords();
      if (fileRef.current) fileRef.current.value = '';
    } catch {
      setUploadMsg('Upload failed — is the backend running?');
      setUploadOk(false);
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
          <p>Upload FIRs as CSV, Excel, PDF, or scanned images (OCR supported)</p>
        </div>
        <form onSubmit={handleUpload} className="upload-form">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls,.pdf,.jpg,.jpeg,.png,.tiff,.webp"
          />
          <button type="submit">Upload</button>
        </form>
      </header>

      {error && <div className="alert">{error}</div>}
      {uploadMsg && (
        <div className={`alert ${uploadOk ? 'success' : 'warning'}`}>{uploadMsg}</div>
      )}
      {uploadDetail && (
        <div className="panel ocr-preview">
          <h3>Extracted Text Preview</h3>
          <pre>{uploadDetail}</pre>
        </div>
      )}

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
