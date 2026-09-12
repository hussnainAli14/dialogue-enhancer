"use client";

import { Puzzle } from "lucide-react";

export default function LinkedInClipperSection() {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-medium text-text-primary">
          <Puzzle className="h-5 w-5 text-accent-light" />
          Browser Clipper
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          The same extension sends a LinkedIn or Reddit post you are already
          reading into this dashboard. It only reads the post you pick.
        </p>
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 space-y-4 text-sm text-text-secondary">
        <ol className="list-decimal space-y-2 pl-5 text-text-primary">
          <li>
            In Chrome, open{" "}
            <span className="font-mono text-xs text-accent-light">
              chrome://extensions
            </span>
            , turn on Developer mode, then{" "}
            <strong className="font-medium">Load unpacked</strong> and select the{" "}
            <span className="font-mono text-xs text-accent-light">extension/</span>{" "}
            folder in this repo. If it is already loaded, click <strong>Reload</strong>.
          </li>
          <li>
            Open the extension options and point it at this API and dashboard
            (local or production). Allow LinkedIn and Reddit if Chrome asks.
          </li>
          <li>
            On LinkedIn or Reddit, open a post you want to reply to, click the
            extension icon, and send that post here.
          </li>
          <li>
            Review drafts in this dashboard. On LinkedIn, copy the reply and
            post it yourself. On Reddit, you can Approve &amp; Post if Reddit is
            connected, or copy it yourself.
          </li>
        </ol>

        <p className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs leading-relaxed">
          The clipper does not scroll the feed, search, visit other profiles, or
          publish comments. Use it only on a post you already opened.
        </p>
      </div>
    </section>
  );
}
