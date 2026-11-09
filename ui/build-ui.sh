#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Shared production/bootstrap path. No dependency on bundled Yarn or Corepack.
set -eu
cd "$(dirname "$0")"
pin="$(node -p 'require("./package.json").packageManager')"
case "$pin" in yarn@[0-9]*.[0-9]*.[0-9]*) ;; *) echo 'Invalid Yarn pin' >&2; exit 1;; esac
package="@yarnpkg/cli-dist@${pin#yarn@}"
yarn() { npm exec --yes --package="$package" -- yarn "$@"; }
node --version
yarn --version
yarn install --immutable
yarn lint
yarn build
