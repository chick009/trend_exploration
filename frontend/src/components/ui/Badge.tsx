import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "accent";

type Props = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

const toneClasses: Record<BadgeTone, string> = {
  neutral: "border-white/10 bg-slate-800/70 text-slate-200",
  info: "border-blue-400/25 bg-blue-500/12 text-blue-100",
  success: "border-emerald-400/25 bg-emerald-500/12 text-emerald-100",
  warning: "border-amber-400/25 bg-amber-500/12 text-amber-100",
  danger: "border-red-400/25 bg-red-500/12 text-red-100",
  accent: "border-violet-400/25 bg-violet-500/12 text-violet-100",
};

export function Badge({ className, tone = "neutral", ...props }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em]",
        toneClasses[tone],
        className,
      )}
      {...props}
    />
  );
}
