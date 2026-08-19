"use client";

import type { Document } from "@/lib/types";
import DocumentCard from "./DocumentCard";

interface DocumentListProps {
  documents: Document[];
  onViewChunks: (doc: Document) => void;
  onReindex: (doc: Document) => void;
  onDelete: (doc: Document) => void;
}

export default function DocumentList({
  documents,
  onViewChunks,
  onReindex,
  onDelete,
}: DocumentListProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {documents.map((doc) => (
        <DocumentCard
          key={doc.id}
          document={doc}
          onViewChunks={onViewChunks}
          onReindex={onReindex}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
