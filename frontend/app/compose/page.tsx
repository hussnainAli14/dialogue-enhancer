"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  ImagePlus,
  Loader2,
  Sparkles,
  X,
  XCircle,
} from "lucide-react";
import {
  postsApi,
  type ComposeCandidate,
  type PostResult,
  type PostTarget,
} from "@/lib/api";
import { PLATFORM_LABELS, STYLE_LABELS } from "@/lib/constants";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Textarea from "@/components/shared/Textarea";
import { cn } from "@/lib/utils";

const MAX_IMAGES = 4;

const SEED_FIELDS = [
  { key: "thinking", label: "What are you thinking about?" },
  { key: "example", label: "What real example or experience gives it life?" },
  { key: "tension", label: "What tension or question feels alive in it?" },
  { key: "invite", label: "What kind of response do you hope to invite?" },
] as const;

interface PendingImage {
  file: File;
  url: string;
  alt: string;
}

export default function ComposePage() {
  const { showToast } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);

  const [targets, setTargets] = useState<PostTarget[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [images, setImages] = useState<PendingImage[]>([]);
  const [posting, setPosting] = useState(false);
  const [results, setResults] = useState<PostResult[] | null>(null);

  // AI drafting from seed thoughts
  const [seed, setSeed] = useState({ thinking: "", example: "", tension: "", invite: "" });
  const [candidates, setCandidates] = useState<ComposeCandidate[]>([]);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    postsApi
      .getTargets()
      .then((r) => {
        setTargets(r.targets);
        // Pre-select every connected platform.
        setSelected(r.targets.filter((t) => t.connected).map((t) => t.platform));
      })
      .catch((err) =>
        showToast("error", err instanceof Error ? err.message : "Failed to load platforms")
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => images.forEach((i) => URL.revokeObjectURL(i.url));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connectedTargets = useMemo(() => targets.filter((t) => t.connected), [targets]);
  const anyConnected = connectedTargets.length > 0;
  const allSelected = anyConnected && selected.length === connectedTargets.length;

  // Strictest limit across the selected platforms drives the counter.
  const effectiveLimit = useMemo(() => {
    const limits = targets
      .filter((t) => selected.includes(t.platform) && t.char_limit != null)
      .map((t) => t.char_limit as number);
    return limits.length ? Math.min(...limits) : null;
  }, [targets, selected]);
  const overLimit = effectiveLimit != null && text.length > effectiveLimit;

  const toggle = (platform: string) =>
    setSelected((prev) =>
      prev.includes(platform) ? prev.filter((p) => p !== platform) : [...prev, platform]
    );

  const toggleAll = () =>
    setSelected(allSelected ? [] : connectedTargets.map((t) => t.platform));

  const addImages = (files: FileList | null) => {
    if (!files) return;
    const room = MAX_IMAGES - images.length;
    if (room <= 0) {
      showToast("warning", `At most ${MAX_IMAGES} images.`);
      return;
    }
    const next = Array.from(files)
      .filter((f) => f.type.startsWith("image/"))
      .slice(0, room)
      .map((f) => ({ file: f, url: URL.createObjectURL(f), alt: "" }));
    setImages((prev) => [...prev, ...next]);
  };

  const removeImage = (idx: number) => {
    setImages((prev) => {
      URL.revokeObjectURL(prev[idx].url);
      return prev.filter((_, i) => i !== idx);
    });
  };

  const setAlt = (idx: number, alt: string) =>
    setImages((prev) => prev.map((img, i) => (i === idx ? { ...img, alt } : img)));

  const canPost =
    selected.length > 0 &&
    !overLimit &&
    (text.trim().length > 0 || images.length > 0) &&
    !posting;

  const canGenerate = Object.values(seed).some((v) => v.trim().length > 0) && !generating;

  const handleGenerate = async () => {
    if (!canGenerate) return;
    setGenerating(true);
    try {
      const res = await postsApi.composeSuggest({ ...seed, char_limit: effectiveLimit });
      setCandidates(res.candidates);
      if (res.candidates.length === 0) {
        showToast("info", "No suggestions came back — try adding more detail.");
      }
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Could not generate suggestions");
    } finally {
      setGenerating(false);
    }
  };

  const useCandidate = (c: ComposeCandidate) => {
    setText(c.content);
    showToast("info", "Loaded into the editor — tweak it, then post.");
    if (typeof window !== "undefined") {
      document.getElementById("post-text")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  const handlePost = async () => {
    if (!canPost) return;
    setPosting(true);
    setResults(null);
    try {
      const res = await postsApi.createPost(selected, text, images);
      setResults(res.results);
      if (res.posted === res.total) {
        showToast("success", `Posted to all ${res.total} platform${res.total > 1 ? "s" : ""}.`);
        setText("");
        images.forEach((i) => URL.revokeObjectURL(i.url));
        setImages([]);
      } else if (res.posted > 0) {
        showToast("warning", `Posted to ${res.posted} of ${res.total} — see details below.`);
      } else {
        showToast("error", "Failed on every platform — see details below.");
      }
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Post failed");
    } finally {
      setPosting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-4">
        <h1 className="text-lg font-semibold text-text-primary">Compose a Post</h1>
        <p className="text-sm text-text-secondary">
          Publish your own thought — with optional images — to one or more connected
          platforms at once.
        </p>
      </div>

      {/* Draft with AI from seed thoughts */}
      <div className="mb-4 rounded-xl border border-border bg-surface p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent-light" />
          <span className="text-sm font-medium text-text-primary">Draft with AI</span>
        </div>
        <p className="text-xs text-text-secondary">
          Answer any of these and generate four candidate posts — Wholistic, Challenging,
          Insightful, and Facilitative — in your own voice. Pick one to edit and post.
        </p>
        {SEED_FIELDS.map((f) => (
          <Textarea
            key={f.key}
            id={`seed-${f.key}`}
            label={f.label}
            value={seed[f.key]}
            onChange={(e) => setSeed((s) => ({ ...s, [f.key]: e.target.value }))}
            className="min-h-[60px]"
          />
        ))}
        <Button onClick={handleGenerate} disabled={!canGenerate} variant="secondary">
          {generating ? (
            <span className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Generating…
            </span>
          ) : (
            "Generate 4 suggestions"
          )}
        </Button>

        {candidates.length > 0 && (
          <div className="space-y-3 border-t border-border pt-4">
            {candidates.map((c) => (
              <div key={c.style} className="rounded-lg border border-border bg-surface-raised p-4">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-accent-light">
                    {STYLE_LABELS[c.style] ?? c.style}
                  </span>
                  <button
                    onClick={() => useCandidate(c)}
                    className="text-xs text-accent-light hover:underline"
                  >
                    Use this →
                  </button>
                </div>
                <p className="whitespace-pre-wrap text-sm text-text-primary">{c.content}</p>
                {c.value_explanation && (
                  <p className="mt-2 text-xs text-text-muted">{c.value_explanation}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
        {/* Platform multi-select */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-text-secondary">
              Post to {selected.length > 0 && `(${selected.length} selected)`}
            </span>
            {anyConnected && (
              <button
                onClick={toggleAll}
                className="text-xs text-accent-light hover:underline"
              >
                {allSelected ? "Clear all" : "Select all"}
              </button>
            )}
          </div>

          {!anyConnected ? (
            <p className="text-sm text-warning">
              No posting-capable platform is connected yet. Connect Bluesky or Mastodon under
              Connections.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {targets.map((t) => {
                const on = selected.includes(t.platform);
                const label = PLATFORM_LABELS[t.platform] ?? t.platform;
                return (
                  <button
                    key={t.platform}
                    disabled={!t.connected}
                    onClick={() => toggle(t.platform)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                      !t.connected
                        ? "cursor-not-allowed border-border text-text-muted opacity-60"
                        : on
                          ? "border-accent bg-accent/15 text-accent-light"
                          : "border-border text-text-secondary hover:border-border-bright hover:text-text-primary"
                    )}
                  >
                    {on && t.connected && <CheckCircle2 className="h-3.5 w-3.5" />}
                    {label}
                    {!t.connected && " (not connected)"}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div>
          <Textarea
            id="post-text"
            label="What's on your mind?"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="min-h-[160px]"
          />
          <div className="mt-1 flex justify-end">
            <span className={overLimit ? "text-xs text-danger" : "text-xs text-text-muted"}>
              {text.length}
              {effectiveLimit != null ? ` / ${effectiveLimit}` : ""} characters
              {effectiveLimit != null && selected.length > 1 && " (strictest limit)"}
            </span>
          </div>
        </div>

        {/* Images */}
        <div className="space-y-3">
          {images.map((img, i) => (
            <div
              key={img.url}
              className="flex gap-3 rounded-lg border border-border bg-surface-raised p-3"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.url}
                alt="preview"
                className="h-20 w-20 shrink-0 rounded-md object-cover"
              />
              <div className="flex-1">
                <input
                  value={img.alt}
                  onChange={(e) => setAlt(i, e.target.value)}
                  placeholder="Alt text (optional, improves accessibility)"
                  className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:border-border-bright focus:outline-none"
                />
                <p className="mt-1 truncate text-xs text-text-muted">{img.file.name}</p>
              </div>
              <button
                onClick={() => removeImage(i)}
                className="self-start text-text-secondary hover:text-danger"
                aria-label="Remove image"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}

          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => {
              addImages(e.target.files);
              e.target.value = "";
            }}
          />
          {images.length < MAX_IMAGES && (
            <button
              onClick={() => fileInput.current?.click()}
              className="flex items-center gap-2 rounded-lg border border-dashed border-border px-4 py-2 text-sm text-text-secondary hover:border-border-bright hover:text-text-primary"
            >
              <ImagePlus className="h-4 w-4" />
              Add image{images.length > 0 ? "s" : ""} ({images.length}/{MAX_IMAGES})
            </button>
          )}
        </div>

        <Button onClick={handlePost} disabled={!canPost} size="lg">
          {posting ? (
            <span className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Posting…
            </span>
          ) : selected.length > 1 ? (
            `Post to ${selected.length} platforms`
          ) : (
            "Post Now"
          )}
        </Button>

        {/* Per-platform results */}
        {results && (
          <div className="space-y-2 border-t border-border pt-4">
            {results.map((r) => (
              <div key={r.platform} className="flex items-center gap-2 text-sm">
                {r.success ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 shrink-0 text-danger" />
                )}
                <span className="font-medium text-text-primary">
                  {PLATFORM_LABELS[r.platform] ?? r.platform}
                </span>
                {r.success ? (
                  r.result?.url && (
                    <a
                      href={r.result.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 text-accent-light hover:underline"
                    >
                      View post <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )
                ) : (
                  <span className="text-danger">{r.error}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
