declare module "react" {
  export type ReactNode = any;
  export type ReactElement = any;
  export interface FormEvent<T = unknown> {
    preventDefault(): void;
    currentTarget: T;
  }
  export interface ChangeEvent<T = unknown> {
    target: T;
  }
  export function useEffect(fn: () => void | (() => void), deps?: unknown[]): void;
  export function useMemo<T>(factory: () => T, deps: unknown[]): T;
  export function useState<T>(initial: T): [T, (next: T | ((prev: T) => T)) => void];
}
