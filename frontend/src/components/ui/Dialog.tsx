import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  className,
  children,
  showClose = true,
  ...props
}: DialogPrimitive.DialogContentProps & { showClose?: boolean }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-slate-950/75 backdrop-blur-sm" />
      <DialogPrimitive.Content
        className={cn(
          "panel fixed left-1/2 top-1/2 z-50 w-[min(92vw,1100px)] max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[28px] p-0 focus:outline-none",
          className,
        )}
        {...props}
      >
        {children}
        {showClose ? (
          <DialogPrimitive.Close className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-slate-900/80 text-slate-200 transition hover:bg-slate-800 hover:text-slate-50">
            <X className="h-4 w-4" />
          </DialogPrimitive.Close>
        ) : null}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-b border-white/10 px-6 py-5", className)} {...props} />;
}

export function DialogBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("max-h-[calc(88vh-140px)] overflow-y-auto px-6 py-5", className)} {...props} />;
}

export function DialogFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-t border-white/10 px-6 py-4", className)} {...props} />;
}

export function DialogTitle({ className, ...props }: DialogPrimitive.DialogTitleProps) {
  return <DialogPrimitive.Title className={cn("text-xl font-semibold text-slate-50", className)} {...props} />;
}

export function DialogDescription({ className, ...props }: DialogPrimitive.DialogDescriptionProps) {
  return <DialogPrimitive.Description className={cn("mt-2 text-sm text-slate-400", className)} {...props} />;
}

type SimpleDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
};

export function SimpleDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: SimpleDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={className}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <DialogBody>{children}</DialogBody>
        {footer ? <DialogFooter>{footer}</DialogFooter> : null}
      </DialogContent>
    </Dialog>
  );
}
