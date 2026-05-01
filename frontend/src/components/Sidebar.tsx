"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import GlobalAddressSearch from "@/components/GlobalAddressSearch";

const NAV_GROUPS = [
  {
    label: "Work",
    items: [
      {
        path: "/",
        label: "Dashboard",
        icon: (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="1.5" y="1.5" width="5" height="5" rx="1" />
            <rect x="9.5" y="1.5" width="5" height="5" rx="1" />
            <rect x="1.5" y="9.5" width="5" height="5" rx="1" />
            <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
          </svg>
        ),
      },
      {
        path: "/review",
        label: "Review Queue",
        icon: (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 4h12M2 8h12M2 12h8" />
            <path d="M12 11l1.5 1.5L15 11" />
          </svg>
        ),
      },
      {
        path: "/map",
        label: "Compliance Map",
        icon: (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 1.5C5.5 1.5 3.5 3.5 3.5 6c0 3.5 4.5 8.5 4.5 8.5s4.5-5 4.5-8.5c0-2.5-2-4.5-4.5-4.5z" />
            <circle cx="8" cy="6" r="1.5" />
          </svg>
        ),
      },
      {
        path: "/before-after",
        label: "Before and After",
        icon: (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="1.5" y="3" width="5.5" height="10" rx="1" />
            <rect x="9" y="3" width="5.5" height="10" rx="1" />
            <path d="M4.25 6.5h.01M11.75 6.5h.01M3 10h2.5M10.5 10H13" />
          </svg>
        ),
      },
    ],
  },
  {
    label: "Data",
    items: [
      {
        path: "/import",
        label: "Import",
        icon: (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 2v8M5 7l3 3 3-3" />
            <path d="M2 11v2a1 1 0 001 1h10a1 1 0 001-1v-2" />
          </svg>
        ),
      },
      {
        path: "/export",
        label: "Export",
        icon: (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 10V2M5 5l3-3 3 3" />
            <path d="M2 11v2a1 1 0 001 1h10a1 1 0 001-1v-2" />
          </svg>
        ),
      },
      {
        path: "/processing",
        label: "Processing",
        icon: (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="8" cy="8" r="3" />
            <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
          </svg>
        ),
      },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav aria-label="Main navigation" className="w-full md:w-56 bg-white border-b md:border-b-0 md:border-r border-gray-200 flex-shrink-0">
      <div className="p-4 border-b border-gray-100">
        <h1 className="font-heading text-lg font-bold text-gray-900 leading-tight">
          Compliance Tracker
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Genesee County Land Bank
        </p>
        <div className="mt-3">
          <GlobalAddressSearch />
        </div>
      </div>

      {/* Desktop: vertical nav with groups */}
      <div className="hidden md:block p-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="text-[10px] uppercase tracking-widest text-gray-400 px-3 mb-1 mt-2 pt-2 border-t border-gray-100 first:border-t-0 first:mt-0 first:pt-0">
              {group.label}
            </div>
            <div className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const isActive = item.path === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.path);
                return (
                  <Link
                    key={item.path}
                    href={item.path}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-green focus-visible:ring-offset-2 ${
                      isActive
                        ? "bg-civic-green-pale text-civic-green ring-1 ring-civic-green/20"
                        : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                    }`}
                  >
                    <span className="shrink-0 opacity-70" aria-hidden="true">{item.icon}</span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Mobile: horizontal scroll nav */}
      <div className="flex md:hidden overflow-x-auto p-2 gap-1">
        {NAV_GROUPS.flatMap((group) => group.items).map((item) => {
          const isActive = item.path === "/"
            ? pathname === "/"
            : pathname.startsWith(item.path);
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-green focus-visible:ring-offset-2 ${
                isActive
                  ? "bg-civic-green-pale text-civic-green"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              }`}
            >
              <span className="shrink-0 opacity-70" aria-hidden="true">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </div>

      <div className="hidden md:block mt-auto p-4 border-t border-gray-100">
        <div className="text-[10px] text-gray-300">v2.0.0</div>
      </div>
    </nav>
  );
}
