import { Link } from "react-router";

import { Page } from "../components/Page";

export function NotFound() {
  return (
    <Page title="No such page">
      <h1>No such page</h1>
      <p className="lede">
        Nothing is served at this address. It may have been a page on the current interface rather
        than this one.
      </p>
      <p>
        <Link to="/">Back to the overview</Link>
      </p>
    </Page>
  );
}
