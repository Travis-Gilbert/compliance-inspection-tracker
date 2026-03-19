import { Fragment, useEffect, useMemo, useState } from "react";
import { Circle, CircleMarker, MapContainer, TileLayer, useMap } from "react-leaflet";
import { Link } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import { fetchHistoricalImagery, getImageUrl } from "../utils/api";
import { DETECTION_LABELS, FINDINGS } from "../utils/constants";

const MAP_CENTER = [43.011, -83.687];
const MAP_ZOOM = 11;
const COVERAGE_META = {
  before_after: {
    label: "Before + Current",
    color: "#2E7D32",
    bg: "#E8F5E9",
    description: "Historical and current Street View available.",
  },
  current_only: {
    label: "Current Only",
    color: "#1565C0",
    bg: "#E3F2FD",
    description: "Current Street View available, no historical image cached yet.",
  },
  satellite_only: {
    label: "Satellite Only",
    color: "#F57F17",
    bg: "#FFF8E1",
    description: "Satellite imagery exists, but no current Street View image is available.",
  },
  no_imagery: {
    label: "No Photo Coverage",
    color: "#B71C1C",
    bg: "#FFEBEE",
    description: "Property is geocoded but does not have cached photo coverage yet.",
  },
};

function getCoverageStatus(property, historicalState = {}) {
  const hasHistorical =
    Boolean(property.streetview_historical_path) ||
    historicalState[property.id]?.status === "ready";

  if (property.streetview_available && hasHistorical) {
    return COVERAGE_META.before_after;
  }
  if (property.streetview_available) {
    return COVERAGE_META.current_only;
  }
  if (property.satellite_path) {
    return COVERAGE_META.satellite_only;
  }
  return COVERAGE_META.no_imagery;
}

function FitMapToProperties({ properties }) {
  const map = useMap();

  useEffect(() => {
    const points = properties
      .filter((property) => property.latitude != null && property.longitude != null)
      .map((property) => [Number(property.latitude), Number(property.longitude)]);

    if (points.length === 0) {
      return;
    }

    if (points.length === 1) {
      map.setView(points[0], 15);
      return;
    }

    map.fitBounds(points, {
      padding: [28, 28],
      maxZoom: 15,
    });
  }, [map, properties]);

  return null;
}

function ImagePanel({ src, label, fallback, loading = false }) {
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    setErrored(false);
  }, [src]);

  if (loading) {
    return (
      <div className="flex aspect-[4/3] w-full items-center justify-center rounded border border-gray-200 bg-gray-100 text-xs text-gray-500">
        Loading image...
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded border border-gray-200 bg-gray-100">
      {src && !errored ? (
        <div className="flex h-full flex-col">
          <img
            src={src}
            alt={label}
            className="aspect-[4/3] w-full object-cover"
            onError={() => setErrored(true)}
          />
          <div className="border-t border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600">
            {label}
          </div>
        </div>
      ) : (
        <div className="flex aspect-[4/3] w-full items-center justify-center px-4 text-center text-xs text-gray-500">
          {fallback}
        </div>
      )}
    </div>
  );
}

export default function ManagementCoverageMap({
  properties,
  totalProperties,
  loading,
  error,
}) {
  const [activeId, setActiveId] = useState(null);
  const [historicalState, setHistoricalState] = useState({});

  const activeProperty = useMemo(
    () => properties.find((property) => property.id === activeId) || null,
    [activeId, properties]
  );

  useEffect(() => {
    if (properties.length === 0) {
      setActiveId(null);
      return;
    }

    setActiveId((current) => {
      if (current && properties.some((property) => property.id === current)) {
        return current;
      }

      const gapProperty = properties.find(
        (property) => getCoverageStatus(property, historicalState) !== COVERAGE_META.before_after
      );
      return gapProperty?.id || properties[0].id;
    });
  }, [historicalState, properties]);

  useEffect(() => {
    if (!activeProperty) {
      return;
    }

    if (activeProperty.streetview_historical_path) {
      return;
    }

    const currentStatus = historicalState[activeProperty.id]?.status;
    if (currentStatus === "loading" || currentStatus === "ready" || currentStatus === "unavailable") {
      return;
    }

    if (!activeProperty.closing_date) {
      setHistoricalState((prev) => ({
        ...prev,
        [activeProperty.id]: { status: "unavailable" },
      }));
      return;
    }

    let cancelled = false;
    setHistoricalState((prev) => ({
      ...prev,
      [activeProperty.id]: { status: "loading" },
    }));

    fetchHistoricalImagery(activeProperty.id)
      .then((result) => {
        if (cancelled) {
          return;
        }

        setHistoricalState((prev) => ({
          ...prev,
          [activeProperty.id]: {
            status: result.historical_available ? "ready" : "unavailable",
            date: result.actual_date || result.target_date || "",
          },
        }));
      })
      .catch(() => {
        if (cancelled) {
          return;
        }

        setHistoricalState((prev) => ({
          ...prev,
          [activeProperty.id]: { status: "unavailable" },
        }));
      });

    return () => {
      cancelled = true;
    };
  }, [activeProperty, historicalState]);

  const coverageSummary = useMemo(() => {
    const summary = {
      geocoded: properties.length,
      before_after: 0,
      current_only: 0,
      satellite_only: 0,
      no_imagery: 0,
      reviewed: properties.filter((property) => property.finding).length,
      unreviewed: properties.filter((property) => !property.finding).length,
    };

    for (const property of properties) {
      const status = getCoverageStatus(property, historicalState);
      if (status === COVERAGE_META.before_after) {
        summary.before_after += 1;
      } else if (status === COVERAGE_META.current_only) {
        summary.current_only += 1;
      } else if (status === COVERAGE_META.satellite_only) {
        summary.satellite_only += 1;
      } else {
        summary.no_imagery += 1;
      }
    }

    summary.ungeocoded = Math.max(0, totalProperties - summary.geocoded);
    summary.covered = summary.before_after + summary.current_only + summary.satellite_only;
    return summary;
  }, [historicalState, properties, totalProperties]);

  const coverageRate = totalProperties > 0
    ? Math.round((coverageSummary.covered / totalProperties) * 100)
    : 0;
  const reviewRate = totalProperties > 0
    ? Math.round((coverageSummary.reviewed / totalProperties) * 100)
    : 0;
  const activeCoverage = activeProperty ? getCoverageStatus(activeProperty, historicalState) : null;
  const activeFinding = activeProperty
    ? FINDINGS.find((finding) => finding.value === activeProperty.finding)
    : null;
  const activeDetection = activeProperty
    ? DETECTION_LABELS[activeProperty.detection_label]
    : null;

  return (
    <section className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-heading text-lg font-semibold text-gray-900">
              County Photo Coverage
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              Hover or click a property to inspect current coverage and compare historical versus current imagery.
            </p>
          </div>

          <div className="flex flex-wrap gap-2 text-xs">
            <Link
              to="/map"
              className="rounded border border-gray-200 px-3 py-1.5 font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              Open Full Map
            </Link>
            <Link
              to="/review"
              className="rounded border border-civic-green bg-civic-green px-3 py-1.5 font-medium text-white transition-colors hover:bg-civic-green-light"
            >
              Open Review Queue
            </Link>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          {[
            { label: "Covered", value: `${coverageRate}%`, detail: `${coverageSummary.covered} of ${totalProperties}` },
            { label: "Before + Current", value: coverageSummary.before_after, detail: "Full photo comparison ready" },
            { label: "Current Only", value: coverageSummary.current_only, detail: "Current Street View only" },
            { label: "Satellite Only", value: coverageSummary.satellite_only, detail: "No Street View image yet" },
            { label: "Not Geocoded", value: coverageSummary.ungeocoded, detail: "Not represented on the county map" },
            { label: "Reviewed", value: `${reviewRate}%`, detail: `${coverageSummary.reviewed} of ${totalProperties}` },
          ].map((card) => (
            <div key={card.label} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-3">
              <div className="text-[11px] uppercase tracking-wide text-gray-500">{card.label}</div>
              <div className="mt-1 font-heading text-2xl font-bold text-gray-900">{card.value}</div>
              <div className="mt-1 text-xs text-gray-500">{card.detail}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1.7fr)_380px]">
        <div className="relative min-h-[460px] border-b border-gray-200 lg:border-b-0 lg:border-r">
          {loading ? (
            <div className="flex h-full items-center justify-center bg-gray-50 text-sm text-gray-500">
              Loading county coverage map...
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center bg-red-50 px-6 text-center text-sm text-red-700">
              {error}
            </div>
          ) : properties.length === 0 ? (
            <div className="flex h-full items-center justify-center bg-gray-50 px-6 text-center text-sm text-gray-500">
              No geocoded properties are available for the management map yet.
            </div>
          ) : (
            <>
              <MapContainer
                center={MAP_CENTER}
                zoom={MAP_ZOOM}
                className="h-[460px] w-full"
                zoomControl
              >
                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <FitMapToProperties properties={properties} />
                {properties.map((property) => {
                  if (property.latitude == null || property.longitude == null) {
                    return null;
                  }

                  const coverage = getCoverageStatus(property, historicalState);
                  const isActive = property.id === activeId;
                  const center = [Number(property.latitude), Number(property.longitude)];

                  return (
                    <Fragment key={property.id}>
                      <Circle
                        center={center}
                        radius={260}
                        pathOptions={{
                          color: coverage.color,
                          weight: 0,
                          fillColor: coverage.color,
                          fillOpacity: isActive ? 0.24 : 0.1,
                        }}
                        eventHandlers={{
                          mouseover: () => setActiveId(property.id),
                          click: () => setActiveId(property.id),
                        }}
                      />
                      <CircleMarker
                        center={center}
                        radius={isActive ? 8 : 5}
                        pathOptions={{
                          color: isActive ? "#FFFFFF" : coverage.color,
                          weight: isActive ? 2 : 1,
                          fillColor: coverage.color,
                          fillOpacity: 0.92,
                        }}
                        eventHandlers={{
                          mouseover: () => setActiveId(property.id),
                          click: () => setActiveId(property.id),
                        }}
                      />
                    </Fragment>
                  );
                })}
              </MapContainer>

              <div className="pointer-events-none absolute bottom-3 left-3 rounded border border-gray-200 bg-white/95 px-3 py-2 text-[11px] text-gray-600 shadow-sm">
                <div className="mb-1 font-semibold text-gray-800">Coverage legend</div>
                <div className="grid gap-1 sm:grid-cols-2">
                  {Object.values(COVERAGE_META).map((status) => (
                    <div key={status.label} className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: status.color }}
                      />
                      <span>{status.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex min-h-[460px] flex-col bg-white">
          {activeProperty ? (
            <>
              <div className="border-b border-gray-200 px-4 py-4">
                <div className="text-xs uppercase tracking-wide text-gray-500">Active property</div>
                <h4 className="mt-1 font-heading text-xl font-semibold text-gray-900">
                  {activeProperty.address}
                </h4>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  <span
                    className="rounded px-2 py-1 font-medium"
                    style={{ color: activeCoverage.color, background: activeCoverage.bg }}
                  >
                    {activeCoverage.label}
                  </span>
                  {activeProperty.program && (
                    <span className="rounded bg-civic-blue-pale px-2 py-1 font-medium text-civic-blue">
                      {activeProperty.program}
                    </span>
                  )}
                  {activeFinding ? (
                    <span
                      className="rounded px-2 py-1 font-medium"
                      style={{ color: activeFinding.color, background: activeFinding.bg }}
                    >
                      {activeFinding.label}
                    </span>
                  ) : (
                    <span className="rounded bg-gray-100 px-2 py-1 font-medium text-gray-600">
                      Unreviewed
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-gray-600">{activeCoverage.description}</p>
              </div>

              <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded border border-gray-200 bg-gray-50 p-2">
                    <div className="uppercase tracking-wide text-[10px] text-gray-400">Parcel</div>
                    <div className="mt-1 font-medium text-gray-800">{activeProperty.parcel_id || "Not listed"}</div>
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 p-2">
                    <div className="uppercase tracking-wide text-[10px] text-gray-400">Buyer</div>
                    <div className="mt-1 font-medium text-gray-800">{activeProperty.buyer_name || "Not listed"}</div>
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 p-2">
                    <div className="uppercase tracking-wide text-[10px] text-gray-400">Sold Date</div>
                    <div className="mt-1 font-medium text-gray-800">{activeProperty.closing_date || "Not listed"}</div>
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 p-2">
                    <div className="uppercase tracking-wide text-[10px] text-gray-400">Latest Street View</div>
                    <div className="mt-1 font-medium text-gray-800">{activeProperty.streetview_date || "Not listed"}</div>
                  </div>
                </div>

                {activeDetection && (
                  <div className="rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
                    <div className="mb-2 uppercase tracking-wide text-[10px] text-gray-400">
                      Detection
                    </div>
                    <div className="flex items-center justify-between">
                      <span>{activeDetection.label}</span>
                      <strong>{activeProperty.detection_score ?? "n/a"}</strong>
                    </div>
                  </div>
                )}

                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <div className="text-xs uppercase tracking-wide text-gray-400">Before and After</div>
                    <Link
                      to={`/property/${activeProperty.id}`}
                      className="text-xs font-medium text-civic-green hover:underline"
                    >
                      Open record
                    </Link>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <ImagePanel
                      src={
                        activeProperty.streetview_historical_path || historicalState[activeProperty.id]?.status === "ready"
                          ? getImageUrl(activeProperty.id, "streetview_historical")
                          : ""
                      }
                      label={`Sold-date view ${activeProperty.streetview_historical_date || historicalState[activeProperty.id]?.date || ""}`.trim()}
                      fallback="No Street View is available close to the sold date"
                      loading={historicalState[activeProperty.id]?.status === "loading"}
                    />
                    <ImagePanel
                      src={activeProperty.streetview_available ? getImageUrl(activeProperty.id, "streetview") : ""}
                      label={`Latest ${activeProperty.streetview_date || ""}`.trim()}
                      fallback="Current Street View unavailable"
                    />
                  </div>
                </div>

                <div>
                  <div className="mb-2 text-xs uppercase tracking-wide text-gray-400">Satellite</div>
                  <ImagePanel
                    src={activeProperty.satellite_path ? getImageUrl(activeProperty.id, "satellite") : ""}
                    label="Satellite"
                    fallback="Satellite imagery unavailable"
                  />
                </div>

                {activeProperty.notes && (
                  <div className="rounded border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
                    <div className="mb-2 text-xs uppercase tracking-wide text-gray-400">Notes</div>
                    {activeProperty.notes}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-gray-500">
              Hover over the county map to inspect photo coverage for a property.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
