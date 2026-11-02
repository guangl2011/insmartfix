// React Native's FormData typing has no `get`; the shared contract mocks (DATA_SOURCE=mock) read
// uploads with it. Merged interface overloads declared later take precedence.
export {};

declare global {
  interface FormData {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    get(name: string): any;
  }
  interface Body {
    formData(): Promise<FormData>;
  }
  interface Request {
    formData(): Promise<FormData>;
  }
}
