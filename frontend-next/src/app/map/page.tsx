"use client";

import dynamic from "next/dynamic";

const LeadershipMap = dynamic(() => import("@/components/LeadershipMap"), {
  ssr: false,
  loading: () => (
    <div className="fixed inset-0 bg-warm-50 flex items-center justify-center">
      <div className="text-sm text-gray-500">Loading map...</div>
    </div>
  ),
});

export default function MapPage() {
  return <LeadershipMap />;
}
