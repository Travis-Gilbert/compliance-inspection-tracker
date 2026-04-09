"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { batchUpdateProperties, getProperty, updateProperty } from "@/lib/api";
import { FINDINGS } from "@/lib/constants";
import type { Property } from "@/lib/types";
import { useReviewQueue } from "@/hooks/useReviewQueue";
import { useReviewKeyboard } from "@/hooks/useReviewKeyboard";
import InlineNotice from "@/components/InlineNotice";
import { ReviewQueueSkeleton } from "@/components/LoadingSkeleton";
import FilterBar from "@/components/review/FilterBar";
import FastLanes from "@/components/review/FastLanes";
import PropertyRow from "@/components/review/PropertyRow";
import PropertyDetailPanel from "@/components/review/PropertyDetailPanel";
import BatchActionBar from "@/components/review/BatchActionBar";
import EmptyState from "@/components/ui/EmptyState";

function ReviewQueueInner() {
  const router = useRouter();
  const {
    properties,
    totalCount,
    totalPages,
    stats,
    loading,
    error: loadError,
    page,
    pageSize,
    filters,
    setFilters,
    setPage,
    refresh,
  } = useReviewQueue();

  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [selectedProperty, setSelectedProperty] = useState<Property | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<{
    tone: "info" | "success" | "warning" | "error";
    title: string;
    message: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [notes, setNotes] = useState("");
  const [detailFocused, setDetailFocused] = useState(false);

  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);

  // When focused index changes, update selected property
  useEffect(() => {
    if (focusedIndex >= 0 && focusedIndex < properties.length) {
      const prop = properties[focusedIndex];
      setSelectedId(prop.id);
    }
  }, [focusedIndex, properties]);

  // Load full property data when selectedId changes
  useEffect(() => {
    if (selectedId == null) {
      setSelectedProperty(null);
      return;
    }
    let cancelled = false;
    getProperty(selectedId).then((data: Property) => {
      if (!cancelled) {
        setSelectedProperty(data);
        setNotes(data.notes || "");
      }
    }).catch(() => {
      // Use the list data as fallback
      if (!cancelled) {
        const fromList = properties.find((p) => p.id === selectedId);
        if (fromList) {
          setSelectedProperty(fromList);
          setNotes(fromList.notes || "");
        }
      }
    });
    return () => { cancelled = true; };
  }, [selectedId, properties]);

  // Reset selection when filters/page change
  useEffect(() => {
    setSelected(new Set());
    setFocusedIndex(-1);
    setSelectedId(null);
    setSelectedProperty(null);
    setDetailFocused(false);
  }, [filters]);

  useEffect(() => {
    setSelected(new Set());
    setFocusedIndex(-1);
    setDetailFocused(false);
  }, [page]);

  // Scroll focused row into view
  useEffect(() => {
    if (focusedIndex >= 0 && rowRefs.current[focusedIndex]) {
      rowRefs.current[focusedIndex]!.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [focusedIndex]);

  const handleSelectProperty = useCallback((index: number) => {
    setFocusedIndex(index);
    setDetailFocused(false);
  }, []);

  const handleFindingAssign = useCallback(async (id: number, finding: string) => {
    setSaving(true);
    setNotice(null);
    try {
      const prop = properties.find((p) => p.id === id);
      const nextFinding = prop?.finding === finding ? "" : finding;
      const updated = await updateProperty(id, { finding: nextFinding, notes });
      setSelectedProperty(updated);
      setNotes(updated.notes || "");

      const findingLabel = FINDINGS.find((f) => f.value === finding)?.label || finding;
      setNotice({
        tone: "success",
        title: nextFinding ? `Saved: ${findingLabel}` : "Finding cleared",
        message: nextFinding ? "Moved to next." : "",
      });

      // Auto-advance
      if (nextFinding && focusedIndex < properties.length - 1) {
        setFocusedIndex((i) => i + 1);
      }

      // Auto-dismiss toast
      setTimeout(() => setNotice(null), 2000);
      await refresh();
    } catch (err: unknown) {
      setNotice({
        tone: "error",
        title: "Update failed",
        message: (err as Error).message || "The finding could not be saved.",
      });
    } finally {
      setSaving(false);
    }
  }, [properties, notes, focusedIndex, refresh]);

  const handleSaveNotes = useCallback(async () => {
    if (!selectedProperty) return;
    setSaving(true);
    setNotice(null);
    try {
      const updated = await updateProperty(selectedProperty.id, { notes });
      setSelectedProperty(updated);
      setNotes(updated.notes || "");
      setNotice({ tone: "success", title: "Notes saved", message: "" });
      setTimeout(() => setNotice(null), 2000);
    } catch (err: unknown) {
      setNotice({ tone: "error", title: "Save failed", message: (err as Error).message });
    } finally {
      setSaving(false);
    }
  }, [selectedProperty, notes]);

  const toggleCheck = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleBatchUpdate = useCallback(async (finding: string) => {
    const label = FINDINGS.find((f) => f.value === finding)?.label || finding;
    if (!window.confirm(`Mark ${selected.size} properties as "${label}"?`)) return;
    setNotice(null);
    try {
      await batchUpdateProperties([...selected], finding);
      setSelected(new Set());
      await refresh();
      setNotice({ tone: "success", title: "Batch update complete", message: `${selected.size} properties updated.` });
    } catch (err: unknown) {
      setNotice({ tone: "error", title: "Batch update failed", message: (err as Error).message });
    }
  }, [selected, refresh]);

  useReviewKeyboard({
    properties,
    focusedIndex,
    setFocusedIndex,
    onFindingAssign: handleFindingAssign,
    onOpenDetail: () => setDetailFocused(true),
    onEscape: () => {
      if (detailFocused) {
        setDetailFocused(false);
        listRef.current?.focus();
      }
    },
    onFocusSearch: () => searchRef.current?.focus(),
    enabled: !detailFocused,
  });

  return (
    <div className="flex h-screen">
      {/* Left panel: property list */}
      <div className="w-full lg:w-[400px] lg:flex-shrink-0 flex flex-col border-r border-gray-200 bg-white">
        {/* Header */}
        <div className="px-3 py-3 border-b border-gray-100">
          <h2 className="font-heading text-lg font-bold text-gray-900">Review Queue</h2>
          {stats && (
            <div className="mt-1 flex gap-3 text-[11px] text-gray-500">
              <span>{totalCount} in view</span>
              <span className="text-civic-green">{stats.reviewed} with manual findings</span>
              <span>{stats.unreviewed} awaiting manual review</span>
            </div>
          )}
        </div>

        {/* Notice (toast) */}
        {notice && (
          <div className="px-3 pt-2">
            <InlineNotice tone={notice.tone} title={notice.title} message={notice.message} />
          </div>
        )}

        {loadError && (
          <div className="px-3 pt-2">
            <InlineNotice tone="error" title="Queue unavailable" message={loadError} actionLabel="Retry" onAction={refresh} />
          </div>
        )}

        {/* Fast lanes */}
        <FastLanes stats={stats} onApplyLane={(partial) => setFilters(partial)} />

        {/* Filter bar */}
        <FilterBar ref={searchRef} filters={filters} onChange={setFilters} />

        {/* Scrollable property list */}
        <div ref={listRef} role="listbox" aria-label="Properties" className="flex-1 overflow-y-auto" tabIndex={-1}>
          {loading ? (
            <div className="p-4">
              <ReviewQueueSkeleton />
            </div>
          ) : properties.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="No properties match this view"
                message="Try clearing a filter, or import more properties from the Import page."
                actionLabel="Import Properties"
                actionHref="/import"
              />
            </div>
          ) : (
            properties.map((property, index) => (
              <div
                key={property.id}
                ref={(el) => { rowRefs.current[index] = el; }}
              >
                <PropertyRow
                  property={property}
                  isSelected={selectedId === property.id}
                  isFocused={focusedIndex === index}
                  isChecked={selected.has(property.id)}
                  onSelect={() => handleSelectProperty(index)}
                  onCheck={() => toggleCheck(property.id)}
                />
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        {totalCount > pageSize && (
          <div className="flex items-center justify-between border-t border-gray-100 px-3 py-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="rounded border border-gray-200 px-2.5 py-1 text-xs font-medium hover:bg-gray-50 disabled:opacity-40"
            >
              Prev
            </button>
            <span className="text-[11px] text-gray-500">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={(page + 1) * pageSize >= totalCount}
              className="rounded border border-civic-green px-2.5 py-1 text-xs font-medium text-civic-green hover:bg-civic-green-pale disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}

        {/* Batch action bar */}
        <BatchActionBar
          selectedCount={selected.size}
          onBatchUpdate={handleBatchUpdate}
          onClear={() => setSelected(new Set())}
        />
      </div>

      {/* Right panel: property detail (desktop only) */}
      <div className="hidden lg:flex flex-1 min-w-0 flex-col overflow-y-auto bg-white">
        {selectedProperty ? (
          <PropertyDetailPanel
            property={selectedProperty}
            notes={notes}
            onNotesChange={setNotes}
            onSaveNotes={handleSaveNotes}
            onFindingAssign={(finding) => handleFindingAssign(selectedProperty.id, finding)}
            saving={saving}
            notice={notice}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-8 text-center">
            <div>
              <p className="text-sm text-gray-500">Select a property from the list to begin review.</p>
              <p className="mt-2 text-xs text-gray-400">Use j/k to navigate, 1-6 to assign findings.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ReviewQueuePage() {
  return (
    <Suspense fallback={<ReviewQueueSkeleton />}>
      <ReviewQueueInner />
    </Suspense>
  );
}
