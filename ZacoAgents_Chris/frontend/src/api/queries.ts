/**
 * Every read this interface makes, in one place.
 *
 * S1 says the documents are the record and everything else is re-derived on read, so each of
 * these endpoints re-parses the whole history to answer. That is the right design and it makes
 * caching worth having: the same question asked twice in a minute is the same answer, and asking
 * it again costs a full rebuild.
 *
 * `staleTime` is a minute rather than infinite. The record does change -- somebody appends a
 * round, agrees terms, records a payment -- and a report that never refreshes would quietly go on
 * showing yesterday's business.
 *
 * ## Why every list is filled in on the way through
 *
 * The API declares its collections with `Field(default_factory=list)`. Pydantic always serialises
 * them, so `products` is `[]` in the JSON and never missing -- but a field with a default is not
 * *required* in OpenAPI, so the generated types say `ProductLineOut[] | undefined` for something
 * that is always an array.
 *
 * Left alone that spreads about thirty `?? []` through the pages, each of which reads like a
 * guard against a case that cannot happen. So the defaults are applied once, here, as a real
 * runtime fill rather than a cast: if a future response genuinely does omit one, the page gets an
 * empty list instead of a crash, which is the same thing the server means by the default.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, type Schemas } from "./client";

/** The named keys made present and non-null. */
type Filled<T, K extends keyof T> = Omit<T, K> & { [P in K]-?: NonNullable<T[P]> };

export type Report = Filled<
  Schemas["ReportOut"],
  "products" | "markets" | "agents" | "take_on" | "caveats" | "bands"
> & {
  chart: Filled<Schemas["ReportChartOut"], "products" | "take_on" | "band_thresholds">;
};

export type Conduct = Filled<Schemas["ConductOut"], "kept" | "never_sold" | "caveats"> & {
  chart: Filled<Schemas["ConductChartOut"], "kept">;
};

export type Board = Filled<
  Schemas["ReconciliationBoardOut"],
  "states" | "labels" | "grouped" | "totals"
>;

export type Settlement = Filled<
  Schemas["SettlementOut"],
  "settled" | "awaiting_terms" | "awaiting_payment" | "by_supplier" | "suppliers" | "terms"
>;

export type Dockets = Filled<Schemas["DocketsOut"], "dockets">;

const MINUTE = 60_000;

function fillReport(raw: Schemas["ReportOut"]): Report {
  return {
    ...raw,
    products: raw.products ?? [],
    markets: raw.markets ?? [],
    agents: raw.agents ?? [],
    take_on: raw.take_on ?? [],
    caveats: raw.caveats ?? [],
    bands: raw.bands ?? {},
    chart: {
      products: raw.chart?.products ?? [],
      take_on: raw.chart?.take_on ?? [],
      band_thresholds: raw.chart?.band_thresholds ?? {},
    },
  };
}

function fillConduct(raw: Schemas["ConductOut"]): Conduct {
  return {
    ...raw,
    kept: raw.kept ?? [],
    never_sold: raw.never_sold ?? [],
    caveats: raw.caveats ?? [],
    chart: { kept: raw.chart?.kept ?? [], normal_share_kept: raw.chart?.normal_share_kept ?? null },
  };
}

function fillBoard(raw: Schemas["ReconciliationBoardOut"]): Board {
  return {
    ...raw,
    states: raw.states ?? [],
    labels: raw.labels ?? {},
    grouped: raw.grouped ?? {},
    totals: raw.totals ?? {},
  };
}

function fillSettlement(raw: Schemas["SettlementOut"]): Settlement {
  return {
    ...raw,
    settled: raw.settled ?? [],
    awaiting_terms: raw.awaiting_terms ?? [],
    awaiting_payment: raw.awaiting_payment ?? [],
    by_supplier: raw.by_supplier ?? [],
    suppliers: raw.suppliers ?? [],
    terms: raw.terms ?? [],
  };
}

export type Period = "all" | "month" | "week";

export function reportPath(period: Period, on: string): string {
  const query = new URLSearchParams({ period });
  if (period !== "all" && on) query.set("on", on);
  return `/api/reports?${query.toString()}`;
}

export function useReport(period: Period, on: string) {
  return useQuery({
    queryKey: ["reports", period, period === "all" ? "" : on],
    queryFn: async () => fillReport(await api.get<Schemas["ReportOut"]>(reportPath(period, on))),
    staleTime: MINUTE,
    // Changing the period keeps the previous report on screen while the next one is worked out.
    // A skeleton in its place would be a page that empties itself every time you ask it something.
    placeholderData: keepPreviousData,
  });
}

export function useConduct() {
  return useQuery({
    queryKey: ["conduct"],
    queryFn: async () => fillConduct(await api.get<Schemas["ConductOut"]>("/api/conduct")),
    staleTime: MINUTE,
  });
}

export function useBoard() {
  return useQuery({
    queryKey: ["reconciliation"],
    queryFn: async () =>
      fillBoard(await api.get<Schemas["ReconciliationBoardOut"]>("/api/reconciliation")),
    staleTime: MINUTE,
  });
}

export function useSettlement() {
  return useQuery({
    queryKey: ["settlement"],
    queryFn: async () =>
      fillSettlement(await api.get<Schemas["SettlementOut"]>("/api/settlement")),
    staleTime: MINUTE,
  });
}

export function useDockets() {
  return useQuery({
    queryKey: ["dockets"],
    queryFn: async () => {
      const raw = await api.get<Schemas["DocketsOut"]>("/api/dockets");
      return { ...raw, dockets: raw.dockets ?? [] };
    },
    staleTime: MINUTE,
  });
}
