// Dawat's logo (CLAUDE.md → Brand): a Mughal-style arch with a covered serving dish inside, gold line art on plum.
// An original drawing, kept as inline SVG so it scales crisply and needs no image request.

type Props = {
  /** Rendered width and height in CSS pixels. */
  size?: number;
  /** Accessible name. Pass "" when the logo sits next to the visible word "Dawat" (it is then decorative). */
  title?: string;
  className?: string;
};

export function DawatLogo({ size = 40, title = "Dawat", className }: Props) {
  const decorative = title === "";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : title}
      focusable="false"
    >
      <rect width="64" height="64" rx="14" fill="#5B1E4E" />
      <g fill="none" stroke="#D8AE4A" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
        {/* The arch: straight jambs rising into an ogee (onion) point, with a finial. */}
        <path d="M15 55V29C15 20 25 17 32 9C39 17 49 20 49 29V55" />
        <path d="M32 9V5.5" />
        {/* A floor line under the arch. */}
        <path d="M11 55H53" />
        {/* The covered dish: dome, knob, rim and stand. */}
        <path d="M21.5 45A10.5 10.5 0 0 1 42.5 45" />
        <circle cx="32" cy="32.6" r="1.9" />
        <path d="M18.5 45.5H45.5" />
        <path d="M26 49.5H38" />
      </g>
    </svg>
  );
}
