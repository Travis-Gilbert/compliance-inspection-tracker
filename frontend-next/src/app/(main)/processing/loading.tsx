const Bone = ({ className = "" }: { className?: string }) => (
  <div className={`animate-pulse bg-gray-200 rounded ${className}`} />
);

export default function ProcessingLoading() {
  return (
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-6">
      <div>
        <Bone className="h-7 w-40 mb-2" />
        <Bone className="h-4 w-72" />
      </div>
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <Bone className="h-5 w-48 mb-3" />
        <Bone className="h-4 w-full mb-2" />
        <Bone className="h-4 w-3/4 mb-4" />
        <div className="flex gap-3">
          <Bone className="h-9 w-36 rounded-md" />
          <Bone className="h-9 w-44 rounded-md" />
        </div>
      </div>
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <Bone className="h-5 w-44 mb-3" />
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Bone key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
