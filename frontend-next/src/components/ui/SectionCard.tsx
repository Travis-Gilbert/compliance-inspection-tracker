interface SectionCardProps {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
}

export default function SectionCard({
  title,
  subtitle,
  action,
  children,
  className = "",
  noPadding = false,
}: SectionCardProps) {
  return (
    <div className={`rounded-lg border border-gray-200 bg-white ${className}`}>
      {(title || action) && (
        <div className={`flex items-start justify-between ${noPadding ? "px-5 pt-5" : "px-5 pt-5"}`}>
          <div>
            {title && <h3 className="font-heading font-semibold text-gray-900">{title}</h3>}
            {subtitle && <p className="mt-1 text-sm text-gray-600">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <div className={noPadding ? "" : "p-5"}>{children}</div>
    </div>
  );
}
