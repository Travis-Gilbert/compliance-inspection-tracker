"use client";

import { FINDINGS } from "@/lib/constants";

interface FindingButtonsProps {
  currentFinding: string | null;
  onAssign: (finding: string) => void;
  disabled?: boolean;
}

export default function FindingButtons({ currentFinding, onAssign, disabled = false }: FindingButtonsProps) {
  return (
    <div role="radiogroup" aria-label="Review findings">
      <div className="flex flex-wrap gap-1.5">
        {FINDINGS.map((finding, index) => {
          const isActive = currentFinding === finding.value;
          return (
            <button
              key={finding.value}
              role="radio"
              aria-checked={isActive}
              onClick={() => onAssign(finding.value)}
              disabled={disabled}
              className="rounded border px-2.5 py-1.5 text-xs font-medium transition-all disabled:opacity-50"
              style={{
                color: isActive ? "#fff" : finding.color,
                background: isActive ? finding.color : finding.bg,
                borderColor: `${finding.color}40`,
              }}
            >
              <span className="mr-0.5 text-[10px] opacity-60">{index + 1}</span>
              {finding.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
