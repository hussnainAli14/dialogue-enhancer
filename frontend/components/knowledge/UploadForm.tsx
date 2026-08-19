"use client";

import { useRef, useState, DragEvent } from "react";
import { UploadCloud, X } from "lucide-react";
import { knowledgeApi } from "@/lib/api";
import { ACCEPTED_FILE_TYPES, SOURCE_TYPES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import Select from "@/components/shared/Select";

export default function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const { showToast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [author, setAuthor] = useState("");
  const [publishedDate, setPublishedDate] = useState("");

  const isAccepted = (f: File) => {
    const ext = "." + (f.name.split(".").pop()?.toLowerCase() ?? "");
    return ACCEPTED_FILE_TYPES.includes(ext);
  };

  // Add a batch of files: keep the accepted ones, warn about the rest and
  // de-duplicate by name + size so the same file is not queued twice.
  const addFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    const accepted = list.filter(isAccepted);
    const rejected = list.filter((f) => !isAccepted(f));
    if (rejected.length) {
      showToast(
        "error",
        `${rejected.length} file(s) skipped — unsupported type. Accepted: ${ACCEPTED_FILE_TYPES.join(", ")}`
      );
    }
    if (accepted.length) {
      setFiles((prev) => {
        const key = (f: File) => `${f.name}:${f.size}`;
        const seen = new Set(prev.map(key));
        const merged = [...prev];
        for (const f of accepted) {
          if (!seen.has(key(f))) {
            merged.push(f);
            seen.add(key(f));
          }
        }
        return merged;
      });
    }
  };

  const removeFile = (index: number) =>
    setFiles((prev) => prev.filter((_, i) => i !== index));

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  };

  const resetForm = () => {
    setFiles([]);
    setTitle("");
    setSourceType("");
    setAuthor("");
    setPublishedDate("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setProgress({ done: 0, total: files.length });

    let succeeded = 0;
    const duplicates: string[] = [];
    const failed: string[] = [];

    // Upload sequentially so the backend and the polling stay stable, and so
    // one bad file does not abort the rest of the batch.
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const res = await knowledgeApi.uploadDocument(file, {
          // A single shared title only makes sense for one file; with several,
          // each document is titled from its own filename by the backend.
          title: files.length === 1 ? title || undefined : undefined,
          source_type: sourceType || undefined,
          author: author || undefined,
          published_date: publishedDate || undefined,
        });
        if (res.duplicate) duplicates.push(file.name);
        else succeeded += 1;
      } catch (err) {
        failed.push(file.name);
      } finally {
        setProgress({ done: i + 1, total: files.length });
      }
    }

    if (succeeded > 0) {
      showToast(
        "success",
        `${succeeded} document(s) uploaded. Processing has started.`
      );
    }
    if (duplicates.length) {
      showToast(
        "info",
        `${duplicates.length} already in your library, skipped: ${duplicates.join(", ")}`
      );
    }
    if (failed.length) {
      showToast("error", `Failed to upload: ${failed.join(", ")}`);
    }

    setUploading(false);
    setProgress(null);
    resetForm();
    onUploaded();
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 transition-colors",
          dragOver ? "border-accent bg-accent/5" : "border-border hover:border-border-bright"
        )}
      >
        <UploadCloud className="h-8 w-8 text-text-muted" />
        <p className="text-sm text-text-primary">
          {files.length
            ? `${files.length} file(s) selected — drop or click to add more`
            : "Drag and drop files here, or click to browse"}
        </p>
        <div className="flex gap-2">
          {ACCEPTED_FILE_TYPES.map((t) => (
            <span
              key={t}
              className="rounded bg-surface-raised px-2 py-0.5 text-xs text-text-muted uppercase"
            >
              {t.replace(".", "")}
            </span>
          ))}
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_FILE_TYPES.join(",")}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) addFiles(e.target.files);
          }}
        />
      </div>

      {files.length > 0 && (
        <ul className="mt-4 space-y-2">
          {files.map((f, i) => (
            <li
              key={`${f.name}:${f.size}:${i}`}
              className="flex items-center justify-between rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm"
            >
              <span className="truncate text-text-primary">{f.name}</span>
              <div className="ml-3 flex flex-shrink-0 items-center gap-3">
                <span className="text-xs text-text-muted">
                  {(f.size / 1024).toFixed(0)} KB
                </span>
                {!uploading && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(i);
                    }}
                    className="text-text-muted transition-colors hover:text-danger"
                    aria-label={`Remove ${f.name}`}
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Input
          id="doc-title"
          label="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={files.length > 1 ? "Uses each filename" : "Optional"}
          disabled={files.length > 1}
        />
        <Select
          id="doc-source-type"
          label="Source Type"
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value)}
          placeholder="Select…"
          options={SOURCE_TYPES.map((s) => ({ value: s, label: s }))}
        />
        <Input
          id="doc-author"
          label="Author"
          value={author}
          onChange={(e) => setAuthor(e.target.value)}
          placeholder="Optional"
        />
        <Input
          id="doc-date"
          label="Published Date"
          type="date"
          value={publishedDate}
          onChange={(e) => setPublishedDate(e.target.value)}
        />
      </div>

      {files.length > 1 && (
        <p className="mt-2 text-xs text-text-muted">
          Source type, author, and date apply to all {files.length} files.
        </p>
      )}

      {progress && (
        <div className="mt-4">
          <div className="h-2 w-full overflow-hidden rounded-full bg-surface-raised">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${(progress.done / progress.total) * 100}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-text-muted">
            Uploading {progress.done} of {progress.total}…
          </p>
        </div>
      )}

      <Button
        className="mt-4"
        onClick={handleUpload}
        disabled={files.length === 0}
        loading={uploading}
      >
        {files.length > 1 ? `Upload ${files.length} Documents` : "Upload Document"}
      </Button>
    </div>
  );
}
