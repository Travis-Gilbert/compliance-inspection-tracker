import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { getProperties, updateProperty, getStats } from "../utils/api";
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

export default function ReviewQueue() {
  const [properties, setProperties] = useState([]);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState("unreviewed");
  const [sort, setSort] = useState("detection_score");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const loadProperties = useCallback(async () => {
    setLoading(true);
    try {
      const params = { sort, order: sort === "address" ? "asc" : "desc", limit: 100 };
      if (filter === "unreviewed") params.reviewed = false;
      else if (filter === "resolved") {
        // We'll filter client-side for resolved
      } else if (filter === "inconclusive") params.finding = "inconclusive";
      if (search) params.search = search;

      const [props, s] = await Promise.all([getProperties(params), getStats()]);
      setProperties(props);
      setStats(s);
    } catch (e) {
      console.error("Failed to load:", e);
    }
    setLoading(false);
  }, [filter, sort, search]);

  useEffect(() => { loadProperties(); }, [loadProperties]);

  const handleFindingUpdate = async (id, finding) => {
    try {
      await updateProperty(id, { finding });
      await loadProperties();
    } catch (e) {
      console.error("Update failed:", e);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-heading text-2xl font-bold text-gray-900">Review Queue</h2>
        <p className="text-sm text-gray-500 mt-1">
          Work through properties one at a time. Click a property to see imagery and record your finding.
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
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="flex gap-4 text-xs text-gray-500">
          <span>{stats.total} total</span>
          <span className="text-civic-green">{stats.reviewed} reviewed</span>
          <span>{stats.unreviewed} remaining</span>
          <span className="text-orange-600">{stats.needs_inspection} need inspection</span>
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
          {properties.map(prop => {
            const finding = FINDINGS.find(f => f.value === prop.finding);
            const detection = DETECTION_LABELS[prop.detection_label];

            return (
              <div
                key={prop.id}
                className="bg-white border border-gray-200 rounded-lg hover:border-gray-300 transition-colors cursor-pointer"
                style={{ borderLeftWidth: 3, borderLeftColor: finding ? finding.color : detection ? detection.color : "#E0E0E0" }}
              >
                <div
                  className="flex items-center gap-3 p-3"
                  onClick={() => navigate(`/property/${prop.id}`, {
                    state: { queueIds: properties.map(p => p.id) }
                  })}
                >
                  {/* Thumbnail placeholder */}
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
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
