import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white shadow-lg shadow-blue-950/30 hover:from-blue-500 hover:to-violet-400",
  secondary:
    "border-white/10 bg-slate-800/75 text-slate-100 hover:border-white/20 hover:bg-slate-700/80",
  ghost: "border-transparent bg-transparent text-slate-200 hover:bg-slate-800/70 hover:text-slate-100",
  danger: "border-red-400/25 bg-red-500/12 text-red-100 hover:bg-red-500/18",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "min-h-9 px-3 text-sm",
  md: "min-h-10 px-4 text-sm",
  lg: "min-h-11 px-5 text-[0.95rem]",
};

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { className, variant = "secondary", size = "md", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-2xl border font-medium transition duration-150 disabled:cursor-not-allowed disabled:opacity-60",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  );
});
