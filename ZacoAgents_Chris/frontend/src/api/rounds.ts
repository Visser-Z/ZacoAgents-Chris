/**
 * Everything that reads or changes a round.
 *
 * These are the writes. The reads elsewhere in this app re-derive a report and cost nothing but
 * time if they are stale; a mutation here records an operator's decision against their own name,
 * and what is on screen afterwards has to be what the server now holds.
 *
 * So every mutation returns the whole `RoundOut` and that response seeds the cache directly,
 * rather than the page patching what it thinks changed and asking again later. Answering one
 * question routinely answers others -- agreeing that two names are one product removes the code
 * question underneath it -- so a client that adjusted only the row it touched would be wrong
 * within one click. Two of them return a `Message` instead, and those refetch.
 *
 * The round list is invalidated alongside, because a document withdrawn or a queue closed changes
 * the counts on the list the operator picks rounds from.
 */

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, type Schemas } from "./client";

export type Round = Schemas["RoundOut"];
export type RoundSummary = Schemas["RoundSummaryOut"];
export type QueueItem = Schemas["QueueItemOut"];
export type Suspension = Schemas["SuspensionOut"];
export type RoundDocument = Schemas["DocumentOut"];
export type DeliveryNote = Schemas["DeliveryNoteOut"];

export const roundsKey = ["rounds"] as const;
export const roundKey = (id: number) => ["round", id] as const;

export function useRounds() {
  return useQuery({
    queryKey: roundsKey,
    queryFn: () => api.get<RoundSummary[]>("/api/rounds"),
  });
}

export function useRound(id: number | null) {
  return useQuery({
    queryKey: roundKey(id ?? 0),
    queryFn: () => api.get<Round>(`/api/rounds/${id}`),
    enabled: id !== null,
  });
}

/** Put a fresh round straight into the cache, and mark the list stale. */
function settle(client: QueryClient, round: Round) {
  client.setQueryData(roundKey(round.summary.id), round);
  void client.invalidateQueries({ queryKey: roundsKey });
}

/** A mutation whose response is the whole round. */
function useRoundMutation<TVariables>(send: (variables: TVariables) => Promise<Round>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: (round) => settle(client, round),
  });
}

/** A mutation that answers with a message rather than a round, so the round is asked for again. */
function useThenRefetch<TVariables>(
  id: number,
  send: (variables: TVariables) => Promise<unknown>,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: roundKey(id) });
      void client.invalidateQueries({ queryKey: roundsKey });
    },
  });
}

export function useStartRound() {
  return useRoundMutation((files: File[]) => api.upload<Round>("/api/rounds", files));
}

export interface LinkAnswer {
  left: string;
  right: string;
  accepted: boolean;
  reason: string;
}

export function useAnswerLink(id: number) {
  return useThenRefetch<LinkAnswer>(id, (body) => api.post("/api/products/link", body));
}

export interface CodeAnswer {
  product_key: string;
  short_code: string;
}

export function useAnswerCode(id: number) {
  return useThenRefetch<CodeAnswer>(id, (body) => api.post("/api/products/code", body));
}

export interface NoteAnswer {
  delivery_id: string;
  /** The other deliveries the operator says travelled on the same note. */
  also: string[];
  dn: string | null;
  provenance: string;
  reason: string;
}

export function useAnswerDeliveryNote(id: number) {
  return useRoundMutation((answer: NoteAnswer) => {
    const { delivery_id, also, dn, provenance, reason } = answer;
    if (also.length) {
      return api.post<Round>(`/api/rounds/${id}/delivery-notes/bulk`, {
        delivery_ids: [delivery_id, ...also],
        dn,
        provenance,
        reason,
      });
    }
    const query = new URLSearchParams({ delivery_id });
    return api.post<Round>(`/api/rounds/${id}/delivery-notes?${query.toString()}`, {
      dn,
      provenance,
      reason,
    });
  });
}

export function useDecideSuspension(id: number) {
  return useRoundMutation((body: { suspension_id: number; chosen_source: string; reason: string }) =>
    api.post<Round>(`/api/rounds/${id}/suspensions/${body.suspension_id}`, {
      chosen_source: body.chosen_source,
      reason: body.reason,
    }),
  );
}

export function useWithdrawDocument(id: number) {
  return useRoundMutation((body: { document_id: number; reason: string }) =>
    api.post<Round>(`/api/rounds/${id}/documents/${body.document_id}/withdraw`, {
      reason: body.reason,
    }),
  );
}

export function useRestoreDocument(id: number) {
  return useRoundMutation((document_id: number) =>
    api.post<Round>(`/api/rounds/${id}/documents/${document_id}/restore`, { reason: "" }),
  );
}

export function useReleaseNumber(id: number) {
  return useRoundMutation((body: { delivery_id: string; reason: string }) =>
    api.post<Round>(
      `/api/rounds/${id}/delivery-notes/${encodeURIComponent(body.delivery_id)}/release`,
      { reason: body.reason },
    ),
  );
}

export function useReopenRound(id: number) {
  return useRoundMutation((reason: string) =>
    api.post<Round>(`/api/rounds/${id}/reopen`, { reason }),
  );
}

export function useAbandonRound(id: number) {
  return useRoundMutation((reason: string) =>
    api.post<Round>(`/api/rounds/${id}/abandon`, { reason }),
  );
}

export function useCloseQueue(id: number) {
  return useRoundMutation(() => api.post<Round>(`/api/rounds/${id}/resolve`));
}
