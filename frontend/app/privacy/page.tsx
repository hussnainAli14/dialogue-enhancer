import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — AI Dialogue Enhancer",
  description: "How AI Dialogue Enhancer collects, uses, and protects your data.",
};

const CONTACT_EMAIL = "support@numina.example"; // TODO: replace with real contact email
const LAST_UPDATED = "October 11, 2026";

export default function PrivacyPolicy() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12 text-text-primary">
      <h1 className="text-2xl font-semibold">Privacy Policy</h1>
      <p className="mt-2 text-sm text-text-muted">Last updated: {LAST_UPDATED}</p>

      <section className="mt-8 space-y-4 text-sm leading-relaxed">
        <p>
          AI Dialogue Enhancer (&ldquo;the Service&rdquo;) helps a single account
          holder discover relevant online conversations and compose thoughtful
          responses. This policy explains what data we collect, how we use it,
          and the choices you have.
        </p>

        <h2 className="pt-4 text-lg font-semibold">Information we collect</h2>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong>Connected account credentials.</strong> When you connect a
            social platform (such as Mastodon, Bluesky, Reddit, Threads, X,
            Discord, or YouTube), we store the OAuth access and refresh tokens
            needed to read content and, where you enable it, publish on your
            behalf. Tokens are stored encrypted and are used only to operate the
            features you turn on.
          </li>
          <li>
            <strong>Content you provide or we retrieve.</strong> Posts you
            submit, documents you upload to your knowledge base, drafts you
            generate, and public posts retrieved from platforms you connect.
          </li>
          <li>
            <strong>Operational data.</strong> Basic logs needed to run the
            Service (for example, discovery run status and error messages).
          </li>
        </ul>

        <h2 className="pt-4 text-lg font-semibold">How we use information</h2>
        <ul className="list-disc space-y-1 pl-6">
          <li>To discover and score relevant posts for your review.</li>
          <li>To generate response drafts grounded in your knowledge base.</li>
          <li>
            To publish replies or posts to a connected platform only when you
            explicitly approve or request it.
          </li>
        </ul>

        <h2 className="pt-4 text-lg font-semibold">Google and YouTube API data</h2>
        <p>
          The Service uses YouTube API Services. By connecting YouTube you also
          agree to the{" "}
          <a className="text-accent underline" href="https://www.youtube.com/t/terms" target="_blank" rel="noreferrer">
            YouTube Terms of Service
          </a>
          . Our use of information received from Google APIs adheres to the{" "}
          <a className="text-accent underline" href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements. You can review Google&rsquo;s
          privacy practices in the{" "}
          <a className="text-accent underline" href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">
            Google Privacy Policy
          </a>
          .
        </p>
        <p>
          We request read access to your YouTube data to surface relevant videos
          and, if you enable it, permission to post comments on your behalf. We
          do not transfer this data to third parties except as required to
          operate the Service, and we do not use it for advertising. You may
          revoke access at any time via your{" "}
          <a className="text-accent underline" href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer">
            Google account permissions
          </a>
          .
        </p>

        <h2 className="pt-4 text-lg font-semibold">Data sharing</h2>
        <p>
          We do not sell your data. Content is sent to the platforms you connect
          (only to perform actions you request) and to the AI model provider used
          to generate scores and drafts. We do not otherwise share your data.
        </p>

        <h2 className="pt-4 text-lg font-semibold">Data retention and deletion</h2>
        <p>
          We retain your connected-account tokens and content until you
          disconnect the account or request deletion. Disconnecting a platform
          removes its stored tokens. To request deletion of your data, contact us
          at the address below.
        </p>

        <h2 className="pt-4 text-lg font-semibold">Contact</h2>
        <p>
          For questions or data requests, contact{" "}
          <a className="text-accent underline" href={`mailto:${CONTACT_EMAIL}`}>
            {CONTACT_EMAIL}
          </a>
          .
        </p>
      </section>
    </main>
  );
}
