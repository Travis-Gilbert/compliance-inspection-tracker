"use client";

import { TAX_STATUSES } from "@/lib/constants";

interface TaxInfoCardProps {
  taxStatus: string;
  lastTaxPayment?: string | null;
  taxAmountOwed?: string | number | null;
  homeownerExemption?: boolean;
}

export default function TaxInfoCard({
  taxStatus,
  lastTaxPayment,
  taxAmountOwed,
  homeownerExemption,
}: TaxInfoCardProps) {
  const meta = TAX_STATUSES.find((s) => s.value === taxStatus) || {
    label: taxStatus || "Unknown",
    color: "#757575",
  };

  const borderColor =
    taxStatus === "delinquent"
      ? "border-l-red-600"
      : taxStatus === "current"
        ? "border-l-civic-green"
        : taxStatus === "payment_plan"
          ? "border-l-yellow-600"
          : "border-l-gray-300";

  return (
    <div className={`rounded-lg border border-gray-200 border-l-4 ${borderColor} bg-white p-4`}>
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-3">Tax Information</div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-gray-500">Status</div>
          <div className="mt-0.5 font-medium" style={{ color: meta.color }}>
            {meta.label}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Amount Owed</div>
          <div className="mt-0.5 font-mono font-medium text-gray-900">
            {taxAmountOwed != null ? `$${Number(taxAmountOwed).toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "N/A"}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Last Payment</div>
          <div className="mt-0.5 text-gray-900">
            {lastTaxPayment || "N/A"}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Homeowner Exemption</div>
          <div className="mt-0.5 text-gray-900">
            {homeownerExemption ? "Yes" : "No"}
          </div>
        </div>
      </div>
    </div>
  );
}
