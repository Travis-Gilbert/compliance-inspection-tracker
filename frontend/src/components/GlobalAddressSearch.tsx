"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { searchProperties } from "@/lib/api";
import type { Property } from "@/lib/types";

export default function GlobalAddressSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Property[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      searchProperties(term)
        .then((response) => {
          if (cancelled) return;
          setResults(response.results || []);
          setOpen(true);
        })
        .catch(() => {
          if (cancelled) return;
          setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 160);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  const openProperty = (property: Property) => {
    setOpen(false);
    setQuery("");
    if (pathname.startsWith("/before-after")) {
      router.push(`/before-after?selected=${property.id}`);
      return;
    }
    router.push(`/property/${property.id}`);
  };

  return (
    <div ref={wrapperRef} className="relative">
      <label htmlFor="global-address-search" className="sr-only">
        Search address, parcel, buyer, or organization
      </label>
      <input
        id="global-address-search"
        name="global-address-search"
        autoComplete="off"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => query.trim().length >= 2 && setOpen(true)}
        placeholder="Search address…"
        className="w-full rounded border border-gray-300 bg-warm-50 px-3 py-2 text-sm text-gray-900 outline-none transition-colors placeholder:text-gray-400 focus-visible:border-civic-green focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-civic-green/20"
      />
      {open && (query.trim().length >= 2 || loading) && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded border border-gray-200 bg-white shadow-lg">
          {loading ? (
            <div className="px-3 py-3 text-sm text-gray-500" role="status" aria-live="polite">Searching…</div>
          ) : results.length === 0 ? (
            <div className="px-3 py-3 text-sm text-gray-500" role="status" aria-live="polite">No matching properties</div>
          ) : (
            <ul role="listbox" aria-label="Search results" className="max-h-80 overflow-y-auto">
              {results.map((property) => (
                <li key={property.id} role="option" aria-selected="false">
                  <button
                    type="button"
                    onClick={() => openProperty(property)}
                    className="block w-full px-3 py-2 text-left text-sm transition-colors hover:bg-civic-green-pale focus:bg-civic-green-pale focus:outline-none"
                  >
                    <span className="block font-medium text-gray-900">{property.address}</span>
                    <span className="mt-0.5 block text-xs text-gray-500">
                      {[property.parcel_id, property.buyer_name, property.organization]
                        .filter(Boolean)
                        .join(" | ") || "Property record"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
