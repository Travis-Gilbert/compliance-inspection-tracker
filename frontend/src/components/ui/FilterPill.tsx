interface FilterPillProps {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;
}

export default function FilterPill({ label, active, onClick, count }: FilterPillProps) {
  return (
    <button
      onClick={onClick}
      className={`text-xs font-medium rounded px-3 py-1.5 transition-colors ${
        active
          ? "border border-civic-green/20 bg-civic-green-pale text-civic-green"
          : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
      }`}
    >
      {label}
      {count != null && ` (${count})`}
    </button>
  );
}
