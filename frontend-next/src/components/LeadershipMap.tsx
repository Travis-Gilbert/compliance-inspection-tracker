"use client";

import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, TileLayer, useMap } from "react-leaflet";
import Link from "next/link";
import "leaflet/dist/leaflet.css";
import { getImageUrl, getMapProperties, fetchHistoricalImagery } from "@/lib/api";
import { PROGRAMS } from "@/lib/constants";

const MAP_CENTER: [number, number] = [43.011, -83.687];
const MAP_ZOOM = 12;
const PROGRAM_COLORS: Record<string, string> = {
  "Featured Homes": "#2E7D32",
  "Ready for Rehab": "#1565C0",
  "VIP Spotlight": "#7C4D1F",
  Demolition: "#B71C1C",
};

function FlyToSelected({ property }: { property: any }) {
  const map = useMap();
  useEffect(() => {
    if (!property?.latitude || !property?.longitude) return;
    map.flyTo([Number(property.latitude), Number(property.longitude)], 16, { duration: 0.5 });
  }, [map, property]);
  return null;
}

function escapeCsv(value: any): string {
  const text = value == null ? "" : String(value);
  if (!text.includes(",") && !text.includes("\"") && !text.includes("\n")) {
    return text;
  }
  return `"${text.replace(/"/g, "\"\"")}"`;
}

function exportFilteredCsv(rows: any[]) {
  const headers = [
    "Address",
    "Parcel ID",
    "Buyer Name",
    "Organization",
    "Email",
    "Program",
    "Closing Date",
    "Purchase Type",
    "Compliance 1st Attempt",
    "Compliance 2nd Attempt",
    "Priority Score",
    "Priority Level",
    "Finding",
    "Detection Label",
  ];
  const lines = rows.map((row) =>
    [
      row.address,
      row.parcel_id,
      row.buyer_name,
      row.organization,
      row.email,
      row.program,
      row.closing_date,
      row.purchase_type,
      row.compliance_1st_attempt,
      row.compliance_2nd_attempt,
      row.priority_score,
      row.priority_level,
      row.finding,
      row.detection_label,
    ].map(escapeCsv).join(",")
  );

  const content = [headers.join(","), ...lines].join("\n");
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `compliance-map-filter-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function ImagePanel({
  src,
  label,
  fallback,
  loading = false,
}: {
  src: string;
  label: string;
  fallback: string;
  loading?: boolean;
}) {
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    setErrored(false);
  }, [src]);

  if (loading) {
    return (
      <div className="w-full aspect-[4/3] bg-gray-100 rounded border border-gray-200 flex items-center justify-center text-xs text-gray-500">
        Loading image...
      </div>
    );
  }

  return (
    <div className="w-full aspect-[4/3] bg-gray-100 rounded border border-gray-200 overflow-hidden">
      {src && !errored ? (
        <div className="h-full flex flex-col">
          <img
            src={src}
            alt={label}
            className="w-full h-full object-cover"
            onError={() => setErrored(true)}
          />
          <div className="text-[11px] text-gray-600 px-2 py-1 border-t border-gray-200 bg-white">
            {label}
          </div>
        </div>
      ) : (
        <div className="h-full flex items-center justify-center text-xs text-gray-500">
          {fallback}
        </div>
      )}
    </div>
  );
}

export default function LeadershipMap() {
  const [properties, setProperties] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [programFilter, setProgramFilter] = useState("all");
  const [contactFilter, setContactFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [historicalState, setHistoricalState] = useState<Record<number, any>>({});
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" ? window.innerWidth < 640 : false
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 639px)");
    const handleChange = () => setIsMobile(mediaQuery.matches);

    handleChange();
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener("change", handleChange);
      return () => mediaQuery.removeEventListener("change", handleChange);
    }

    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  const loadMap = async () => {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {};
      if (programFilter !== "all") params.program = programFilter;
      if (contactFilter !== "all") params.contact = contactFilter;
      const response = await getMapProperties(params);
      const rows = response.properties || [];
      setProperties(rows);
      setSelectedId((current) => {
        if (rows.length === 0) {
          return null;
        }
        if (current && rows.some((row: any) => row.id === current)) {
          return current;
        }
        return isMobile ? null : rows[0].id;
      });
    } catch (err: any) {
      setError(err.message || "Failed to load map data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programFilter, contactFilter, isMobile]);

  const selectedProperty = useMemo(
    () => properties.find((row) => row.id === selectedId) || null,
    [properties, selectedId]
  );

  useEffect(() => {
    if (!selectedProperty) return;
    const currentStatus = historicalState[selectedProperty.id]?.status;
    if (selectedProperty.streetview_historical_path) return;
    if (currentStatus === "loading" || currentStatus === "ready" || currentStatus === "unavailable") {
      return;
    }
    if (!selectedProperty.closing_date) {
      setHistoricalState((prev) => ({
        ...prev,
        [selectedProperty.id]: { status: "unavailable" },
      }));
      return;
    }

    let cancelled = false;
    setHistoricalState((prev) => ({
      ...prev,
      [selectedProperty.id]: { status: "loading" },
    }));

    fetchHistoricalImagery(selectedProperty.id)
      .then((result: any) => {
        if (cancelled) return;
        setHistoricalState((prev) => ({
          ...prev,
          [selectedProperty.id]: {
            status: result.historical_available ? "ready" : "unavailable",
            date: result.actual_date || result.target_date || "",
          },
        }));
        if (result.historical_available) {
          setProperties((prev) =>
            prev.map((row) =>
              row.id === selectedProperty.id
                ? {
                    ...row,
                    streetview_historical_path: result.streetview_historical_path || row.streetview_historical_path,
                    streetview_historical_date: result.actual_date || row.streetview_historical_date,
                  }
                : row
            )
          );
        }
      })
      .catch(() => {
        if (cancelled) return;
        setHistoricalState((prev) => ({
          ...prev,
          [selectedProperty.id]: { status: "unavailable" },
        }));
      });

    return () => {
      cancelled = true;
    };
  }, [
    selectedProperty?.id,
    selectedProperty?.streetview_historical_path,
    selectedProperty?.closing_date,
    historicalState,
  ]);

  const stats = useMemo(() => {
    const total = properties.length;
    const noContact = properties.filter((row) => !row.has_contact_attempt).length;
    const highPriority = properties.filter((row) => row.priority_level === "high").length;
    return { total, noContact, highPriority };
  }, [properties]);

  return (
    <div className="fixed inset-0 bg-warm-50">
      <div className="absolute top-0 left-0 right-0 z-[1000] bg-white/95 border-b border-gray-200 backdrop-blur-sm">
        <div className="px-4 py-3 flex flex-wrap items-start gap-3">
          <div>
            <h2 className="font-heading text-base font-bold text-gray-900">Compliance Map</h2>
            <p className="text-xs text-gray-500">Leadership view for geocoded properties</p>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
            <span>Total: <strong className="text-gray-900">{stats.total}</strong></span>
            <span>High priority: <strong className="text-red-700">{stats.highPriority}</strong></span>
            <span>No outreach: <strong className="text-orange-700">{stats.noContact}</strong></span>
          </div>

          <div className="flex w-full flex-wrap items-center gap-2 sm:ml-auto sm:w-auto">
            <Link
              href="/review"
              className="text-xs font-medium px-3 py-1.5 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
            >
              Review Queue
            </Link>

            <select
              value={programFilter}
              onChange={(event) => setProgramFilter(event.target.value)}
              className="text-xs border border-gray-300 rounded px-2 py-1.5 bg-white"
            >
              <option value="all">All programs</option>
              {PROGRAMS.map((program) => (
                <option key={program} value={program}>{program}</option>
              ))}
            </select>

            <select
              value={contactFilter}
              onChange={(event) => setContactFilter(event.target.value)}
              className="text-xs border border-gray-300 rounded px-2 py-1.5 bg-white"
            >
              <option value="all">All contact statuses</option>
              <option value="no_contact">No outreach attempts</option>
              <option value="contacted">At least one outreach attempt</option>
            </select>

            <button
              onClick={() => exportFilteredCsv(properties)}
              disabled={properties.length === 0}
              className={`text-xs font-medium px-3 py-1.5 rounded border ${
                properties.length === 0
                  ? "border-gray-200 text-gray-400 bg-gray-100 cursor-not-allowed"
                  : "border-civic-green bg-civic-green text-white hover:bg-civic-green-light"
              }`}
            >
              Export Current View
            </button>
          </div>
        </div>
      </div>

      <div className="absolute inset-0 pt-[124px] sm:pt-[74px]">
        <MapContainer center={MAP_CENTER} zoom={MAP_ZOOM} className="w-full h-full" zoomControl>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <FlyToSelected property={selectedProperty} />
          {properties.map((property) => {
            if (property.latitude == null || property.longitude == null) return null;
            const color = PROGRAM_COLORS[property.program] || "#455A64";
            const isSelected = selectedId === property.id;
            return (
              <CircleMarker
                key={property.id}
                center={[Number(property.latitude), Number(property.longitude)]}
                radius={isSelected ? 9 : 6}
                pathOptions={{
                  fillColor: color,
                  color: isSelected ? "#FFFFFF" : color,
                  fillOpacity: property.has_contact_attempt ? 0.85 : 0.45,
                  weight: isSelected ? 2.5 : 1,
                }}
                eventHandlers={{ click: () => setSelectedId(property.id) }}
              />
            );
          })}
        </MapContainer>
      </div>

      {loading && (
        <div className="absolute left-4 top-[134px] z-[1000] rounded border border-gray-200 bg-white px-3 py-2 text-xs text-gray-600 sm:top-[84px]">
          Loading map data...
        </div>
      )}

      {error && (
        <div className="absolute left-4 top-[134px] z-[1000] rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 sm:top-[84px]">
          {error}
        </div>
      )}

      {!loading && !error && properties.length === 0 && (
        <div className="absolute left-4 top-[134px] z-[1000] rounded border border-gray-200 bg-white px-3 py-2 text-xs text-gray-600 sm:top-[84px]">
          No geocoded properties match this view.
        </div>
      )}

      <div className="absolute bottom-4 left-4 z-[1000] bg-white border border-gray-200 rounded px-3 py-2 text-[11px] text-gray-600">
        Marker colors: Featured Homes (green), Ready for Rehab (blue), VIP Spotlight (brown), Demolition (red)
      </div>

      {selectedProperty && (
        <aside
          className={`absolute z-[1100] overflow-y-auto bg-white shadow-xl ${
            isMobile
              ? "bottom-0 left-0 right-0 h-[78vh] rounded-t-2xl border-t border-gray-200"
              : "bottom-0 right-0 top-[74px] w-[430px] border-l border-gray-200"
          }`}
        >
          <div className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 flex items-start justify-between gap-3">
            <div>
              <h3 className="font-heading text-lg font-bold text-gray-900 leading-tight">
                {selectedProperty.address}
              </h3>
              <p className="text-xs text-gray-500 mt-1">Parcel: {selectedProperty.parcel_id || "Not listed"}</p>
            </div>
            <button
              onClick={() => setSelectedId(null)}
              className="text-xs text-gray-600 border border-gray-300 rounded px-2 py-1 hover:bg-gray-50"
            >
              Close
            </button>
          </div>

          <div className="p-4 space-y-4">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-gray-50 border border-gray-200 rounded p-2">
                <div className="text-gray-400 uppercase tracking-wide text-[10px]">Buyer</div>
                <div className="text-gray-800 font-medium mt-1">{selectedProperty.buyer_name || "Not listed"}</div>
              </div>
              <div className="bg-gray-50 border border-gray-200 rounded p-2">
                <div className="text-gray-400 uppercase tracking-wide text-[10px]">Program</div>
                <div className="text-gray-800 font-medium mt-1">{selectedProperty.program || "Not listed"}</div>
              </div>
              <div className="bg-gray-50 border border-gray-200 rounded p-2">
                <div className="text-gray-400 uppercase tracking-wide text-[10px]">Organization</div>
                <div className="text-gray-800 font-medium mt-1">{selectedProperty.organization || "Not listed"}</div>
              </div>
              <div className="bg-gray-50 border border-gray-200 rounded p-2">
                <div className="text-gray-400 uppercase tracking-wide text-[10px]">Email</div>
                <div className="text-gray-800 font-medium mt-1">{selectedProperty.email || "Not listed"}</div>
              </div>
              <div className="bg-gray-50 border border-gray-200 rounded p-2">
                <div className="text-gray-400 uppercase tracking-wide text-[10px]">Closing Date</div>
                <div className="text-gray-800 font-medium mt-1">{selectedProperty.closing_date || "Not listed"}</div>
              </div>
              <div className="bg-gray-50 border border-gray-200 rounded p-2">
                <div className="text-gray-400 uppercase tracking-wide text-[10px]">Purchase Type</div>
                <div className="text-gray-800 font-medium mt-1">{selectedProperty.purchase_type || "Not listed"}</div>
              </div>
            </div>

            <div className="bg-gray-50 border border-gray-200 rounded p-3 text-xs">
              <div className="text-gray-500 uppercase tracking-wide text-[10px] mb-2">Compliance Outreach</div>
              <div className="space-y-1 text-gray-700">
                <div>1st attempt: {selectedProperty.compliance_1st_attempt || "Not sent"}</div>
                <div>2nd attempt: {selectedProperty.compliance_2nd_attempt || "Not sent"}</div>
              </div>
            </div>

            <div className="bg-gray-50 border border-gray-200 rounded p-3 text-xs">
              <div className="text-gray-500 uppercase tracking-wide text-[10px] mb-2">Priority</div>
              <div className="flex items-center justify-between">
                <span className="text-gray-700">Score</span>
                <strong className="text-gray-900">{selectedProperty.priority_score}</strong>
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-gray-700">Level</span>
                <strong className="uppercase text-gray-900">{selectedProperty.priority_level}</strong>
              </div>
            </div>

            <div>
              <h4 className="font-heading text-sm font-semibold text-gray-900 mb-2">Before and After</h4>
              <div className="grid grid-cols-2 gap-2">
                <ImagePanel
                  src={selectedProperty.streetview_historical_path ? getImageUrl(selectedProperty.id, "streetview_historical") : ""}
                  label={`Historical ${selectedProperty.streetview_historical_date || ""}`.trim()}
                  fallback="Historical Street View unavailable"
                  loading={historicalState[selectedProperty.id]?.status === "loading"}
                />
                <ImagePanel
                  src={selectedProperty.streetview_available ? getImageUrl(selectedProperty.id, "streetview") : ""}
                  label={`Current ${selectedProperty.streetview_date || ""}`.trim()}
                  fallback="Current Street View unavailable"
                />
              </div>
              <div className="mt-2">
                <ImagePanel
                  src={selectedProperty.satellite_path ? getImageUrl(selectedProperty.id, "satellite") : ""}
                  label="Satellite"
                  fallback="Satellite imagery unavailable"
                />
              </div>
            </div>

            {selectedProperty.notes && (
              <div className="bg-gray-50 border border-gray-200 rounded p-3 text-xs text-gray-700">
                <div className="text-gray-500 uppercase tracking-wide text-[10px] mb-2">Notes</div>
                {selectedProperty.notes}
              </div>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
