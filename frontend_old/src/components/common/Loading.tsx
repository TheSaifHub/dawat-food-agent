// A loading line that admits when the free backend is waking up (CLAUDE.md: the "Waking up Dawat AI…" loader for
// cold starts). Pass `slow` once the request has run past the API client's onSlow threshold. It is not a live region:
// a region inserted already filled is often not read out, so each page keeps one <Announcer> that is always there.

/** `seq` counts messages: the same text twice in a row (a second "Added…", a repeated error) is still a change,
 *  because odd counts add a trailing no-break space that screen readers don't speak but do notice. */
export function Announcer({ text, seq = 0 }: { text: string; seq?: number }) {
  return <p role="status" aria-live="polite" className="sr-only">{text}{seq % 2 ? " " : ""}</p>;
}

export function Loading({ what, slow }: { what: string; slow: boolean }) {
  return (
    <p className="py-10 text-center text-muted-foreground">
      {slow ? "Waking up Dawat AI… the free server sleeps when idle, this can take up to a minute." : `Loading ${what}…`}
    </p>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border border-destructive px-4 py-6 text-center">
      <p className="text-destructive">{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="inline-block py-1 text-plum underline underline-offset-2">
          Try again
        </button>
      ) : null}
    </div>
  );
}
