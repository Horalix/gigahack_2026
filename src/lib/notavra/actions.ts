// React and Svelte treat <select value> differently, and the Notavra UI polls
// its data every few seconds, so the difference is visible. In Svelte,
// `value={x}` on a <select> is re-assigned whenever the surrounding data
// refreshes, which would reset a dropdown the user just changed. This action
// reproduces React's `defaultValue` instead.

/** React's `defaultValue`: set once when the element mounts; later changes are ignored. */
export function initialValue(node: HTMLSelectElement, value: string | null | undefined): void {
  node.value = value ?? "";
}
