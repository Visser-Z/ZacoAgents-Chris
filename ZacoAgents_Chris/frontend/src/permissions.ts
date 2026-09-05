/** What each permission lets an account do, in words.
 *
 * The same sentences as `DESCRIPTIONS` in `zaco/auth/permissions.py`. They are repeated rather
 * than fetched because they are prose about a fixed set, not data: there is no endpoint that
 * serves them, and inventing one so a refusal page could name a permission would be a request in
 * the way of a sentence.
 */

import type { Permission } from "./auth/session";

export const DESCRIPTIONS: Record<Permission, string> = {
  ingest: "Upload and stage rounds",
  resolve: "Answer the resolution queue",
  append: "Append to the workbook and roll back versions",
  record_terms: "Record suppliers and commission terms",
  view_reports: "View reports",
  admin: "Invite accounts and set permissions",
};
