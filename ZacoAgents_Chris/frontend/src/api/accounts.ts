/**
 * Everything that reads or changes an account.
 *
 * Four lists, and they move together. Turning somebody off changes the users list and writes to
 * the trail; issuing a link answers a request and writes to the trail; accepting an invitation
 * removes it from one list and adds a row to another. So rather than each mutation naming the
 * two or three keys it happens to touch -- which is how a list goes stale after somebody adds a
 * fifth thing a mutation affects -- `unsettle` invalidates the account lists as a set.
 *
 * That is deliberately blunter than the round hooks next door, and it is the right bluntness
 * here: these four lists are small, read only by administrators, and read on one page at a time.
 * The round cache is the opposite -- expensive to rebuild, on screen constantly -- which is why
 * it is seeded from mutation responses instead.
 *
 * One thing is never cached: the reset link. It is returned once by the API and never listed
 * again, so putting it in a query cache would keep a working credential alive in memory for as
 * long as the tab is open, and would show it again to whoever opened the page next.
 */

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, type Schemas } from "./client";

export type Account = Schemas["UserOut"];
export type Invitation = Schemas["InvitationOut"];
export type ResetLink = Schemas["ResetOut"];
export type ResetRequest = Schemas["ResetRequestOut"];
export type AccountEvent = Schemas["AccountEventOut"];
export type Permission = Schemas["Permission"];

export const accountsKey = ["accounts"] as const;
export const invitationsKey = ["invitations"] as const;
export const requestsKey = ["password-requests"] as const;
export const eventsKey = ["account-events"] as const;

/** The order permissions are offered in, widest last. `admin` sits apart because it is the only
 *  one that grants the power to grant the others. */
export const PERMISSIONS: readonly { value: Permission; label: string; what: string }[] = [
  { value: "ingest", label: "Ingest", what: "Read documents and stage rounds" },
  { value: "resolve", label: "Resolve", what: "Answer the queue" },
  { value: "record_terms", label: "Record terms", what: "Set an agent's commission and charges" },
  { value: "append", label: "Append", what: "Write rows into the workbook" },
  { value: "view_reports", label: "View reports", what: "Read the reports and agent conduct" },
  { value: "admin", label: "Administer", what: "Invite people and set what they may do" },
];

export function useAccounts() {
  return useQuery({ queryKey: accountsKey, queryFn: () => api.get<Account[]>("/api/admin/users") });
}

export function useInvitations() {
  return useQuery({
    queryKey: invitationsKey,
    queryFn: () => api.get<Invitation[]>("/api/admin/invitations"),
  });
}

export function usePasswordRequests() {
  return useQuery({
    queryKey: requestsKey,
    queryFn: () => api.get<ResetRequest[]>("/api/admin/password-requests"),
  });
}

export function useAccountEvents() {
  return useQuery({
    queryKey: eventsKey,
    queryFn: () => api.get<AccountEvent[]>("/api/admin/events"),
  });
}

function unsettle(client: QueryClient) {
  for (const key of [accountsKey, invitationsKey, requestsKey, eventsKey]) {
    void client.invalidateQueries({ queryKey: key });
  }
}

function useAccountMutation<TVariables, TResult>(send: (variables: TVariables) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: send, onSuccess: () => unsettle(client) });
}

export function useSetPermissions() {
  return useAccountMutation(({ id, permissions }: { id: number; permissions: Permission[] }) =>
    api.put<Account>(`/api/admin/users/${id}/permissions`, { permissions }),
  );
}

export function useSetActive() {
  return useAccountMutation(({ id, isActive }: { id: number; isActive: boolean }) =>
    api.put<Account>(`/api/admin/users/${id}/active`, { is_active: isActive }),
  );
}

export function useSetProfile() {
  return useAccountMutation(({ id, displayName }: { id: number; displayName: string }) =>
    api.put<Account>(`/api/admin/users/${id}/profile`, { display_name: displayName }),
  );
}

export function useSetEmail() {
  return useAccountMutation(({ id, email, reason }: { id: number; email: string; reason: string }) =>
    api.put<Account>(`/api/admin/users/${id}/email`, { email, reason }),
  );
}

/** The response is a working credential. It is returned to the caller and goes nowhere else --
 *  see the note at the top of this file. */
export function useIssueReset() {
  return useAccountMutation(({ id, reason }: { id: number; reason: string }) =>
    api.post<ResetLink>(`/api/admin/users/${id}/password-reset`, { reason }),
  );
}

export function useInvite() {
  return useAccountMutation(({ email, permissions }: { email: string; permissions: Permission[] }) =>
    api.post<Invitation>("/api/admin/invitations", { email, permissions }),
  );
}

export function useRevokeInvitation() {
  return useAccountMutation((id: number) =>
    api.delete<Schemas["Message"]>(`/api/admin/invitations/${id}`),
  );
}

export function useReissueInvitation() {
  return useAccountMutation((id: number) =>
    api.post<Invitation>(`/api/admin/invitations/${id}/reissue`),
  );
}
