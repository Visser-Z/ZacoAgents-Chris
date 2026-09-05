/**
 * The nav icons, drawn here rather than pulled from an icon package.
 *
 * They exist for one reason: when the sidebar is collapsed to a rail the label is gone, and a
 * column of identical dots is not navigation. Nine small shapes did not justify a dependency, and
 * D3 rules out fetching them from a CDN -- the system has to run offline from `docker compose up`.
 *
 * Every icon is decorative. The accessible name is always on the link, never here, which is why
 * each one is `aria-hidden`.
 */

export type IconName =
  | "overview"
  | "document"
  | "stage"
  | "queue"
  | "workbook"
  | "reconciliation"
  | "settlement"
  | "reports"
  | "conduct"
  | "accounts"
  | "signout"
  | "collapse"
  | "expand"
  | "menu"
  | "close";

const PATHS: Record<IconName, string> = {
  overview: "M4 11 12 4l8 7M6 9.5V20h12V9.5",
  document: "M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7zM14 3v4h4M9 12h6M9 16h6",
  stage: "M12 3 3 7.5 12 12l9-4.5zM3 12l9 4.5 9-4.5M3 16.5 12 21l9-4.5",
  queue: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .9-1 1.6v.4M12 17h.01",
  workbook: "M4 5h16v14H4zM4 9.5h16M9.5 9.5V19M4 14.3h16",
  reconciliation: "M4 8.5h13m-3.5-3.5 3.5 3.5-3.5 3.5M20 15.5H7m3.5 3.5L7 15.5 10.5 12",
  settlement: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M8.4 12.2l2.5 2.5 4.7-4.9",
  reports: "M4 20h16M7.5 20V11m4.5 9V5m4.5 15v-6",
  conduct: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14M20 20l-4.1-4.1",
  accounts: "M9 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M3.5 20a5.5 5.5 0 0 1 11 0M16 5.3a3.5 3.5 0 0 1 0 6.4M17.5 14.6a5.5 5.5 0 0 1 3 5.4",
  signout: "M12 4v8M7.8 6.8a7 7 0 1 0 8.4 0",
  collapse: "M14.5 6 8.5 12l6 6",
  expand: "M9.5 6l6 6-6 6",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6 6 18",
};

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
