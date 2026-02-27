import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getProperties, updateProperty, getStats, batchUpdateProperties } from "../utils/api";
import { FINDINGS, DETECTION_LABELS } from "../utils/constants";
import { ReviewQueueSkeleton } from "../components/LoadingSkeleton";

const FILTER_OPTIONS = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Unreviewed" },
  { value: "resolved", label: "Resolved" },
  { value: "inconclusive", label: "Needs Inspection" },
];

const SORT_OPTIONS = [
  { value: "detection_score", label: "Worst First (Detection)" },
  { value: "created_at", label: "Newest First" },
  { value: "address", label: "Address A-Z" },
  { value: "reviewed_at", label: "Recently Reviewed" },
];

const PAGE_SIZE = 50;

export default function ReviewQueue() {
  const [properties, setProperties] = useState([]);
  const [stats, setStats] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("unreviewed");
  const [sort, setSort] = useState("detection_score");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [expandedId, setExpandedId] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const rowRefs = useRef([]);
  const navigate = useNavigate();

  const loadProperties = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        sort,
        order: sort === "address" ? "asc" : "desc",
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };
      if (filter === "unreviewed") params.reviewed = false;
      else if (filter === "inconclusive") params.finding = "inconclusive";
      if (search) params.search = search;

      const [result, s] = await Promise.all([getProperties(params), getStats()]);
      // Handle paginated response
      const props = result.properties || result;
      const total = result.total || 0;
      setProperties(props);
      setTotalCount(total);
      setStats(s);
    } catch (e) {
      console.error("Failed to load:", e);
    }
    setLoading(false);
  }, [filter, sort, search, page]);

  useEffect(() => { loadProperties(); }, [loadProperties]);

  // Reset page when filter/sort/search changes
  useEffect(() => { setPage(0); }, [filter, sort, search]);

  const handleFindingUpdate = async (id, finding) => {
    try {
      await updateProperty(id, { finding });
      await loadProperties();
    } catch (e) {
      console.error("Update failed:", e);
    }
  };

  // --- Feature 5: Bulk selection ---
  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(properties.map(p => p.id)));
  const selectNone = () => setSelected(new Set());

  const handleBatchUpdate = async (finding) => {
    const label = FINDINGS.find(f => f.value === finding)?.label || finding;
    if (!window.confirm(`Mark ${selected.size} properties as "${label}"?`)) return;
    try {
      await batchUpdateProperties([...selected], finding);
      setSelected(new Set());
      await loadProperties();
    } catch (e) {
      console.error("Batch update failed:", e);
    }
  };

  // --- Feature 3: Keyboard navigation ---
  useEffect(() => {
    const handler = (e) => {
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        setFocusedIndex(i => Math.min(i + 1, properties.length - 1));
        setExpandedId(null);
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        setFocusedIndex(i => Math.max(i - 1, 0));
        setExpandedId(null);
      } else if (e.key === "Enter" && focusedIndex >= 0) {
        e.preventDefault();
        navigate(`/property/${properties[focusedIndex].id}`, {
          state: { queueIds: properties.map(p => p.id) },
        });
      } else if (e.key === " " && focusedIndex >= 0) {
        // Feature 4: spacebar toggle preview
        e.preventDefault();
        setExpandedId(prev =>
          prev === properties[focusedIndex].id ? null : properties[focusedIndex].id
        );
      } else if (e.key >= "1" && e.key <= "6" && focusedIndex >= 0) {
        const findingIdx = parseInt(e.key) - 1;
        if (findingIdx < FINDINGS.length) {
          handleFindingUpdate(properties[focusedIndex].id, FINDINGS[findingIdx].value);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [focusedIndex, properties, navigate]);

  // Auto-scroll focused row into view
  useEffect(() => {
    if (focusedIndex >= 0 && rowRefs.current[focusedIndex]) {
      rowRefs.current[focusedIndex].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [focusedIndex]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Review Queue</h2>
        <p className="text-sm text-gray-500 mt-1">
          Work through properties. Click to open detail, or use keyboard: arrows navigate, Enter open, Space preview, 1-6 assign finding.
        </p>
      </div>

      {/* Filters and search */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-1.5">
          {FILTER_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                filter === opt.value
                  ? "bg-civic-green-pale text-civic-green border border-civic-green/20"
                  : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <select
          value={sort}
          onChange={e => setSort(e.target.value)}
          className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white text-gray-700"
        >
          {SORT_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search address, parcel, buyer..."
          className="text-xs border border-gray-200 rounded px-3 py-1.5 w-48 md:w-64"
        />
        {/* Select all / none */}
        <div className="flex gap-1.5 text-xs text-gray-500">
          <button onClick={selectAll} className="hover:text-gray-700 hover:underline">Select all</button>
          <span>/</span>
          <button onClick={selectNone} className="hover:text-gray-700 hover:underline">None</button>
        </div>
      </div>

      {/* Stats bar + keyboard hint */}
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

      {/* Property list */}
      {loading ? (
        <ReviewQueueSkeleton />
      ) : properties.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-gray-500">No properties match this filter.</p>
          <p className="text-xs text-gray-400 mt-2">Import properties first, then run the pipeline from the Dashboard.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {properties.map((prop, i) => {
            const finding = FINDINGS.find(f => f.value === prop.finding);
            const detection = DETECTION_LABELS[prop.detection_label];

            return (
              <div
                key={prop.id}
                ref={el => rowRefs.current[i] = el}
                className={`bg-white border rounded-lg hover:border-gray-300 transition-colors cursor-pointer ${
                  focusedIndex === i ? "ring-2 ring-civic-green ring-offset-1 border-civic-green" : "border-gray-200"
                }`}
                style={{ borderLeftWidth: 3, borderLeftColor: finding ? finding.color : detection ? detection.color : "#E0E0E0" }}
              >
                <div
                  className="flex items-center gap-3 p-3"
                  onClick={() => navigate(`/property/${prop.id}`, {
                    state: { queueIds: properties.map(p => p.id) }
                  })}
                >
                  {/* Checkbox for bulk selection */}
                  <input
                    type="checkbox"
                    checked={selected.has(prop.id)}
                    onChange={(e) => { e.stopPropagation(); toggleSelect(prop.id); }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-4 h-4 rounded border-gray-300 text-civic-green focus:ring-civic-green flex-shrink-0"
                  />

                  {/* Thumbnail */}
                  {prop.streetview_available ? (
                    <img
                      src={`/api/imagery/image/${prop.id}/streetview`}
                      alt=""
                      className="w-20 h-14 object-cover rounded flex-shrink-0 bg-gray-100"
                    />
                  ) : (
                    <div className="w-20 h-14 bg-gray-100 rounded flex-shrink-0 flex items-center justify-center text-gray-400 text-xs">
                      No img
                    </div>
                  )}

                  {/* Property info */}
                  <div className="flex-1 min-w-0">
                    <div className="font-heading text-sm font-semibold text-gray-900 truncate">
                      {prop.address}
                    </div>
                    <div className="flex gap-2 mt-1 flex-wrap">
                      {prop.parcel_id && (
                        <span className="text-xs text-gray-500">{prop.parcel_id}</span>
                      )}
                      {prop.buyer_name && (
                        <span className="text-xs text-gray-500">{prop.buyer_name}</span>
                      )}
                      {prop.program && (
                        <span className="text-xs font-medium text-civic-blue bg-civic-blue-pale px-1.5 py-0.5 rounded">
                          {prop.program}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Detection badge */}
                  {detection && prop.detection_label !== "unprocessed" && (
                    <span
                      className="text-xs font-medium px-2 py-1 rounded flex-shrink-0"
                      style={{ color: detection.color, background: detection.bg }}
                    >
                      {detection.label}
                    </span>
                  )}

                  {/* Finding badge */}
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

                {/* Feature 4: Expandable inline preview */}
                {expandedId === prop.id && (
                  <div className="px-4 pb-4 pt-2 border-t border-gray-100 bg-gray-50/50">
                    <div className="flex gap-4">
                      {/* Imagery */}
                      <div className="flex gap-3 flex-shrink-0">
                        {prop.streetview_available ? (
                          <img
                            src={`/api/imagery/image/${prop.id}/streetview`}
                            alt=""
                            className="w-72 h-48 object-cover rounded border border-gray-200"
                          />
                        ) : (
                          <div className="w-72 h-48 bg-gray-100 rounded flex items-center justify-center text-gray-400 text-sm">
                            No Street View
                          </div>
                        )}
                        {prop.satellite_path && (
                          <img
                            src={`/api/imagery/image/${prop.id}/satellite`}
                            alt=""
                            className="w-48 h-48 object-cover rounded border border-gray-200"
                          />
                        )}
                      </div>
                      {/* Finding buttons */}
                      <div className="flex-1 space-y-3">
                        {detection && prop.detection_label !== "unprocessed" && (
                          <div className="text-xs" style={{ color: detection.color }}>
                            Detection: {detection.label} (score: {prop.detection_score})
                          </div>
                        )}
                        <div className="flex gap-1.5 flex-wrap">
                          {FINDINGS.map((f, idx) => (
                            <button
                              key={f.value}
                              onClick={(e) => { e.stopPropagation(); handleFindingUpdate(prop.id, f.value); }}
                              className="text-xs font-medium px-2.5 py-1.5 rounded border transition-all"
                              style={{
                                color: prop.finding === f.value ? "#fff" : f.color,
                                background: prop.finding === f.value ? f.color : f.bg,
                                borderColor: f.color + "40",
                              }}
                            >
                              <span className="opacity-60 mr-0.5">{idx + 1}</span> {f.label}
                            </button>
                          ))}
                        </div>
                        {/* External links */}
                        <div className="flex gap-2">
                          <a
                            href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${encodeURIComponent(prop.address + ", Flint, MI")}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-civic-green hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            Interactive Street View
                          </a>
                          <a
                            href={`https://www.flintpropertyportal.com/search?q=${encodeURIComponent(prop.address)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-civic-blue hover:underline"
                            onClick={(e) => e.stopPropagation()}
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

      {/* Feature 2: Pagination controls */}
      {totalCount > PAGE_SIZE && (
        <div className="flex items-center justify-between pt-4 border-t border-gray-100">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            className="text-xs font-medium px-3 py-1.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-xs text-gray-500">
            Page {page + 1} of {totalPages} ({totalCount} total)
          </span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={(page + 1) * PAGE_SIZE >= totalCount}
            className="text-xs font-medium px-3 py-1.5 rounded border border-civic-green text-civic-green hover:bg-civic-green-pale disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}

      {/* Feature 5: Floating bulk actions bar */}
      {selected.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-30 bg-white border border-gray-200 shadow-lg rounded-lg px-4 py-3 flex items-center gap-3">
          <span className="text-xs font-medium text-gray-700">
            {selected.size} selected
          </span>
          <div className="flex gap-1.5">
            {FINDINGS.map(f => (
              <button
                key={f.value}
                onClick={() => handleBatchUpdate(f.value)}
                className="text-xs font-medium px-2.5 py-1.5 rounded"
                style={{ color: f.color, background: f.bg }}
              >
                {f.label}
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
