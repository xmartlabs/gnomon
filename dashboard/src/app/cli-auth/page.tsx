import { isLoopbackRedirect } from "@/lib/auth";

// Typeset to docs/design/mockups/cli-auth.html ("The Ledger"): a ruled sheet on
// cream paper — 4px ink top rule, Fraunces masthead, hairline-ruled privacy
// line, underline inputs, ink button, hairline colophon. No boxes.

export default async function CliAuthPage({
  searchParams,
}: {
  searchParams: Promise<{ redirect_uri?: string; count?: string; error?: string }>;
}) {
  const { redirect_uri = "", count = "1", error } = await searchParams;
  // Refuse the form outright rather than let someone fill it in for a callback
  // the route will reject — this page is the layer that knows a human is here.
  const validCallback = isLoopbackRedirect(redirect_uri);

  return (
    <main className="grid min-h-screen place-items-center p-10">
      <div className="w-full max-w-[440px] border-t-4 border-ink">
        <div className="flex items-baseline gap-3.5 border-b-2 border-ink pt-6 pb-4">
          <span className="serif text-[28px] font-semibold tracking-[-0.02em]">
            gnomon<span className="text-accent">.</span>
          </span>
          <span className="text-[11px] font-semibold tracking-[.2em] text-ink-60 uppercase">
            CLI sign-in
          </span>
        </div>

        <h1
          className="serif mt-6 mb-2.5 text-[34px] font-semibold tracking-[-0.01em]"
          style={{ fontVariationSettings: "'opsz' 80" }}
        >
          {validCallback ? "Authorize upload" : "Nothing to authorize"}
        </h1>

        {validCallback ? (
          <>
            <p className="max-w-[38ch] text-sm text-ink-60">
              Enter your team token to let the gnomon CLI upload your build profile.
            </p>

            <div className="my-5 flex gap-[11px] border-y border-hairline py-3.5 text-[13px] text-ink-60">
              <span className="serif flex-none text-gain italic">§</span>
              <span>
                Only <strong className="font-semibold text-ink">summary statistics</strong> are
                uploaded — prompts and file contents never leave your machine.
              </span>
            </div>

            {error && <p className="mb-5 text-[13px] font-medium text-accent">{error}</p>}

            <form method="POST" action="/api/cli-auth">
              <input type="hidden" name="redirect_uri" value={redirect_uri} />
              <input type="hidden" name="count" value={count} />
              <Field name="name" label="Name" type="text" placeholder="Grace Hopper" />
              <Field name="email" label="Email" type="email" placeholder="grace@company.com" />
              <Field
                name="team_token"
                label="Team token"
                type="password"
                placeholder="••••••••••••"
                inputClassName="num tracking-[.18em]"
              />
              <button
                type="submit"
                className="mt-2 w-full rounded-[2px] bg-ink py-3.5 text-sm font-semibold tracking-[.03em] text-paper"
              >
                Authorize
              </button>
            </form>
          </>
        ) : (
          <p className="my-5 max-w-[38ch] border-y border-hairline py-3.5 text-sm text-ink-60">
            This page signs the gnomon CLI in. Start it from your terminal — run{" "}
            <span className="num text-ink">xl-ai-insights</span> and it will open this page with a
            local callback attached.
          </p>
        )}

        <div className="mt-[22px] flex justify-between border-t border-hairline pt-3.5 text-[11px] tracking-[.04em] text-ink-60">
          <span>callback</span>
          <span className="num text-ink">{URL.parse(redirect_uri)?.host ?? "—"}</span>
        </div>
      </div>
    </main>
  );
}

function Field({
  name,
  label,
  type,
  placeholder,
  inputClassName = "",
}: {
  name: string;
  label: string;
  type: string;
  placeholder: string;
  inputClassName?: string;
}) {
  return (
    <div className="mb-5">
      <label
        htmlFor={name}
        className="mb-[7px] block text-[11px] font-semibold tracking-[.14em] text-ink-60 uppercase"
      >
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        required
        placeholder={placeholder}
        // Underline input: one ink-30 bottom rule that turns terracotta on
        // focus (design system §Inputs).
        className={`w-full border-0 border-b border-ink-30 bg-transparent py-1.5 text-base
          text-ink outline-none focus:border-accent placeholder:text-ink-30 ${inputClassName}`}
      />
    </div>
  );
}
