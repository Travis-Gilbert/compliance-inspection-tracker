"use client";

import { useRef, useState } from "react";
import { getImageUrl, getMediaUrl, uploadPropertyPhoto } from "@/lib/api";
import type { PhotoSide, Property, PropertyPhoto } from "@/lib/types";

const SIDE_LABELS: Record<PhotoSide, string> = {
  before: "Before",
  after: "After",
};

function PhotoImage({
  photo,
  fallbackUrl,
  fallbackAlt,
  emptyLabel,
}: {
  photo?: PropertyPhoto | null;
  fallbackUrl?: string;
  fallbackAlt: string;
  emptyLabel: string;
}) {
  const src = photo?.image_url ? getMediaUrl(photo.image_url) : fallbackUrl || "";

  return (
    <div className="overflow-hidden rounded border border-gray-200 bg-warm-100">
      {src ? (
        <img
          src={src}
          alt={photo?.caption || fallbackAlt}
          width={640}
          height={480}
          loading="lazy"
          className="aspect-[4/3] w-full object-cover"
        />
      ) : (
        <div className="flex aspect-[4/3] w-full items-center justify-center px-4 text-center text-sm text-gray-500">
          {emptyLabel}
        </div>
      )}
    </div>
  );
}

function PhotoUploadZone({
  property,
  side,
  onUploaded,
}: {
  property: Property;
  side: PhotoSide;
  onUploaded?: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const label = `${SIDE_LABELS[side]} photo for ${property.address}`;

  const handleFile = async (file?: File) => {
    if (!file) return;
    setUploading(true);
    setMessage("");
    try {
      await uploadPropertyPhoto(property.id, { file, side });
      setMessage(`${SIDE_LABELS[side]} photo uploaded.`);
      onUploaded?.();
    } catch (error: unknown) {
      setMessage((error as Error).message || "Photo upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragActive(false);
        handleFile(event.dataTransfer.files[0]);
      }}
      className={`rounded border border-dashed px-3 py-3 text-sm transition-colors ${
        dragActive
          ? "border-civic-green bg-civic-green-pale"
          : "border-gray-300 bg-warm-50"
      }`}
    >
      <div className="font-medium text-gray-800">{label}</div>
      <div className="mt-1 text-xs text-gray-500">
        Drop an image here, or choose a file.
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="rounded border border-civic-green bg-civic-green px-2.5 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-civic-green-light focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-green focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:border-gray-200 disabled:bg-gray-100 disabled:text-gray-400"
        >
          {uploading ? "Uploading…" : "Choose Image"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="sr-only"
          aria-label={label}
          onChange={(event) => handleFile(event.target.files?.[0])}
        />
      </div>
      {message && (
        <div className="mt-2 text-xs text-gray-600" role="status" aria-live="polite">
          {message}
        </div>
      )}
    </div>
  );
}

export function PhotoEvidencePair({
  property,
  onUploaded,
  compact = false,
}: {
  property: Property;
  onUploaded?: () => void;
  compact?: boolean;
}) {
  const beforePhoto = property.primary_before_photo || null;
  const afterPhoto = property.primary_after_photo || null;
  const hasHistoricalStreetView = Boolean(property.streetview_historical_path);
  const hasCurrentStreetView = Boolean(property.streetview_available);

  return (
    <section aria-label={`Photo evidence for ${property.address}`} className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-gray-900">Before</h4>
            <span className="text-xs text-gray-500">
              {property.photo_summary?.before_count || 0} uploaded
            </span>
          </div>
          <PhotoImage
            photo={beforePhoto}
            fallbackUrl={hasHistoricalStreetView ? getImageUrl(property.id, "streetview_historical") : ""}
            fallbackAlt={`Before image for ${property.address}`}
            emptyLabel="No before photo yet"
          />
          {!compact && (
            <PhotoUploadZone property={property} side="before" onUploaded={onUploaded} />
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-gray-900">After</h4>
            <span className="text-xs text-gray-500">
              {property.photo_summary?.after_count || 0} uploaded
            </span>
          </div>
          <PhotoImage
            photo={afterPhoto}
            fallbackUrl={hasCurrentStreetView ? getImageUrl(property.id, "streetview") : ""}
            fallbackAlt={`After image for ${property.address}`}
            emptyLabel="No after photo yet"
          />
          {!compact && (
            <PhotoUploadZone property={property} side="after" onUploaded={onUploaded} />
          )}
        </div>
      </div>
    </section>
  );
}
