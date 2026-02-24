import { useState, useEffect } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { getProperty, updateProperty, getImageUrl } from "../utils/api";
import { FINDINGS, DETECTION_LABELS } from "../utils/constants";
import { PropertyDetailSkeleton } from "../components/LoadingSkeleton";

export default function PropertyDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [property, setProperty] = useState(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  // Queue navigation: get prev/next IDs from route state
  const queueIds = location.state?.queueIds || [];
  const currentIndex = queueIds.indexOf(Number(id));
  const prevId = currentIndex > 0 ? queueIds[currentIndex - 1] : null;
  const nextId = currentIndex >= 0 && currentIndex < queueIds.length - 1 ? queueIds[currentIndex + 1] : null;

  const navigateTo = (targetId) => {
    navigate(`/property/${targetId}`, { state: { queueIds } });
  };

  useEffect(() => {
    getProperty(id).then(p => {
      setProperty(p);
      setNotes(p.notes || "");
    }).catch(() => navigate("/review"));
  }, [id, navigate]);

  const handleFinding = async (finding) => {
    setSaving(true);
    try {
      const updated = await updateProperty(id, {
        finding: property.finding === finding ? "" : finding,
        notes,
      });
      setProperty(updated);
    } catch (e) {
      console.error("Failed to update:", e);
    }
    setSaving(false);
  };

  const handleSaveNotes = async () => {
    setSaving(true);
    try {
      const updated = await updateProperty(id, { notes });
      setProperty(updated);
    } catch (e) {
      console.error("Failed to save notes:", e);
    }
    setSaving(false);
  };

  // Keyboard shortcuts: arrows for prev/next, 1-6 for findings, Esc for back
  useEffect(() => {
    const handler = (e) => {
      // Skip when typing in inputs or textareas
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (saving) return;

      if (e.key === "ArrowLeft" && prevId) {
        e.preventDefault();
        navigateTo(prevId);
      } else if (e.key === "ArrowRight" && nextId) {
        e.preventDefault();
        navigateTo(nextId);
      } else if (e.key === "Escape") {
        navigate("/review");
      } else if (e.key >= "1" && e.key <= "6" && property) {
        const idx = parseInt(e.key) - 1;
        if (idx < FINDINGS.length) {
          handleFinding(FINDINGS[idx].value);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [prevId, nextId, saving, property, navigate, notes]);

  if (!property) return <PropertyDetailSkeleton />;

  const detection = DETECTION_LABELS[property.detection_label];
  const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${encodeURIComponent(property.formatted_address || property.address + ", Flint, MI")}`;
  const propertyPortalUrl = `https://www.flintpropertyportal.com/search?q=${encodeURIComponent(property.address)}`;
  const googleMapsUrl = `https://www.google.com/maps/search/${encodeURIComponent(property.formatted_address || property.address + ", Flint, MI")}`;

  return (
    <div className="space-y-5">
      {/* Navigation bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate("/review")}
          className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded border border-gray-200 hover:bg-gray-50"
        >
          Back to Queue
        </button>
        {queueIds.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => prevId && navigateTo(prevId)}
              disabled={!prevId}
              className={`text-xs font-medium px-3 py-1.5 rounded border transition-colors ${
                prevId
                  ? "text-gray-700 border-gray-200 hover:bg-gray-50"
                  : "text-gray-300 border-gray-100 cursor-not-allowed"
              }`}
            >
              Prev
            </button>
            <span className="text-xs text-gray-400">
              {currentIndex + 1} / {queueIds.length}
            </span>
            <button
              onClick={() => nextId && navigateTo(nextId)}
              disabled={!nextId}
              className={`text-xs font-medium px-3 py-1.5 rounded border transition-colors ${
                nextId
                  ? "text-white bg-civic-green border-civic-green hover:bg-civic-green-light"
                  : "text-gray-300 border-gray-100 cursor-not-allowed"
              }`}
            >
              Next
            </button>
          </div>
        )}
      </div>

      <div>
        <h2 className="font-heading text-xl font-bold text-gray-900">{property.address}</h2>
        <div className="flex gap-3 mt-1.5 flex-wrap text-xs text-gray-500">
          {property.parcel_id && <span>Parcel: {property.parcel_id}</span>}
          {property.buyer_name && <span>Buyer: {property.buyer_name}</span>}
          {property.program && (
            <span className="font-medium text-civic-blue bg-civic-blue-pale px-1.5 py-0.5 rounded">
              {property.program}
            </span>
          )}
          {property.closing_date && <span>Closed: {property.closing_date}</span>}
          {property.commitment && <span>Committed: {property.commitment}</span>}
        </div>
      </div>

      {/* Detection info */}
      {detection && property.detection_label !== "unprocessed" && (
        <div
          className="rounded-lg border px-4 py-3 flex items-center gap-3"
          style={{ borderColor: detection.color + "40", background: detection.bg }}
        >
          <span className="font-medium text-sm" style={{ color: detection.color }}>
            Smart Detection: {detection.label}
          </span>
          {property.detection_score != null && (
            <span className="text-xs text-gray-500">
              Score: {property.detection_score}
            </span>
          )}
        </div>
      )}

      {/* Imagery */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">Street View</span>
            {property.streetview_date && (
              <span className="text-xs text-gray-400">Captured: {property.streetview_date}</span>
            )}
          </div>
          {property.streetview_available ? (
            <img
              src={getImageUrl(property.id, "streetview")}
              alt="Street View"
              className="w-full aspect-video object-cover"
            />
          ) : (
            <div className="w-full aspect-video bg-gray-50 flex items-center justify-center text-gray-400 text-sm">
              No Street View available
            </div>
          )}
        </div>

        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-100">
            <span className="text-xs font-medium text-gray-700">Satellite</span>
          </div>
          {property.satellite_path ? (
            <img
              src={getImageUrl(property.id, "satellite")}
              alt="Satellite"
              className="w-full aspect-video object-cover"
            />
          ) : (
            <div className="w-full aspect-video bg-gray-50 flex items-center justify-center text-gray-400 text-sm">
              No satellite image
            </div>
          )}
        </div>
      </div>

      {/* External research links */}
      <div className="flex gap-2 flex-wrap">
        <a
          href={streetViewUrl} target="_blank" rel="noopener noreferrer"
          className="text-xs font-medium text-white bg-civic-green px-3 py-2 rounded-md hover:bg-civic-green-light transition-colors"
        >
          Open Street View (Interactive)
        </a>
        <a
          href={propertyPortalUrl} target="_blank" rel="noopener noreferrer"
          className="text-xs font-medium text-white bg-civic-blue px-3 py-2 rounded-md hover:bg-civic-blue-light transition-colors"
        >
          Flint Property Portal
        </a>
        <a
          href={googleMapsUrl} target="_blank" rel="noopener noreferrer"
          className="text-xs font-medium text-gray-600 bg-gray-100 px-3 py-2 rounded-md hover:bg-gray-200 transition-colors"
        >
          Google Maps
        </a>
      </div>

      {/* Finding selector */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-gray-500 uppercase tracking-wide font-medium">
            Record Your Finding
          </span>
          <span className="text-xs text-gray-400 hidden md:inline">
            Keys: 1-6 findings, arrows prev/next, Esc back
          </span>
        </div>
        <div className="flex gap-2 flex-wrap">
          {FINDINGS.map((f, i) => (
            <button
              key={f.value}
              onClick={() => handleFinding(f.value)}
              disabled={saving}
              className="text-xs font-medium px-3 py-2 rounded border transition-all"
              style={{
                color: property.finding === f.value ? "#fff" : f.color,
                background: property.finding === f.value ? f.color : f.bg,
                borderColor: f.color + "40",
                opacity: property.finding && property.finding !== f.value ? 0.5 : 1,
              }}
            >
              <span className="hidden md:inline text-[10px] opacity-60 mr-1">{i + 1}</span>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Notes */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="text-xs text-gray-500 uppercase tracking-wide font-medium mb-2">
          Notes
        </div>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Street View shows recent renovation work. New siding visible. Image dated June 2025."
          rows={3}
          className="w-full text-sm border border-gray-200 rounded-md p-2.5 resize-y font-body"
        />
        <button
          onClick={handleSaveNotes}
          disabled={saving || notes === (property.notes || "")}
          className={`mt-2 text-xs font-medium px-4 py-1.5 rounded transition-colors ${
            saving || notes === (property.notes || "")
              ? "bg-gray-100 text-gray-400 cursor-not-allowed"
              : "bg-civic-green text-white hover:bg-civic-green-light"
          }`}
        >
          {saving ? "Saving..." : "Save Notes"}
        </button>
      </div>

      {/* Metadata */}
      <div className="text-xs text-gray-400 flex gap-4 flex-wrap">
        {property.reviewed_at && <span>Reviewed: {new Date(property.reviewed_at).toLocaleString()}</span>}
        {property.geocoded_at && <span>Geocoded: {new Date(property.geocoded_at).toLocaleString()}</span>}
        {property.formatted_address && <span>Resolved: {property.formatted_address}</span>}
        {property.latitude && <span>{property.latitude.toFixed(5)}, {property.longitude.toFixed(5)}</span>}
      </div>
    </div>
  );
}
