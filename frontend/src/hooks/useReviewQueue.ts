import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getPriorityQueue, getStats } from "@/lib/api";
import type { Property, Stats } from "@/lib/types";

export interface ReviewFilters {
  filter: string;
  sort: string;
  search: string;
  program: string;
  detection: string;
  compliance: string;
  tax: string;
}

const PAGE_SIZE = 50;

const DEFAULT_FILTERS: ReviewFilters = {
  filter: "unreviewed",
  sort: "priority",
  search: "",
  program: "all",
  detection: "all",
  compliance: "all",
  tax: "all",
};

export function useReviewQueue() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [properties, setProperties] = useState<Property[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(() =>
    Math.max(0, Number(searchParams.get("page") || 0)),
  );
  const [filters, setFiltersState] = useState<ReviewFilters>(() => ({
    filter: searchParams.get("filter") || DEFAULT_FILTERS.filter,
    sort: searchParams.get("sort") || DEFAULT_FILTERS.sort,
    search: searchParams.get("search") || DEFAULT_FILTERS.search,
    program: searchParams.get("program") || DEFAULT_FILTERS.program,
    detection: searchParams.get("detection") || DEFAULT_FILTERS.detection,
    compliance: searchParams.get("compliance") || DEFAULT_FILTERS.compliance,
    tax: searchParams.get("tax") || DEFAULT_FILTERS.tax,
  }));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  const loadProperties = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {
        filter: filters.filter,
        sort: filters.sort,
        order: filters.sort === "address" ? "asc" : "desc",
        search: filters.search,
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      };
      if (filters.program !== "all") params.program = filters.program;
      if (filters.detection !== "all") params.detection = filters.detection;
      if (filters.compliance !== "all") params.compliance_status = filters.compliance;
      if (filters.tax !== "all") params.tax_status = filters.tax;

      const [queue, statsSummary] = await Promise.all([
        getPriorityQueue(params),
        getStats(),
      ]);
      setProperties(queue.properties || []);
      setTotalCount(queue.total || 0);
      setStats(statsSummary);
    } catch (err: unknown) {
      setError((err as Error).message || "Could not load the review queue.");
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    loadProperties();
  }, [loadProperties]);

  // Sync state to URL search params
  useEffect(() => {
    const nextParams = new URLSearchParams();
    if (filters.filter !== DEFAULT_FILTERS.filter) nextParams.set("filter", filters.filter);
    if (filters.sort !== DEFAULT_FILTERS.sort) nextParams.set("sort", filters.sort);
    if (filters.search) nextParams.set("search", filters.search);
    if (filters.program !== "all") nextParams.set("program", filters.program);
    if (filters.detection !== "all") nextParams.set("detection", filters.detection);
    if (filters.compliance !== "all") nextParams.set("compliance", filters.compliance);
    if (filters.tax !== "all") nextParams.set("tax", filters.tax);
    if (page > 0) nextParams.set("page", String(page));
    const qs = nextParams.toString();
    router.replace(`/review${qs ? `?${qs}` : ""}`, { scroll: false });
  }, [filters, page, router]);

  // Reset page when filters change
  useEffect(() => {
    setPage(0);
  }, [filters]);

  const setFilters = useCallback((partial: Partial<ReviewFilters>) => {
    setFiltersState((prev) => ({ ...prev, ...partial }));
  }, []);

  const refresh = useCallback(async () => {
    await loadProperties();
  }, [loadProperties]);

  return {
    properties,
    totalCount,
    totalPages,
    stats,
    loading,
    error,
    page,
    pageSize: PAGE_SIZE,
    filters,
    setFilters,
    setPage,
    refresh,
  };
}
