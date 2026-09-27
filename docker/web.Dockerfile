# Svelte/Vite dev server for the browser path of the app.
#
# Source is bind-mounted at run time (see docker-compose.yml) so edits hot-reload.
# node_modules lives only inside the image: a Windows-installed node_modules has
# Windows-native esbuild/rollup binaries that cannot run on Linux.
#
# The native Tauri desktop build is not containerised. It targets Windows
# (WebView2, Windows audio capture) and has no meaningful Linux-container form.

# Matches the Node version the team develops with locally.
FROM node:22.14.0-bookworm-slim

# Install as the unprivileged `node` user that ships with the image. Doing the
# install as root and chown-ing afterwards would copy all of node_modules into a
# second layer and double the image size.
RUN mkdir /app && chown node:node /app
USER node
WORKDIR /app

COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# vite.config.js fixes port 1420 (Tauri's expectation). --host 0.0.0.0 makes it
# listen beyond the container's loopback so the published port reaches it.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
