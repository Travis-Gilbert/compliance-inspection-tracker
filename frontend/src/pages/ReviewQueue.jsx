import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  getPriorityQueue,
  updateProperty,
  getStats,
  batchUpdateProperties,
} from "../utils/api";
import { FINDINGS, DETECTION_LABELS } from "../utils/constants";
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

export default function ReviewQueue() {
  const [properties, setProperties] = useState([]);
  const [stats, setStats] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("unreviewed");
  const [sort, setSort] = useState("priority");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [expandedId, setExpandedId] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const rowRefs = useRef([]);
  const navigate = useNavigate();

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  const loadProperties = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        filter,
        sort,
        order: sort === "address" ? "asc" : "desc",
        search,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };
      const [queue, statsSummary] = await Promise.all([getPriorityQueue(params), getStats()]);
      setProperties(queue.properties || []);
      setTotalCount(queue.total || 0);
      setStats(statsSummary);
    } catch (error) {
      console.error("Failed to load review queue:", error);
    } finally {
      setLoading(false);
    }
  }, [filter, sort, search, page]);

  useEffect(() => {
    loadProperties();
  }, [loadProperties]);

  useEffect(() => {
    setPage(0);
  }, [filter, sort, search]);

  const handleFindingUpdate = async (id, finding) => {
    try {
      await updateProperty(id, { finding });
      await loadProperties();
    } catch (error) {
      console.error("Update failed:", error);
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

  const selectAll = () => setSelected(new Set(properties.map((prop) => prop.id)));
  const selectNone = () => setSelected(new Set());

  const handleBatchUpdate = async (finding) => {
    const label = FINDINGS.find((item) => item.value === finding)?.label || finding;
    if (!window.confirm(`Mark ${selected.size} properties as "${label}"?`)) {
      return;
    }
    try {
      await batchUpdateProperties([...selected], finding);
      setSelected(new Set());
      await loadProperties();
    } catch (error) {
      console.error("Batch update failed:", error);
    }
  };

  useEffect(() => {
    const handler = (event) => {
      const tag = event.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return;
      }

      if (event.key === "ArrowDown" || event.key === "j") {
        event.preventDefault();
        setFocusedIndex((index) => Math.min(index + 1, properties.length - 1));
        setExpandedId(null);
      } else if (event.key === "ArrowUp" || event.key === "k") {
        event.preventDefault();
        setFocusedIndex((index) => Math.max(index - 1, 0));
        setExpandedId(null);
      } else if (event.key === "Enter" && focusedIndex >= 0) {
        event.preventDefault();
        navigate(`/property/${properties[focusedIndex].id}`, {
          state: { queueIds: properties.map((prop) => prop.id) },
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
  }, [focusedIndex, properties, navigate]);

  useEffect(() => {
    if (focusedIndex >= 0 && rowRefs.current[focusedIndex]) {
      rowRefs.current[focusedIndex].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [focusedIndex]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Review Queue</h2>
        <p className="text-sm text-gray-500 mt-1">
          Queue defaults to compliance priority, keyboard and bulk tools stay available for fast review.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-1.5">
          {FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => setFilter(option.value)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                filter === option.value
                  ? "bg-civic-green-pale text-civic-green border border-civic-green/20"
                  : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <select
          value={sort}
          onChange={(event) => setSort(event.target.value)}
          className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white text-gray-700"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>

        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search address, parcel, buyer..."
          className="text-xs border border-gray-200 rounded px-3 py-1.5 w-48 md:w-64"
        />

        <div className="flex gap-1.5 text-xs text-gray-500">
          <button onClick={selectAll} className="hover:text-gray-700 hover:underline">Select all</button>
          <span>/</span>
          <button onClick={selectNone} className="hover:text-gray-700 hover:underline">None</button>
        </div>
      </div>

      {stats && (
        <div className="flex items-center gap-4 text-xs text-gray-500 flex-wrap">
          <span>{totalCount} total</span>
          <span className="text-civic-green">{stats.reviewed} reviewed</span>
          <span>{stats.unreviewed} remaining</span>
          <span className="text-orange-600">{stats.needs_inspection} need inspection</span>
          <span className="text-gray-400 hidden md:inline ml-auto">
            Keys: arrows navigate, Enter open, Space preview, 1-6 finding
          </span>
        </div>
      )}

      {loading ? (
        <ReviewQueueSkeleton />
      ) : properties.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-gray-500">No properties match this filter.</p>
          <p className="text-xs text-gray-400 mt-2">Import properties, then run the pipeline from the Dashboard.</p>
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
                className={`bg-white border rounded-lg hover:border-gray-300 transition-colors cursor-pointer ${
                  focusedIndex === index ? "ring-2 ring-civic-green ring-offset-1 border-civic-green" : "border-gray-200"
                }`}
                style={{
                  borderLeftWidth: 3,
                  borderLeftColor: finding ? finding.color : detection ? detection.color : "#E0E0E0",
                }}
              >
                <div
                  className="flex items-center gap-3 p-3"
                  onClick={() => navigate(`/property/${property.id}`, {
                    state: { queueIds: properties.map((item) => item.id) },
                  })}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(property.id)}
                    onChange={(event) => {
                      event.stopPropagation();
                      toggleSelect(property.id);
                    }}
                    onClick={(event) => event.stopPropagation()}
                    className="w-4 h-4 rounded border-gray-300 text-civic-green focus:ring-civic-green flex-shrink-0"
                  />

                  {property.streetview_available ? (
                    <img
                      src={`/api/imagery/image/${property.id}/streetview`}
                      alt=""
                      className="w-20 h-14 object-cover rounded flex-shrink-0 bg-gray-100"
                    />
                  ) : (
                    <div className="w-20 h-14 bg-gray-100 rounded flex-shrink-0 flex items-center justify-center text-gray-400 text-xs">
                      No img
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="font-heading text-sm font-semibold text-gray-900 truncate">
                      {property.address}
                    </div>
                    <div className="flex gap-2 mt-1 flex-wrap items-center">
                      {property.parcel_id && (
                        <span className="text-xs text-gray-500">{property.parcel_id}</span>
                      )}
                      {property.buyer_name && (
                        <span className="text-xs text-gray-500">{property.buyer_name}</span>
                      )}
                      {property.program && (
                        <span className="text-xs font-medium text-civic-blue bg-civic-blue-pale px-1.5 py-0.5 rounded">
                          {property.program}
                        </span>
                      )}
                      <span className="text-xs font-medium text-gray-700 bg-gray-100 px-1.5 py-0.5 rounded">
                        Priority {property.priority_score}
                      </span>
                    </div>
                  </div>

                  {detection && property.detection_label !== "unprocessed" && (
                    <span
                      className="text-xs font-medium px-2 py-1 rounded flex-shrink-0"
                      style={{ color: detection.color, background: detection.bg }}
                    >
                      {detection.label}
                    </span>
                  )}

                  {finding ? (
                    <span
                      className="text-xs font-medium px-2 py-1 rounded flex-shrink-0"
                      style={{ color: finding.color, background: finding.bg }}
                    >
                      {finding.label}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-400 italic flex-shrink-0">Unreviewed</span>
                  )}
                </div>

                {expandedId === property.id && (
                  <div className="px-4 pb-4 pt-2 border-t border-gray-100 bg-gray-50/50">
                    <div className="flex gap-4">
                      <div className="flex gap-3 flex-shrink-0">
                        {property.streetview_available ? (
                          <img
                            src={`/api/imagery/image/${property.id}/streetview`}
                            alt=""
                            className="w-72 h-48 object-cover rounded border border-gray-200"
                          />
                        ) : (
                          <div className="w-72 h-48 bg-gray-100 rounded flex items-center justify-center text-gray-400 text-sm">
                            No Street View
                          </div>
                        )}
                        {property.satellite_path && (
                          <img
                            src={`/api/imagery/image/${property.id}/satellite`}
                            alt=""
                            className="w-48 h-48 object-cover rounded border border-gray-200"
                          />
                        )}
                      </div>

                      <div className="flex-1 space-y-3">
                        {detection && property.detection_label !== "unprocessed" && (
                          <div className="text-xs" style={{ color: detection.color }}>
                            Detection: {detection.label} (score: {property.detection_score})
                          </div>
                        )}
                        <div className="flex gap-1.5 flex-wrap">
                          {FINDINGS.map((findingOption, findingIndex) => (
                            <button
                              key={findingOption.value}
                              onClick={(event) => {
                                event.stopPropagation();
                                handleFindingUpdate(property.id, findingOption.value);
                              }}
                              className="text-xs font-medium px-2.5 py-1.5 rounded border transition-all"
                              style={{
                                color: property.finding === findingOption.value ? "#fff" : findingOption.color,
                                background: property.finding === findingOption.value ? findingOption.color : findingOption.bg,
                                borderColor: `${findingOption.color}40`,
                              }}
                            >
                              <span className="opacity-60 mr-0.5">{findingIndex + 1}</span> {findingOption.label}
                            </button>
                          ))}
                        </div>
                        <div className="flex gap-2">
                          <a
                            href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${encodeURIComponent(property.address + ", Flint, MI")}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-civic-green hover:underline"
                            onClick={(event) => event.stopPropagation()}
                          >
                            Interactive Street View
                          </a>
                          <a
                            href={`https://www.flintpropertyportal.com/search?q=${encodeURIComponent(property.address)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-civic-blue hover:underline"
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
        <div className="flex items-center justify-between pt-4 border-t border-gray-100">
          <button
            onClick={() => setPage((current) => Math.max(0, current - 1))}
            disabled={page === 0}
            className="text-xs font-medium px-3 py-1.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-xs text-gray-500">
            Page {page + 1} of {totalPages} ({totalCount} total)
          </span>
          <button
            onClick={() => setPage((current) => current + 1)}
            disabled={(page + 1) * PAGE_SIZE >= totalCount}
            className="text-xs font-medium px-3 py-1.5 rounded border border-civic-green text-civic-green hover:bg-civic-green-pale disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}

      {selected.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-30 bg-white border border-gray-200 shadow-lg rounded-lg px-4 py-3 flex items-center gap-3">
          <span className="text-xs font-medium text-gray-700">{selected.size} selected</span>
          <div className="flex gap-1.5">
            {FINDINGS.map((findingOption) => (
              <button
                key={findingOption.value}
                onClick={() => handleBatchUpdate(findingOption.value)}
                className="text-xs font-medium px-2.5 py-1.5 rounded"
                style={{ color: findingOption.color, background: findingOption.bg }}
              >
                {findingOption.label}
              </button>
            ))}
          </div>
          <button onClick={selectNone} className="text-xs text-gray-500 hover:text-gray-700 ml-2">
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
