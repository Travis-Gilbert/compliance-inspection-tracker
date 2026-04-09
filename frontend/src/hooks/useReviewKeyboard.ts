import { useEffect } from "react";
import { FINDINGS } from "@/lib/constants";
import type { Property } from "@/lib/types";

interface UseReviewKeyboardOptions {
  properties: Property[];
  focusedIndex: number;
  setFocusedIndex: (fn: (i: number) => number) => void;
  onFindingAssign: (id: number, finding: string) => void;
  onOpenDetail: () => void;
  onEscape: () => void;
  onFocusSearch: () => void;
  enabled: boolean;
}

export function useReviewKeyboard({
  properties,
  focusedIndex,
  setFocusedIndex,
  onFindingAssign,
  onOpenDetail,
  onEscape,
  onFocusSearch,
  enabled,
}: UseReviewKeyboardOptions) {
  useEffect(() => {
    if (!enabled) return;

    const handler = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement).tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) {
        if (event.key === "Escape") {
          (event.target as HTMLElement).blur();
          return;
        }
        return;
      }

      if (event.key === "/" ) {
        event.preventDefault();
        onFocusSearch();
        return;
      }

      if ((event.key === "ArrowDown" || event.key === "j") && properties.length > 0) {
        event.preventDefault();
        setFocusedIndex((i) => Math.min(i + 1, properties.length - 1));
      } else if ((event.key === "ArrowUp" || event.key === "k") && properties.length > 0) {
        event.preventDefault();
        setFocusedIndex((i) => Math.max(i - 1, 0));
      } else if (event.key === "Enter" && focusedIndex >= 0) {
        event.preventDefault();
        onOpenDetail();
      } else if (event.key === "Escape") {
        event.preventDefault();
        onEscape();
      } else if (event.key >= "1" && event.key <= "6" && focusedIndex >= 0) {
        const findingIndex = parseInt(event.key, 10) - 1;
        if (findingIndex < FINDINGS.length) {
          onFindingAssign(properties[focusedIndex].id, FINDINGS[findingIndex].value);
        }
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [enabled, focusedIndex, properties, setFocusedIndex, onFindingAssign, onOpenDetail, onEscape, onFocusSearch]);
}
