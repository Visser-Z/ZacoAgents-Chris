/**
 * The operator's book, and what a round would put into it.
 *
 * Two reads and two writes. The writes are the only ones in this system that touch a file the
 * business settles money against, so neither of them patches anything locally: an append and a
 * rollback both re-ask for the whole book afterwards, because what matters is what the file now
 * holds and not what the client thought it would.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Schemas } from "./client";
import { roundsKey } from "./rounds";

type Filled<T, K extends keyof T> = Omit<T, K> & { [P in K]-?: NonNullable<T[P]> };

export type Book = Filled<
  Schemas["WorkbookStateOut"],
  | "letters"
  | "headers"
  | "order"
  | "unknown_headers"
  | "versions"
  | "appended_rounds"
  | "ready_rounds"
  | "rows"
  | "numeric_columns"
  | "never_written"
>;

export type Preview = Filled<
  Schemas["AppendPreviewOut"],
  | "refusals"
  | "letters"
  | "headers"
  | "order"
  | "numeric_columns"
  | "formula_columns"
  | "never_written"
  | "rows"
  | "versions"
>;

export type BookRow = Schemas["BookRowOut"];
export type PreviewRow = Schemas["PreviewRowOut"];

/** The API always sends these -- Pydantic serialises a `default_factory` -- but a field with a
 *  default is not *required* in OpenAPI, so the generated type says it might be missing. Filled
 *  once here rather than guarded at every use. */
function fillBook(raw: Schemas["WorkbookStateOut"]): Book {
  return {
    ...raw,
    letters: raw.letters ?? {},
    headers: raw.headers ?? {},
    order: raw.order ?? [],
    unknown_headers: raw.unknown_headers ?? {},
    versions: raw.versions ?? [],
    appended_rounds: raw.appended_rounds ?? [],
    ready_rounds: raw.ready_rounds ?? [],
    rows: raw.rows ?? [],
    numeric_columns: raw.numeric_columns ?? [],
    never_written: raw.never_written ?? [],
  };
}

function fillPreview(raw: Schemas["AppendPreviewOut"]): Preview {
  return {
    ...raw,
    refusals: raw.refusals ?? [],
    letters: raw.letters ?? {},
    headers: raw.headers ?? {},
    order: raw.order ?? [],
    numeric_columns: raw.numeric_columns ?? [],
    formula_columns: raw.formula_columns ?? [],
    never_written: raw.never_written ?? [],
    rows: raw.rows ?? [],
    versions: raw.versions ?? [],
  };
}

export const bookKey = ["workbook"] as const;
export const previewKey = (id: number) => ["append-preview", id] as const;

export function useBook() {
  return useQuery({
    queryKey: bookKey,
    queryFn: async () => fillBook(await api.get<Schemas["WorkbookStateOut"]>("/api/workbook")),
  });
}

export function usePreview(roundId: number | null) {
  return useQuery({
    queryKey: previewKey(roundId ?? 0),
    queryFn: async () =>
      fillPreview(await api.get<Schemas["AppendPreviewOut"]>(`/api/rounds/${roundId}/append`)),
    enabled: roundId !== null,
  });
}

export function useAppend() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (roundId: number) =>
      fillPreview(await api.post<Schemas["AppendPreviewOut"]>(`/api/rounds/${roundId}/append`)),
    onSuccess: async (preview) => {
      client.setQueryData(previewKey(preview.round_id), preview);
      // The book, the ready list and the round's own status all change together.
      await client.invalidateQueries({ queryKey: bookKey });
      void client.invalidateQueries({ queryKey: roundsKey });
    },
  });
}

export function useRollBack() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; reason: string }) =>
      fillBook(
        await api.post<Schemas["WorkbookStateOut"]>(
          `/api/workbook/versions/${encodeURIComponent(body.name)}/restore`,
          { reason: body.reason },
        ),
      ),
    onSuccess: async (book) => {
      client.setQueryData(bookKey, book);
      // Every append preview is now describing a file that has changed underneath it.
      await client.invalidateQueries({ queryKey: ["append-preview"] });
    },
  });
}
