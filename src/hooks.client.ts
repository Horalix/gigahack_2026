import { installTauriMock } from "$lib/dev/tauri-mock";

// Runs before any page component mounts. In a production build DEV is false,
// so this is dead code and the mock is not shipped.
if (
  import.meta.env.DEV &&
  import.meta.env.VITE_TAURI_MOCK === "1" &&
  !("__TAURI_INTERNALS__" in window)
) {
  installTauriMock();
}
