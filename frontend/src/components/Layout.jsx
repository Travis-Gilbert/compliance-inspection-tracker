import { NavLink, Outlet } from "react-router-dom";
import { NAV_ITEMS } from "../utils/constants";

export default function Layout({ children }) {
  const content = children ?? <Outlet />;

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      {/* Sidebar */}
      <nav className="w-full md:w-56 bg-white border-b md:border-b-0 md:border-r border-gray-200 flex-shrink-0">
        {/* Header */}
        <div className="p-4 border-b border-gray-100">
          <h1 className="font-heading text-lg font-bold text-gray-900 leading-tight">
            Compliance Tracker
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Genesee County Land Bank
          </p>
        </div>

        {/* Nav links */}
        <div className="flex md:flex-col overflow-x-auto md:overflow-visible p-2 gap-1">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? "bg-civic-green-pale text-civic-green"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`
              }
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </div>

        {/* API status indicator */}
        <div className="hidden md:block mt-auto p-4 border-t border-gray-100">
          <div className="text-xs text-gray-400">
            Local tool. No database connection.
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 min-w-0">
        <div className="max-w-5xl mx-auto p-4 md:p-6">
          {content}
        </div>
      </main>
    </div>
  );
}
