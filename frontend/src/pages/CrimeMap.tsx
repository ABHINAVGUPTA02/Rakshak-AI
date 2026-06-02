import { useEffect, useState } from 'react';
import { api, type Hotspot } from '../api/client';

export default function CrimeMap() {
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getHotspots()
      .then(setHotspots)
      .catch(() => setError('Unable to load hotspot data.'));
  }, []);

  const maxCount = Math.max(...hotspots.map((h) => h.crime_count), 1);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Crime Hotspot Map</h2>
          <p>District-level geospatial crime visualization</p>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <div className="map-layout">
        <div className="panel map-canvas">
          <div className="map-grid">
            {hotspots.map((spot) => {
              const intensity = spot.crime_count / maxCount;
              return (
                <div
                  key={spot.district}
                  className="map-marker"
                  style={{
                    left: `${((spot.longitude - 74.5) / 3.5) * 100}%`,
                    top: `${((13.5 - spot.latitude) / 2.5) * 100}%`,
                    transform: 'translate(-50%, -50%)',
                  }}
                >
                  <div
                    className="marker-dot"
                    style={{
                      width: `${24 + intensity * 40}px`,
                      height: `${24 + intensity * 40}px`,
                      opacity: 0.4 + intensity * 0.6,
                    }}
                  />
                  <span className="marker-label">{spot.district}</span>
                </div>
              );
            })}
          </div>
          <p className="map-note">Karnataka district crime density (sample data)</p>
        </div>

        <div className="panel hotspot-list">
          <h3>Hotspot Rankings</h3>
          <ul>
            {hotspots
              .sort((a, b) => b.crime_count - a.crime_count)
              .map((spot) => (
                <li key={spot.district}>
                  <span>{spot.district}</span>
                  <span className="badge">{spot.crime_count} incidents</span>
                </li>
              ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
