import type { FieldValues, Resolver } from "react-hook-form";
import type { z } from "zod";

import { ApiError } from "@/lib/api/fetcher";

/** Minimal zod v4 resolver for react-hook-form. */
export function zodResolver<T extends FieldValues>(schema: z.ZodType<T>): Resolver<T> {
  return async (values) => {
    const result = await schema.safeParseAsync(values);
    if (result.success) {
      return { values: result.data, errors: {} };
    }
    const errors: Record<string, { type: string; message: string }> = {};
    for (const issue of result.error.issues) {
      const path = issue.path.join(".");
      errors[path] ??= { type: issue.code, message: issue.message };
    }
    return { values: {}, errors } as unknown as Awaited<ReturnType<Resolver<T>>>;
  };
}

/** A user-facing message for any error thrown by an API call. */
export function errorMessage(error: unknown, fallback = "Something went wrong. Please try again.") {
  if (error instanceof ApiError) {
    if (error.code === "validation_error" && error.problem.errors?.length) {
      return error.problem.errors[0].msg;
    }
    return error.message || fallback;
  }
  return fallback;
}
