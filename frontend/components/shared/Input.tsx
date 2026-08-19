"use client";

import { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export default function Input({ label, className, id, ...props }: InputProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={id} className="text-xs text-text-secondary font-medium">
          {label}
        </label>
      )}
      <input
        id={id}
        className={cn(
          "rounded-lg bg-surface border border-border px-3 py-2 text-sm text-text-primary",
          "placeholder:text-text-muted focus:outline-none focus:border-border-bright",
          "transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
          className
        )}
        {...props}
      />
    </div>
  );
}
