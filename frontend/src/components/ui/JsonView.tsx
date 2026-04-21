import { Code2 } from "lucide-react";

import { Button } from "./Button";
import { DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle, Dialog, DialogTrigger } from "./Dialog";

type Props = {
  title?: string;
  description?: string;
  value: unknown;
  triggerLabel?: string;
};

export function JsonView({ title = "JSON payload", description, value, triggerLabel = "View JSON" }: Props) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="justify-start px-0 text-blue-200 hover:bg-transparent hover:text-blue-100">
          <Code2 className="h-4 w-4" />
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[min(92vw,900px)]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <DialogBody>
          <pre className="overflow-x-auto rounded-3xl border border-white/10 bg-slate-950/80 p-4 text-xs leading-6 text-slate-200">
            {JSON.stringify(value, null, 2)}
          </pre>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
