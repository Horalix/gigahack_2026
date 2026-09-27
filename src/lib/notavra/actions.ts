// Small differences between React and Svelte that are visible in the Notavra UI.
//
// `value={x}` on a <select> is re-assigned in Svelte whenever the surrounding
// data refreshes (the UI polls every few seconds), which would reset a dropdown
// the user just changed. `initialValue` reproduces React's `defaultValue`.
//
// Svelte's `autofocus` only focuses when nothing else has focus, but a form
// opened by a button click still has the button focused. `focusOnMount`
// reproduces React's `autoFocus`, which always focuses.

/** React's `defaultValue`: set once when the element mounts; later changes are ignored. */
export function initialValue(node: HTMLSelectElement, value: string | null | undefined): void {
  node.value = value ?? "";
}

/** React's `autoFocus`: focus the element when it mounts. */
export function focusOnMount(node: HTMLElement): void {
  node.focus();
}
