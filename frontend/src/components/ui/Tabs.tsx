import * as TabsPrimitive from "@radix-ui/react-tabs";

import { cn } from "../../lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List
      className={cn(
        "inline-flex w-full flex-wrap gap-1.5 rounded-xl border border-white/10 bg-slate-900/70 p-1.5",
        className,
      )}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "inline-flex min-h-8 items-center justify-center rounded-lg px-3 text-xs font-medium text-slate-400 transition data-[state=active]:bg-white data-[state=active]:text-slate-950 data-[state=active]:shadow data-[state=inactive]:hover:bg-white/6 data-[state=inactive]:hover:text-slate-100 md:min-h-9 md:px-3.5 md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({ className, ...props }: TabsPrimitive.TabsContentProps) {
  return <TabsPrimitive.Content className={cn("outline-none", className)} {...props} />;
}
