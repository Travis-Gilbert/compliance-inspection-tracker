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
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 font-heading text-2xl font-bold text-gray-900">{value}</div>
      {subtitle && <div className="mt-0.5 text-xs text-gray-400">{subtitle}</div>}
    </>
  );

  const baseClasses = `rounded-lg border border-gray-200 border-l-4 p-4 transition-colors ${
    highlight ? "bg-amber-50" : "bg-white"
  }`;

  if (href) {
    return (
      <Link
        href={href}
        className={`${baseClasses} block hover:border-gray-300`}
        style={{ borderLeftColor: accentColor }}
      >
        {inner}
      </Link>
    );
  }

  return (
    <div className={baseClasses} style={{ borderLeftColor: accentColor }}>
      {inner}
    </div>
  );
}
