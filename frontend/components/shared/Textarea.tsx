"use client";

import { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
}

export default function Textarea({ label, className, id, ...props }: TextareaProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={id} className="text-xs text-text-secondary font-medium">
          {label}
        </label>
      )}
      <textarea
        id={id}
        className={cn(
          "rounded-lg bg-surface border border-border px-3 py-2 text-sm text-text-primary",
          "placeholder:text-text-muted focus:outline-none focus:border-border-bright",
          "transition-colors min-h-[100px] resize-y",
          className
        )}
        {...props}
      />
    </div>
  );
}
