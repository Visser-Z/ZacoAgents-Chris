/**
 * The one place this app talks to the API.
 *
 * Two things are centralised here because the Jinja pages got them wrong eight times over: every
 * request carries the session cookie, and every refusal is turned into one shape.
 *
 * The API's `detail` is not one type. Most refusals are a string -- "Sign in first.", "Your
 * account does not have the 'append' permission." -- but a document the classifier will not
 * accept returns an object instead, carrying the filename and the scores it rejected it on. The
 * inline scripts each rediscovered that and handled it slightly differently. Here it is modelled
 * once, and `ApiError.refusal` is either the object or null.
 */

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Paths = paths;

/** What the classifier says when it will not accept a file. Not in the OpenAPI schema: the
 *  endpoints raise it rather than return it, so it is described here instead. */
export interface Refusal {
  filename: string;
  detail: string;
  scores: Record<string, number>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly refusal: Refusal | null;

  constructor(message: string, status: number, refusal: Refusal | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.refusal = refusal;
  }

  /** No session, or one that has expired. The caller sends the viewer to sign in. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** Signed in, but without the permission. Deliberately different from the above: the shell
   *  keeps its navigation and says which permission is missing, rather than bouncing to a login
   *  page the viewer has already been through. */
  get isForbidden(): boolean {
    return this.status === 403;
  }
}

function isRefusal(value: unknown): value is Refusal {
  return (
    typeof value === "object" &&
    value !== null &&
    "filename" in value &&
    "detail" in value &&
    typeof (value as Refusal).detail === "string"
  );
}

/** Pydantic's own 422 shape, which arrives when a body fails validation. */
function validationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const first = detail[0] as { msg?: unknown; loc?: unknown };
  if (typeof first?.msg !== "string") return null;
  const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null;
  return field ? `${String(field)}: ${first.msg}` : first.msg;
}

async function refuse(response: Response): Promise<never> {
  const payload = await response.json().catch(() => null);
  const detail = (payload as { detail?: unknown } | null)?.detail;

  if (isRefusal(detail)) {
    throw new ApiError(detail.detail, response.status, detail);
  }
  if (typeof detail === "string") {
    throw new ApiError(detail, response.status);
  }
  const validation = validationMessage(detail);
  if (validation) {
    throw new ApiError(validation, response.status);
  }
  throw new ApiError(`The request failed (${response.status}).`, response.status);
}

// `same-origin` rather than `include`: the app is served by the API. Sending credentials to
// anywhere else is not something this client should be able to do by accident.
const CREDENTIALS: RequestCredentials = "same-origin";

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: CREDENTIALS,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) await refuse(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string): Promise<T> => send<T>("GET", path),
  post: <T>(path: string, body?: unknown): Promise<T> => send<T>("POST", path, body),
  put: <T>(path: string, body?: unknown): Promise<T> => send<T>("PUT", path, body),
  delete: <T>(path: string, body?: unknown): Promise<T> => send<T>("DELETE", path, body),

  /**
   * Multipart upload. Written by hand rather than generated: the generators model file bodies
   * poorly, and the browser must set its own `Content-Type` so the boundary is right -- setting
   * it here would break the upload in a way that looks like a server fault.
   */
  upload: async <T>(path: string, files: File[], fields: Record<string, string> = {}): Promise<T> => {
    const body = new FormData();
    for (const file of files) body.append("files", file);
    for (const [key, value] of Object.entries(fields)) body.append(key, value);
    const response = await fetch(path, { method: "POST", body, credentials: CREDENTIALS });
    if (!response.ok) await refuse(response);
    return (await response.json()) as T;
  },

  /** The single-file variant: `/api/ingest/inspect` takes `file`, not `files`. */
  inspect: async <T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> => {
    const body = new FormData();
    body.append("file", file);
    for (const [key, value] of Object.entries(fields)) body.append(key, value);
    const response = await fetch(path, { method: "POST", body, credentials: CREDENTIALS });
    if (!response.ok) await refuse(response);
    return (await response.json()) as T;
  },
};
