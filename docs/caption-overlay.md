# Caption overlay

The overlay is a Win32/GDI layered child process, separate from the Tauri settings window. It has no webview, taskbar button, normal title bar, or activation on mouse interaction. Topmost behavior is optional.

Drag the caption area to move it. Resize using edges and corners. A small corner control opens native options for text size, text/background colors, opacity, and local transcript saving. The full Settings dialog remains in the main window. Click-through is optional and disables mouse interaction until turned off in Settings or with Ctrl+Shift+X.

Appearance settings are written atomically and read by the overlay. An authenticated loopback-only control channel carries settings and saving status; it never carries audio or transcript content. Geometry persists after a move or resize. Startup positions are clamped to the nearest monitor work area; font sizes scale with monitor DPI.

Recognition writes bounded recent text, keeping original/translation boundaries separate. The overlay wraps within its dimensions, drops older words if necessary, and clears stale speech after 4.5 seconds. Finalized speech is stored independently of display truncation. Saving status and storage errors are visible in the overlay.

Start owns one overlay process. Stop and normal exit close it. The child also watches the parent process and closes if the parent exits unexpectedly.

`--overlay-render-test <bmp-path>` exercises the native renderer with a window that never has `WS_VISIBLE`. It asserts that the window remains invisible and the foreground handle stays unchanged, then writes a bitmap and exits. `FEELSAY_CAPTION_TEXT_FILE` and `FEELSAY_OVERLAY_SETTINGS` supply controlled fixtures. Do not launch ordinary visible overlay tests in an active user's desktop session.

Hidden rendering verifies the renderer and no-activation path. Live dragging, resize cursors, popup interaction, mixed-monitor DPI transitions, fullscreen behavior, and parent-crash lifecycle still need the explicitly controlled manual checks in `installer-smoke-test.md`.
