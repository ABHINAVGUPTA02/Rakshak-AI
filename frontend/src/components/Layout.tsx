import { NavLink, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/chat', label: 'Intelligence Chat', icon: '🗣️' },
  { to: '/map', label: 'Crime Map', icon: '🗺️' },
  { to: '/network', label: 'Network Graph', icon: '🕸️' },
  { to: '/records', label: 'Crime Records', icon: '📋' },
];

export default function Layout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">🛡️</span>
          <div>
            <h1>Rakshak AI</h1>
            <p>Crime Intelligence OS</p>
          </div>
        </div>
        <nav>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
