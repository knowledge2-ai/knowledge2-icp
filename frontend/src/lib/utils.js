import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge class names with Tailwind dedup — standard shadcn/ui helper. */
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
