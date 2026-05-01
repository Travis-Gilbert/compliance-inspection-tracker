import Link from "next/link";

interface StatCardProps {
  label: string;
  value: number | string;
  accentColor?: string;
  subtitle?: string;
  href?: string;
  highlight?: boolean;
}

export default function StatCard({
  label,
  value,
  accentColor = "#D1D5DB",
  subtitle,
  href,
  highlight = false,
}: StatCardProps) {
  const inner = (
    <>
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500">
        <span
          className="h-2 w-2 rounded-full"
          style={{ backgroundColor: accentColor }}
          aria-hidden="true"
        />
        {label}
      </div>
      <div className="mt-1 font-heading text-2xl font-bold text-gray-900">{value}</div>
      {subtitle && <div className="mt-0.5 text-xs text-gray-400">{subtitle}</div>}
    </>
  );

  const baseClasses = `rounded-lg border border-gray-200 p-4 transition-colors ${
    highlight ? "bg-amber-50" : "bg-white"
  }`;

  if (href) {
    return (
      <Link
        href={href}
        className={`${baseClasses} block hover:border-gray-300`}
      >
        {inner}
      </Link>
    );
  }

  return (
    <div className={baseClasses}>
      {inner}
    </div>
  );
}
