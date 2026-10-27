import { useState } from "react";
import {
  Activity,
  Blocks,
  ChevronDown,
  Code2,
  CreditCard,
  LayoutDashboard,
  Menu,
  ShieldCheck,
  X,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

interface AppShellProps {
  onLogout?: () => void;
}

const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/payments", label: "Payments", icon: CreditCard },
  { to: "/requests", label: "Request inspector", icon: Activity },
  { to: "/explorer", label: "API Explorer", icon: Code2 },
];

export function AppShell({ onLogout }: AppShellProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const queryClient = useQueryClient();

  return (
    <div className="app-shell">
      {menuOpen && (
        <button
          className="mobile-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside className={`sidebar ${menuOpen ? "sidebar--open" : ""}`}>
        <div className="brand">
          <div className="brand__mark">
            <ShieldCheck size={21} strokeWidth={2.2} />
          </div>
          <span>
            vitt<span className="brand__light">guard</span>
          </span>
          <button
            className="icon-button sidebar__close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          >
            <X size={19} />
          </button>
        </div>
        <div className="workspace-switcher">
          <div className="workspace-switcher__avatar">VG</div>
          <div>
            <strong>Vitt Guard</strong>
            <span>Development workspace</span>
          </div>
          <ChevronDown size={15} aria-hidden="true" />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation" className="main-nav">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              className={({ isActive }) =>
                `nav-link${isActive ? " nav-link--active" : ""}`
              }
              end={end}
              key={to}
              to={to}
              onClick={() => setMenuOpen(false)}
            >
              <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
              <span>{label}</span>
              {label === "API Explorer" && <span className="nav-link__dot" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__bottom">
          <div className="sidebar-note">
            <div className="sidebar-note__icon">
              <Blocks size={17} />
            </div>
            <strong>Simulation mode</strong>
            <p>Payments are recorded for development only. No money moves.</p>
          </div>
          <div className="profile">
            <div className="profile__avatar">D</div>
            <div className="profile__text">
              <strong>Developer</strong>
              <span>Local environment</span>
            </div>
            <span className="online-dot" title="Local environment" />
          </div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            type="button"
            aria-label="Open navigation"
            onClick={() => setMenuOpen(true)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb__slash">/</span>
            <strong>Developer dashboard</strong>
          </div>
          <div className="topbar__right">
            <span className="environment-pill">
              <i /> {onLogout ? "Protected demo" : "Local development"}
            </span>
            {onLogout && (
              <button
                className="topbar__refresh"
                onClick={onLogout}
                type="button"
              >
                Sign out
              </button>
            )}
            <button
              className="topbar__refresh"
              type="button"
              onClick={() => void queryClient.invalidateQueries()}
              title="Refresh dashboard data"
            >
              <Activity size={17} />
            </button>
          </div>
        </header>
        <main className="page-content">
          <Outlet />
          <footer className="page-footer">
            <span>Vitt Guard · Simulated payment environment</span>
            <span>Built for developers</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
