"use client";

import { File, FileCode, FileText, FileType, RefreshCw, Trash2 } from "lucide-react";
import type { Document } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import Button from "@/components/shared/Button";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import StatusBadge from "@/components/feed/StatusBadge";

const FILE_ICONS: Record<string, React.ReactNode> = {
  pdf: <FileType className="h-5 w-5 text-red-400" />,
  docx: <FileText className="h-5 w-5 text-blue-400" />,
  doc: <FileText className="h-5 w-5 text-blue-300" />,
  html: <FileCode className="h-5 w-5 text-orange-400" />,
  txt: <File className="h-5 w-5 text-gray-400" />,
  md: <FileCode className="h-5 w-5 text-purple-400" />,
};

interface DocumentCardProps {
  document: Document;
  onViewChunks: (doc: Document) => void;
  onReindex: (doc: Document) => void;
  onDelete: (doc: Document) => void;
}

export default function DocumentCard({
  document: doc,
  onViewChunks,
  onReindex,
  onDelete,
}: DocumentCardProps) {
  const processing = doc.status === "processing";
  const errored = doc.status === "error";

  return (
    <div className="flex flex-col rounded-xl border border-border bg-surface p-6">
      <div className="flex items-start gap-3">
        {FILE_ICONS[doc.file_type] ?? <File className="h-5 w-5 text-gray-400" />}
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-medium text-text-primary">
            {doc.title || doc.filename}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {doc.source_type && (
              <span className="rounded-full bg-surface-raised px-2 py-0.5 text-xs text-text-secondary capitalize">
                {doc.source_type}
              </span>
            )}
            <StatusBadge status={doc.status} />
          </div>
        </div>
      </div>

      <div className="mt-3 flex-1">
        {processing ? (
          <div className="flex items-center gap-2 text-sm text-warning">
            <LoadingSpinner size="sm" />
            Processing your document
          </div>
        ) : errored ? (
          <p className="text-sm text-danger">{doc.error_message || "Processing failed"}</p>
        ) : (
          <p className="text-xs text-text-secondary">
            {doc.word_count?.toLocaleString() ?? "?"} words · {doc.chunk_count} chunks
          </p>
        )}
        <p className="mt-1 text-xs text-text-muted">{formatDate(doc.created_at)}</p>
      </div>

      <div className="mt-4 flex gap-2 border-t border-border pt-4">
        {!processing && !errored && (
          <Button size="sm" variant="ghost" onClick={() => onViewChunks(doc)}>
            View Chunks
          </Button>
        )}
        {!processing && (
          <Button
            size="sm"
            variant="ghost"
            iconLeft={<RefreshCw className="h-3.5 w-3.5" />}
            onClick={() => onReindex(doc)}
          >
            Reindex
          </Button>
        )}
        <Button
          size="sm"
          variant="danger"
          iconLeft={<Trash2 className="h-3.5 w-3.5" />}
          onClick={() => onDelete(doc)}
          className="ml-auto"
        >
          Delete
        </Button>
      </div>
    </div>
  );
}
