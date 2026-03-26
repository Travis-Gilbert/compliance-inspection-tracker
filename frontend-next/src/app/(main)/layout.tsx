"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "@/lib/constants";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <nav className="w-full md:w-56 bg-white border-b md:border-b-0 md:border-r border-gray-200 flex-shrink-0">
        <div className="p-4 border-b border-gray-100">
          <h1 className="font-heading text-lg font-bold text-gray-900 leading-tight">
            Compliance Tracker
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Genesee County Land Bank
          </p>
        </div>

        <div className="flex md:flex-col overflow-x-auto md:overflow-visible p-2 gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive = item.path === "/" ? pathname === "/" : pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                  isActive
                    ? "bg-civic-green-pale text-civic-green"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <span className="inline-flex h-6 min-w-6 items-center justify-center rounded bg-gray-100 px-1 text-[10px] font-semibold tracking-wide text-gray-500">
                  {item.shortLabel}
                </span>
                {item.label}
              </Link>
            );
          })}
        </div>

        <div className="hidden md:block mt-auto p-4 border-t border-gray-100">
          <div className="text-xs text-gray-400">
            Local desk-research tool. Data stays in this tracker.
          </div>
        </div>
      </nav>

      <main className="flex-1 min-w-0">
        <div className="max-w-5xl mx-auto p-4 md:p-6">
          {children}
        </div>
      </main>
    </div>
  );
}
