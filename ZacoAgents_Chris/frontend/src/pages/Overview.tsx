/**
 * The first page after signing in: every view this account may open, in one place.
 *
 * It used to be a list of the permissions the account held, which told somebody what they were
 * allowed to do without telling them where any of it was -- the sidebar was the only way through,
 * and a sidebar collapsed to a rail says nothing at all about what a section is for.
 *
 * The cards are generated from the same `NAV` the sidebar is drawn from, filtered by the same
 * permission check, so a section cannot appear in one and not the other.
 *
 * ## Why only two of them carry a figure
 *
 * `/api/rounds` is cheap: it lists what is saved, and the queue and workbook counts fall out of
 * that one call. Every other view -- reports, conduct, reconciliation, settlement -- re-derives
 * the whole record from every document on read (S1). Putting a number from each on this page
 * would re-parse the entire history four times over before anybody had asked a question, to
 * decorate a card. So those cards say what the view is for and leave the figure to the page that
 * is entitled to spend the time working it out.
 */

import { Link } from "react-router";

import { ACCOUNTS, NAV, type NavItem } from "../nav";
import { Icon } from "../components/Icon";
import { Page } from "../components/Page";
import { useRounds, type RoundSummary } from "../api/rounds";
import { useSession } from "../auth/session";

import "../styles/overview.css";

/** What each view is *for*, which is not the same as what its permission allows. The permission
 *  descriptions answer "may I?"; these answer "what would I come here to find out?". */
const WHAT: Record<string, string> = {
  "/rounds": "Read one document and see what it says, without saving anything.",
  "/staged": "Put a set of documents together and see what they amount to before committing.",
  "/queue": "Answer the questions the reports do not answer, one at a time.",
  "/workbook": "The operator's book as it stands, and what would be written beneath it.",
  "/reconciliation": "Where the agents' figures and the payments disagree, and by how much.",
  "/settlement": "What each supplier is owed, and what is not yet settleable.",
  "/reports": "What sold, for how much, and what is worth taking on again.",
  "/conduct": "Each account sale against this business's own normal. Not an accusation.",
  "/admin": "Who may use this system, what they may do, and what has been done to their accounts.",
};

interface Figure {
  text: string;
  quiet: boolean;
}

/** The two figures `/api/rounds` can answer honestly. `null` means the card carries none, which
 *  is the normal case -- see the note at the top of this file. */
function figureFor(path: string, rounds: readonly RoundSummary[]): Figure | null {
  if (path === "/queue") {
    const waiting = rounds.reduce((total, round) => total + round.open_questions, 0);
    if (waiting === 0) {
      return { text: rounds.length ? "Nothing waiting" : "No rounds saved yet", quiet: true };
    }
    const rounds_with = rounds.filter((round) => round.open_questions > 0).length;
    return {
      text: `${waiting} question${waiting === 1 ? "" : "s"} across ${rounds_with} round${rounds_with === 1 ? "" : "s"}`,
      quiet: false,
    };
  }
  if (path === "/workbook") {
    const ready = rounds.filter((round) => round.status === "resolved").length;
    if (ready === 0) return { text: "Nothing ready to append", quiet: true };
    return { text: `${ready} round${ready === 1 ? "" : "s"} ready to append`, quiet: false };
  }
  return null;
}

function ViewCard({ item, figure }: { item: NavItem; figure: Figure | null }) {
  return (
    <Link to={item.path} className="view-card">
      <span className="view-card-head">
        <Icon name={item.icon} />
        <span className="view-card-name">{item.label}</span>
      </span>
      <p>{WHAT[item.path]}</p>
      {figure ? (
        <span className={figure.quiet ? "view-card-figure quiet" : "view-card-figure"}>
          {figure.quiet ? figure.text : <strong>{figure.text}</strong>}
        </span>
      ) : null}
    </Link>
  );
}

export function Overview() {
  const { user, can } = useSession();
  // Only asked for when the queue or the workbook is on offer, because those are the only two
  // cards it feeds. An account that can read reports but not resolve should not be made to wait
  // on a list it will not be shown anything from.
  const wanted = can("resolve") || can("append");
  const rounds = useRounds({ enabled: wanted });
  const saved = rounds.data ?? [];

  const sections = NAV.filter(
    (item) => item.path !== "/" && (item.permission === null || can(item.permission)),
  );
  const views = can("admin") ? [...sections, ACCOUNTS] : sections;

  return (
    <Page title="Zaco account sales">
      <h1>Zaco account sales</h1>
      <p className="lede">
        Reads a round of market agent reports, resolves the facts those reports do not carry, and
        appends the result to the operator&rsquo;s live workbook.
      </p>

      {views.length === 0 ? (
        <div className="panel">
          <p className="muted" style={{ marginBottom: 0 }}>
            Your account has no permissions yet, so there is nothing here to open. An administrator
            grants them individually — ask for the ones you need rather than for all of them.
          </p>
        </div>
      ) : (
        <div className="views">
          {views.map((item) => (
            <ViewCard
              key={item.path}
              item={item}
              figure={rounds.isSuccess ? figureFor(item.path, saved) : null}
            />
          ))}
        </div>
      )}

      <h2>Where the decisions are written down</h2>
      <div className="panel">
        <p style={{ marginBottom: 0 }}>
          Every call this system makes where the reports left a choice open is recorded in{" "}
          <code>docs/DECISIONS.md</code>, together with what was rejected and why, and the
          questions that are still open. Those open questions are surfaced in the interface as
          they come up rather than being guessed at.
        </p>
      </div>

      {user ? (
        <p className="muted" style={{ fontSize: "0.9em" }}>
          Signed in as {user.display_name || user.email}. Your{" "}
          <Link to="/account">account page</Link> lists what it may do and is where you change your
          password.
        </p>
      ) : null}
    </Page>
  );
}
