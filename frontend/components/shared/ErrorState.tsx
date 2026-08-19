"use client";

import { AlertCircle } from "lucide-react";
import Button from "./Button";

interface ErrorStateProps {
  title: string;
  description?: string;
  onRetry?: () => void;
}

export default function ErrorState({ title, description, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
      <AlertCircle className="h-10 w-10 text-danger" />
      <h3 className="text-lg font-medium text-text-primary">{title}</h3>
      {description && (
        <p className="max-w-md text-sm text-text-secondary">{description}</p>
      )}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry} className="mt-2">
          Try Again
        </Button>
      )}
    </div>
  );
}
