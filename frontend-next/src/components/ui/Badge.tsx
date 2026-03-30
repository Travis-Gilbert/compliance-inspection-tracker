interface BadgeProps {
  label: string;
  color: string;
  bg: string;
  size?: "sm" | "md";
  className?: string;
}

export default function Badge({ label, color, bg, size = "md", className = "" }: BadgeProps) {
  const sizeClasses = size === "sm" ? "text-[11px] px-1.5 py-0.5" : "text-xs px-2 py-0.5";

  return (
    <span
      className={`font-medium rounded ${sizeClasses} ${className}`}
      style={{ color, backgroundColor: bg }}
    >
      {label}
    </span>
  );
}
