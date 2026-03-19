import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  batchUpdateProperties,
  getImageUrl,
  getPriorityQueue,
  getStats,
  updateProperty,
} from "../utils/api";
import {
  DETECTION_LABELS,
  FINDINGS,
  PROGRAMS,
  REVIEW_FAST_LANES,
} from "../utils/constants";
import InlineNotice from "../components/InlineNotice";
import { ReviewQueueSkeleton } from "../components/LoadingSkeleton";

const PAGE_SIZE = 50;

const FILTER_OPTIONS = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Unreviewed" },
  { value: "resolved", label: "Resolved" },
  { value: "inconclusive", label: "Needs Inspection" },
];

const SORT_OPTIONS = [
  { value: "priority", label: "Compliance Priority" },
  { value: "detection_score", label: "Detection Score" },
  { value: "created_at", label: "Newest First" },
  { value: "address", label: "Address A-Z" },
];

const DETECTION_FILTER_OPTIONS = [
  { value: "all", label: "All detections" },
  { value: "likely_demolished", label: "Likely Demolished" },
  { value: "likely_vacant", label: "Likely Vacant" },
  { value: "likely_occupied", label: "Likely Occupied" },
  { value: "no_streetview", label: "No Street View" },
  { value: "unprocessed", label: "Not Processed" },
];

export default function ReviewQueue() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [properties, setProperties] = useState([]);
  const [stats, setStats] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(() => Math.max(0, Number(searchParams.get("page") || 0)));
  const [filter, setFilter] = useState(() => searchParams.get("filter") || "unreviewed");
  const [sort, setSort] = useState(() => searchParams.get("sort") || "priority");
  const [search, setSearch] = useState(() => searchParams.get("search") || "");
  const [programFilter, setProgramFilter] = useState(() => searchParams.get("program") || "all");
  const [detectionFilter, setDetectionFilter] = useState(() => searchParams.get("detection") || "all");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [expandedId, setExpandedId] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const rowRefs = useRef([]);
  const navigate = useNavigate();

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  const loadProperties = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const params = {
        filter,
        sort,
        order: sort === "address" ? "asc" : "desc",
        search,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };
      if (programFilter !== "all") {
        params.program = programFilter;
      }
      if (detectionFilter !== "all") {
        params.detection = detectionFilter;
      }

      const [queue, statsSummary] = await Promise.all([
        getPriorityQueue(params),
        getStats(),
      ]);
      setProperties(queue.properties || []);
      setTotalCount(queue.total || 0);
      setStats(statsSummary);
    } catch (error) {
      setLoadError(error.message || "Could not load the review queue.");
    } finally {
      setLoading(false);
    }
  }, [detectionFilter, filter, page, programFilter, search, sort]);

  useEffect(() => {
    loadProperties();
  }, [loadProperties]);

  useEffect(() => {
    const nextParams = new URLSearchParams();
    if (filter !== "unreviewed") {
      nextParams.set("filter", filter);
    }
    if (sort !== "priority") {
      nextParams.set("sort", sort);
    }
    if (search) {
      nextParams.set("search", search);
    }
    if (programFilter !== "all") {
      nextParams.set("program", programFilter);
    }
    if (detectionFilter !== "all") {
      nextParams.set("detection", detectionFilter);
    }
    if (page > 0) {
      nextParams.set("page", String(page));
    }
    setSearchParams(nextParams, { replace: true });
  }, [detectionFilter, filter, page, programFilter, search, setSearchParams, sort]);

  useEffect(() => {
    setPage(0);
    setSelected(new Set());
    setFocusedIndex(-1);
    setExpandedId(null);
  }, [filter, sort, search, programFilter, detectionFilter]);

  useEffect(() => {
    setSelected(new Set());
    setFocusedIndex(-1);
    setExpandedId(null);
  }, [page]);

  const handleFindingUpdate = async (id, finding) => {
    setNotice(null);
    try {
      await updateProperty(id, { finding });
      await loadProperties();
      setNotice({
        tone: "success",
        title: "Finding saved",
        message: "The property finding was updated.",
      });
    } catch (error) {
      setNotice({
        tone: "error",
        title: "Update failed",
        message: error.message || "The finding could not be saved.",
      });
    }
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(properties.map((property) => property.id)));
  const selectNone = () => setSelected(new Set());

  const handleBatchUpdate = async (finding) => {
    const label = FINDINGS.find((item) => item.value === finding)?.label || finding;
    if (!window.confirm(`Mark ${selected.size} properties as "${label}"?`)) {
      return;
    }

    setNotice(null);
    try {
      await batchUpdateProperties([...selected], finding);
      setSelected(new Set());
      await loadProperties();
      setNotice({
        tone: "success",
        title: "Batch update complete",
        message: `${selected.size} properties were updated.`,
      });
    } catch (error) {
      setNotice({
        tone: "error",
        title: "Batch update failed",
        message: error.message || "The selected properties could not be updated.",
      });
    }
  };

  useEffect(() => {
    const handler = (event) => {
      const tag = event.target.tagName;
      if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(tag)) {
        return;
      }

      if ((event.key === "ArrowDown" || event.key === "j") && properties.length > 0) {
        event.preventDefault();
        setFocusedIndex((index) => Math.min(index + 1, properties.length - 1));
        setExpandedId(null);
      } else if ((event.key === "ArrowUp" || event.key === "k") && properties.length > 0) {
        event.preventDefault();
        setFocusedIndex((index) => Math.max(index - 1, 0));
        setExpandedId(null);
      } else if (event.key === "Enter" && focusedIndex >= 0) {
        event.preventDefault();
        navigate(`/property/${properties[focusedIndex].id}`, {
          state: { queueIds: properties.map((property) => property.id) },
        });
      } else if (event.key === " " && focusedIndex >= 0) {
        event.preventDefault();
        setExpandedId((prev) =>
          prev === properties[focusedIndex].id ? null : properties[focusedIndex].id
        );
      } else if (event.key >= "1" && event.key <= "6" && focusedIndex >= 0) {
        const findingIndex = parseInt(event.key, 10) - 1;
        if (findingIndex < FINDINGS.length) {
          handleFindingUpdate(properties[focusedIndex].id, FINDINGS[findingIndex].value);
        }
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [focusedIndex, navigate, properties]);

  useEffect(() => {
    if (focusedIndex >= 0 && rowRefs.current[focusedIndex]) {
      rowRefs.current[focusedIndex].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [focusedIndex]);

  const laneCounts = {
    unreviewed: stats?.unreviewed || 0,
    likely_demolished: stats?.unreviewed_by_detection?.likely_demolished || 0,
    likely_vacant: stats?.unreviewed_by_detection?.likely_vacant || 0,
    needs_inspection: stats?.needs_inspection || 0,
    unprocessed: stats?.unreviewed_by_detection?.unprocessed || 0,
  };

  const applyLane = (lane) => {
    setFilter(lane.params.filter || "unreviewed");
    setSort(lane.params.sort || "priority");
    setProgramFilter(lane.params.program || "all");
    setDetectionFilter(lane.params.detection || "all");
    setSearch(lane.params.search || "");
    setPage(0);
    setNotice(null);
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Review Queue</h2>
        <p className="mt-1 text-sm text-gray-500">
          Review unreviewed properties first, then narrow by program or detection signal when you need to move quickly.
        </p>
      </div>

      {notice && (
        <InlineNotice
          tone={notice.tone}
          title={notice.title}
          message={notice.message}
        />
      )}

      {loadError && (
        <InlineNotice
          tone="error"
          title="Queue unavailable"
          message={loadError}
          actionLabel="Retry"
          onAction={loadProperties}
        />
      )}

      <div className="grid gap-2 rounded-lg border border-gray-200 bg-white p-4 md:grid-cols-5">
        {REVIEW_FAST_LANES.map((lane) => (
          <button
            key={lane.id}
            onClick={() => applyLane(lane)}
            className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-left transition-colors hover:border-civic-green/40 hover:bg-civic-green-pale/20"
          >
            <div className="text-[11px] uppercase tracking-wide text-gray-500">
              {laneCounts[lane.id] || 0} open
            </div>
            <div className="mt-1 text-sm font-semibold text-gray-900">{lane.label}</div>
            <div className="mt-1 text-xs text-gray-500">{lane.description}</div>
          </button>
        ))}
      </div>

      <div className="grid gap-3 rounded-lg border border-gray-200 bg-white p-4 md:grid-cols-[auto_auto_auto_1fr_auto]">
        <div className="flex flex-wrap gap-1.5">
          {FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => setFilter(option.value)}
              className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                filter === option.value
                  ? "border border-civic-green/20 bg-civic-green-pale text-civic-green"
                  : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <select
          value={sort}
          onChange={(event) => setSort(event.target.value)}
          className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>

        <select
          value={programFilter}
          onChange={(event) => setProgramFilter(event.target.value)}
          className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
        >
          <option value="all">All programs</option>
          {PROGRAMS.map((program) => (
            <option key={program} value={program}>{program}</option>
          ))}
        </select>

        <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search address, parcel, buyer..."
            className="w-full rounded border border-gray-200 px-3 py-1.5 text-xs"
          />
          <select
            value={detectionFilter}
            onChange={(event) => setDetectionFilter(event.target.value)}
            className="rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-700"
          >
            {DETECTION_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <button onClick={selectAll} className="hover:text-gray-700 hover:underline">Select visible</button>
          <span>/</span>
          <button onClick={selectNone} className="hover:text-gray-700 hover:underline">Clear</button>
        </div>
      </div>

      {stats && (
        <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
          <span>{totalCount} in view</span>
          <span className="text-civic-green">{stats.reviewed} reviewed</span>
          <span>{stats.unreviewed} remaining</span>
          <span className="text-orange-600">{stats.needs_inspection} need inspection</span>
          <span className="ml-auto hidden text-gray-400 md:inline">
            Keys: arrows navigate, Enter open, Space preview, 1-6 finding
          </span>
        </div>
      )}

      {loading ? (
        <ReviewQueueSkeleton />
      ) : loadError && properties.length === 0 ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-sm text-red-700">The review queue could not be loaded.</p>
          <button
            onClick={loadProperties}
            className="mt-3 text-xs font-medium text-red-700 underline"
          >
            Retry
          </button>
        </div>
      ) : properties.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center">
          <p className="text-gray-600">No properties match this view.</p>
          <p className="mt-2 text-xs text-gray-400">
            Try clearing a filter, or import more properties from the Import page.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {properties.map((property, index) => {
            const finding = FINDINGS.find((item) => item.value === property.finding);
            const detection = DETECTION_LABELS[property.detection_label];

            return (
              <div
                key={property.id}
                ref={(element) => {
                  rowRefs.current[index] = element;
                }}
                className={`rounded-lg border bg-white transition-colors hover:border-gray-300 ${
                  focusedIndex === index
                    ? "border-civic-green ring-2 ring-civic-green ring-offset-1"
                    : "border-gray-200"
                }`}
                style={{
                  borderLeftWidth: 4,
                  borderLeftColor: finding ? finding.color : detection ? detection.color : "#E0E0E0",
                }}
              >
                <div
                  className="cursor-pointer p-3"
                  onClick={() => navigate(`/property/${property.id}`, {
                    state: { queueIds: properties.map((item) => item.id) },
                  })}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      aria-label={`Select ${property.address}`}
                      checked={selected.has(property.id)}
                      onChange={(event) => {
                        event.stopPropagation();
                        toggleSelect(property.id);
                      }}
                      onClick={(event) => event.stopPropagation()}
                      className="mt-1 h-4 w-4 shrink-0 rounded border-gray-300 text-civic-green focus:ring-civic-green"
                    />

                    {property.streetview_available ? (
                      <img
                        src={getImageUrl(property.id, "streetview")}
                        alt={`Street View preview for ${property.address}`}
                        className="h-16 w-24 shrink-0 rounded bg-gray-100 object-cover"
                      />
                    ) : (
                      <div className="flex h-16 w-24 shrink-0 items-center justify-center rounded bg-gray-100 text-xs text-gray-400">
                        No image
                      </div>
                    )}

                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-gray-900">{property.address}</div>
                      <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-gray-500">
                        {property.parcel_id && <span>{property.parcel_id}</span>}
                        {property.buyer_name && <span>{property.buyer_name}</span>}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {property.program && (
                          <span className="rounded bg-civic-blue-pale px-1.5 py-0.5 text-xs font-medium text-civic-blue">
                            {property.program}
                          </span>
                        )}
                        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-700">
                          Priority {property.priority_score}
                        </span>
                        {detection && property.detection_label !== "unprocessed" && (
                          <span
                            className="rounded px-2 py-0.5 text-xs font-medium"
                            style={{ color: detection.color, background: detection.bg }}
                          >
                            {detection.label}
                          </span>
                        )}
                        {finding ? (
                          <span
                            className="rounded px-2 py-0.5 text-xs font-medium"
                            style={{ color: finding.color, background: finding.bg }}
                          >
                            {finding.label}
                          </span>
                        ) : (
                          <span className="rounded bg-gray-50 px-2 py-0.5 text-xs italic text-gray-400">
                            Unreviewed
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {expandedId === property.id && (
                  <div className="border-t border-gray-100 bg-gray-50/70 px-4 pb-4 pt-3">
                    <div className="flex flex-col gap-4 lg:flex-row">
                      <div className="flex flex-wrap gap-3">
                        {property.streetview_available ? (
                          <img
                            src={getImageUrl(property.id, "streetview")}
                            alt={`Expanded Street View for ${property.address}`}
                            className="h-48 w-full rounded border border-gray-200 object-cover sm:w-72"
                          />
                        ) : (
                          <div className="flex h-48 w-full items-center justify-center rounded border border-gray-200 bg-gray-100 text-sm text-gray-400 sm:w-72">
                            No Street View
                          </div>
                        )}
                        {property.satellite_path && (
                          <img
                            src={getImageUrl(property.id, "satellite")}
                            alt={`Satellite image for ${property.address}`}
                            className="h-48 w-full rounded border border-gray-200 object-cover sm:w-48"
                          />
                        )}
                      </div>

                      <div className="flex-1 space-y-3">
                        {detection && property.detection_label !== "unprocessed" && (
                          <div className="text-xs" style={{ color: detection.color }}>
                            Detection: {detection.label} (score: {property.detection_score})
                          </div>
                        )}

                        <div className="flex flex-wrap gap-1.5">
                          {FINDINGS.map((findingOption, findingIndex) => (
                            <button
                              key={findingOption.value}
                              onClick={(event) => {
                                event.stopPropagation();
                                handleFindingUpdate(property.id, findingOption.value);
                              }}
                              className="rounded border px-2.5 py-1.5 text-xs font-medium transition-all"
                              style={{
                                color: property.finding === findingOption.value ? "#fff" : findingOption.color,
                                background: property.finding === findingOption.value ? findingOption.color : findingOption.bg,
                                borderColor: `${findingOption.color}40`,
                              }}
                            >
                              <span className="mr-0.5 opacity-60">{findingIndex + 1}</span>
                              {findingOption.label}
                            </button>
                          ))}
                        </div>

                        <div className="flex flex-wrap gap-3 text-xs">
                          <a
                            href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${encodeURIComponent(property.address + ", Flint, MI")}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-civic-green hover:underline"
                            onClick={(event) => event.stopPropagation()}
                          >
                            Interactive Street View
                          </a>
                          <a
                            href={`https://www.flintpropertyportal.com/search?q=${encodeURIComponent(property.address)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-civic-blue hover:underline"
                            onClick={(event) => event.stopPropagation()}
                          >
                            Property Portal
                          </a>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {totalCount > PAGE_SIZE && (
        <div className="flex items-center justify-between border-t border-gray-100 pt-4">
          <button
            onClick={() => setPage((current) => Math.max(0, current - 1))}
            disabled={page === 0}
            className="rounded border border-gray-200 px-3 py-1.5 text-xs font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-xs text-gray-500">
            Page {page + 1} of {totalPages} ({totalCount} total)
          </span>
          <button
            onClick={() => setPage((current) => current + 1)}
            disabled={(page + 1) * PAGE_SIZE >= totalCount}
            className="rounded border border-civic-green px-3 py-1.5 text-xs font-medium text-civic-green hover:bg-civic-green-pale disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      {selected.size > 0 && (
        <div className="fixed bottom-4 left-1/2 z-30 flex max-w-[calc(100vw-1rem)] -translate-x-1/2 items-center gap-3 overflow-x-auto rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-lg">
          <span className="shrink-0 text-xs font-medium text-gray-700">{selected.size} selected</span>
          <div className="flex shrink-0 gap-1.5">
            {FINDINGS.map((findingOption) => (
              <button
                key={findingOption.value}
                onClick={() => handleBatchUpdate(findingOption.value)}
                className="shrink-0 rounded px-2.5 py-1.5 text-xs font-medium"
                style={{ color: findingOption.color, background: findingOption.bg }}
              >
                {findingOption.label}
              </button>
            ))}
          </div>
          <button onClick={selectNone} className="shrink-0 text-xs text-gray-500 hover:text-gray-700">
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
