import * as ToastPrimitive from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import { X } from "lucide-react";

import { cn } from "../../lib/utils";

type ToastTone = "info" | "success" | "warning" | "danger";

type ToastItem = {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
};

type ToastInput = {
  title: string;
  description?: string;
  tone?: ToastTone;
};

type ToastContextValue = {
  pushToast: (toast: ToastInput) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const toneClasses: Record<ToastTone, string> = {
  info: "border-blue-400/25 bg-slate-900/95",
  success: "border-emerald-400/25 bg-slate-900/95",
  warning: "border-amber-400/25 bg-slate-900/95",
  danger: "border-red-400/25 bg-slate-900/95",
};

export function ToastProvider({ children }: PropsWithChildren) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const pushToast = useCallback((toast: ToastInput) => {
    setToasts((current) => [
      ...current,
      {
        id: Date.now() + Math.floor(Math.random() * 1000),
        tone: toast.tone ?? "info",
        title: toast.title,
        description: toast.description,
      },
    ]);
  }, []);

  const contextValue = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={contextValue}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {toasts.map((toast) => (
          <ToastPrimitive.Root
            key={toast.id}
            open
            duration={4000}
            onOpenChange={(open) => {
              if (!open) {
                setToasts((current) => current.filter((item) => item.id !== toast.id));
              }
            }}
            className={cn(
              "panel grid w-[360px] gap-2 rounded-3xl border px-5 py-4 shadow-2xl",
              toneClasses[toast.tone],
            )}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <ToastPrimitive.Title className="text-sm font-semibold text-slate-50">
                  {toast.title}
                </ToastPrimitive.Title>
                {toast.description ? (
                  <ToastPrimitive.Description className="text-sm leading-6 text-slate-400">
                    {toast.description}
                  </ToastPrimitive.Description>
                ) : null}
              </div>
              <ToastPrimitive.Close className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-slate-900/80 text-slate-300 transition hover:bg-slate-800 hover:text-slate-100">
                <X className="h-4 w-4" />
              </ToastPrimitive.Close>
            </div>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[80] flex max-w-[100vw] flex-col gap-3 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return context;
}
