"use client";

const Bone = ({ className = "" }: { className?: string }) => (
  <div className={`animate-pulse bg-gray-200 rounded ${className}`} />
);

export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Bone className="h-7 w-36 mb-2" />
        <Bone className="h-4 w-64" />
      </div>
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <Bone className="h-5 w-32" />
          <Bone className="h-4 w-10" />
        </div>
        <Bone className="h-3 w-full rounded-full" />
        <div className="flex justify-between mt-2">
          <Bone className="h-3 w-20" />
          <Bone className="h-3 w-20" />
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-4">
            <Bone className="h-3 w-20 mb-2" />
            <Bone className="h-7 w-12" />
          </div>
        ))}
      </div>
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <Bone className="h-5 w-40 mb-3" />
        <Bone className="h-4 w-full mb-2" />
        <Bone className="h-4 w-3/4 mb-4" />
        <Bone className="h-9 w-44 rounded-md" />
      </div>
    </div>
  );
}

export function ReviewQueueSkeleton() {
  return (
    <div className="space-y-4">
      <div>
        <Bone className="h-7 w-36 mb-2" />
        <Bone className="h-4 w-80" />
      </div>
      <div className="flex gap-2">
        {[1, 2, 3, 4].map((i) => (
          <Bone key={i} className="h-7 w-20 rounded" />
        ))}
        <Bone className="h-7 w-32 rounded ml-2" />
      </div>
      <div className="space-y-2">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="bg-white border border-gray-200 rounded-lg p-3 flex items-center gap-3">
            <Bone className="w-20 h-14 rounded flex-shrink-0" />
            <div className="flex-1">
              <Bone className="h-4 w-48 mb-2" />
              <div className="flex gap-2">
                <Bone className="h-3 w-24" />
                <Bone className="h-3 w-20" />
              </div>
            </div>
            <Bone className="h-6 w-20 rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function PropertyDetailSkeleton() {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <Bone className="h-7 w-24 rounded" />
        <div className="flex gap-2">
          <Bone className="h-7 w-14 rounded" />
          <Bone className="h-4 w-12" />
          <Bone className="h-7 w-14 rounded" />
        </div>
      </div>
      <div>
        <Bone className="h-6 w-64 mb-2" />
        <div className="flex gap-3">
          <Bone className="h-4 w-28" />
          <Bone className="h-4 w-24" />
          <Bone className="h-5 w-24 rounded" />
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-100">
            <Bone className="h-4 w-20" />
          </div>
          <Bone className="w-full aspect-video" />
        </div>
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-100">
            <Bone className="h-4 w-16" />
          </div>
          <Bone className="w-full aspect-video" />
        </div>
      </div>
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <Bone className="h-3 w-32 mb-3" />
        <div className="flex gap-2 flex-wrap">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Bone key={i} className="h-8 w-28 rounded" />
          ))}
        </div>
      </div>
    </div>
  );
}
