"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getGalleryProperties } from "@/lib/api";
import type { ComplianceOutcome, GalleryResponse, Property } from "@/lib/types";
import { PhotoEvidencePair } from "@/components/evidence/PhotoEvidence";
import InlineNotice from "@/components/InlineNotice";

const OUTCOME_LABELS: Record<ComplianceOutcome, string> = {
  pending: "Pending review",
  compliant: "Compliant",
  non_compliant: "Non-compliant",
  in_progress: "In progress",
  needs_inspection: "Needs inspection",
  unknown: "Unknown",
};

const OUTCOME_STYLES: Record<ComplianceOutcome, string> = {
  pending: "border-gray-200 bg-gray-100 text-gray-700",
  compliant: "border-civic-green/20 bg-civic-green-pale text-civic-green",
  non_compliant: "border-orange-200 bg-orange-50 text-orange-700",
  in_progress: "border-civic-blue/20 bg-civic-blue-pale text-civic-blue",
  needs_inspection: "border-purple-200 bg-purple-50 text-purple-700",
  unknown: "border-gray-200 bg-gray-100 text-gray-700",
};

const SORT_OPTIONS = [
  { value: "address", label: "Address" },
  { value: "program", label: "Program" },
  { value: "closing_date", label: "Closing date" },
  { value: "review_status", label: "Review status" },
  { value: "photo_completeness", label: "Photo completeness" },
  { value: "compliance_outcome", label: "Compliance outcome" },
];

function GalleryCard({
  property,
  selected,
  onUploaded,
}: {
  property: Property;
  selected: boolean;
  onUploaded: () => void;
}) {
  const outcome = property.manual_compliance_outcome || "pending";
  const summary = property.photo_summary;

  return (
    <article
      id={`property-${property.id}`}
      className={`rounded border bg-white p-4 transition-colors ${
        selected ? "border-civic-green ring-2 ring-civic-green/20" : "border-gray-200"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-heading text-lg font-semibold leading-tight text-gray-900">
            {property.address}
          </h3>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
            {property.parcel_id && <span>Parcel: {property.parcel_id}</span>}
            {property.program && <span>{property.program}</span>}
            {property.closing_date && <span>Closed: {property.closing_date}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className={`rounded border px-2 py-1 font-medium ${OUTCOME_STYLES[outcome]}`}>
            {OUTCOME_LABELS[outcome]}
          </span>
          <span className="rounded border border-gray-200 bg-warm-50 px-2 py-1 font-medium text-gray-700">
            {summary?.is_complete ? "Before and after ready" : "Photo set incomplete"}
          </span>
        </div>
      </div>

      <div className="mt-4">
        <PhotoEvidencePair property={property} onUploaded={onUploaded} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 pt-3 text-xs text-gray-500">
        <span>
          {summary?.before_count || 0} before, {summary?.after_count || 0} after
        </span>
        <Link
          href={`/property/${property.id}`}
          className="rounded border border-gray-200 px-3 py-1.5 font-medium text-gray-700 transition-colors hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-green focus-visible:ring-offset-2"
        >
          Open Record
        </Link>
      </div>
    </article>
  );
}

function BeforeAfterInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("selected");
  const cardRefs = useRef<Record<string, HTMLElement | null>>({});
  const [properties, setProperties] = useState<Property[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState(searchParams.get("status") || "all");
  const [photo, setPhoto] = useState(searchParams.get("photo") || "all");
  const [sort, setSort] = useState(searchParams.get("sort") || "address");
  const [order, setOrder] = useState(searchParams.get("order") || "asc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const params = useMemo(() => ({
    status,
    photo,
    sort,
    order,
    limit: "200",
  }), [status, photo, sort, order]);

  const loadGallery = async () => {
    setLoading(true);
    setError("");
    try {
      const response: GalleryResponse = await getGalleryProperties(params);
      setProperties(response.properties || []);
      setTotal(response.total || 0);
    } catch (err: unknown) {
      setError((err as Error).message || "Could not load the gallery.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGallery();
  }, [params]);

  useEffect(() => {
    const nextParams = new URLSearchParams();
    if (selectedId) nextParams.set("selected", selectedId);
    if (status !== "all") nextParams.set("status", status);
    if (photo !== "all") nextParams.set("photo", photo);
    if (sort !== "address") nextParams.set("sort", sort);
    if (order !== "asc") nextParams.set("order", order);
    const qs = nextParams.toString();
    router.replace(`/before-after${qs ? `?${qs}` : ""}`, { scroll: false });
  }, [order, photo, router, selectedId, sort, status]);

  useEffect(() => {
    if (!selectedId) return;
    const node = cardRefs.current[selectedId];
    if (node) {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      node.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
    }
  }, [selectedId, properties]);

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-heading text-2xl font-bold text-gray-900">Before and After</h2>
          <p className="mt-1 max-w-2xl text-sm text-gray-600">
            Review uploaded evidence by property. Each upload target names the destination address before staff choose a file.
          </p>
        </div>
        <Link
          href="/review"
          className="rounded border border-civic-green bg-civic-green px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-civic-green-light focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-green focus-visible:ring-offset-2"
        >
          Open Review Queue
        </Link>
      </div>

      <section aria-label="Gallery controls" className="rounded border border-gray-200 bg-white p-3">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-xs font-medium text-gray-600">
            Review status
            <select
              name="gallery-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm text-gray-900"
            >
              <option value="all">All statuses</option>
              <option value="pending">Pending review</option>
              <option value="reviewed">Reviewed</option>
              <option value="compliant">Compliant</option>
              <option value="non_compliant">Non-compliant</option>
              <option value="needs_inspection">Needs inspection</option>
            </select>
          </label>

          <label className="text-xs font-medium text-gray-600">
            Photo completeness
            <select
              name="gallery-photo"
              value={photo}
              onChange={(event) => setPhoto(event.target.value)}
              className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm text-gray-900"
            >
              <option value="all">All photo states</option>
              <option value="complete">Before and after ready</option>
              <option value="missing_before">Missing before</option>
              <option value="missing_after">Missing after</option>
              <option value="has_uploads">Has uploads</option>
            </select>
          </label>

          <label className="text-xs font-medium text-gray-600">
            Sort by
            <select
              name="gallery-sort"
              value={sort}
              onChange={(event) => setSort(event.target.value)}
              className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm text-gray-900"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>

          <label className="text-xs font-medium text-gray-600">
            Direction
            <select
              name="gallery-order"
              value={order}
              onChange={(event) => setOrder(event.target.value)}
              className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-2 text-sm text-gray-900"
            >
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </label>
        </div>
      </section>

      <div className="flex items-center justify-between text-sm text-gray-600">
        <span>{total} properties in gallery</span>
        {loading && <span>Refreshing…</span>}
      </div>

      {error && (
        <InlineNotice
          tone="error"
          title="Gallery unavailable"
          message={error}
          actionLabel="Retry"
          onAction={loadGallery}
        />
      )}

      {!loading && !error && properties.length === 0 && (
        <div className="rounded border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
          No properties match this gallery view.
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {properties.map((property) => (
          <div
            key={property.id}
            ref={(node) => {
              cardRefs.current[String(property.id)] = node;
            }}
          >
            <GalleryCard
              property={property}
              selected={selectedId === String(property.id)}
              onUploaded={loadGallery}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function BeforeAfterPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-gray-500">Loading gallery…</div>}>
      <BeforeAfterInner />
    </Suspense>
  );
}
