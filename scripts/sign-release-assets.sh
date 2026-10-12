#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Sign the files of a PyQtPass release with your GnuPG key, like QtPass:
# every asset gets a detached, ASCII-armoured signature (<file>.asc) that
# is uploaded next to it. Run it on the draft release the Build and Release
# workflow made, then publish the release.
#
# Push the final release tag (a signed one, too) before signing: a tag push
# builds the release again, and refuses to once its files are signed.
#
#   scripts/sign-release-assets.sh [--dryrun] v0.4.0
#
# --dryrun signs in a temporary folder and uploads nothing. Files that
# already have a signature are skipped. Needs gh (logged in) and gpg.
#
# The build provenance attestation says which workflow run built the
# files; the signature says the maintainer chose to publish them.
set -euo pipefail

dryrun=false
while [ $# -gt 0 ]; do
	case "$1" in
	--dryrun)
		dryrun=true
		shift
		;;
	-*)
		echo "Usage: $0 [--dryrun] <release-tag>" >&2
		exit 1
		;;
	*)
		break
		;;
	esac
done

if [ $# -ne 1 ]; then
	echo "Usage: $0 [--dryrun] <release-tag>" >&2
	exit 1
fi

tag="$1"
repo="annejan/PyQtPass"

workdir="$(mktemp -d -t "sign-release-${tag}.XXXXXX")"
trap 'rm -rf "$workdir"' EXIT
cd "$workdir"

# Only uploaded assets are signed: GitHub's "Source code" links are made on
# the fly and are not release assets (the workflow uploads its own archives).
gh release download "$tag" --repo "$repo" --pattern '*'

new_asc=()
for file in *; do
	[ -f "$file" ] || continue
	case "$file" in
	*.asc) continue ;;
	esac
	[ -e "$file.asc" ] && continue
	if ! gpg_output=$(gpg --armor --detach-sign -- "$file" 2>&1 >/dev/null); then
		echo "Error: gpg could not sign '$file': $gpg_output" >&2
		exit 1
	fi
	if ! gpg --verify -- "$file.asc" "$file" 2>/dev/null; then
		echo "Error: the new signature of '$file' does not verify" >&2
		exit 1
	fi
	new_asc+=("$file.asc")
done

if [ ${#new_asc[@]} -eq 0 ]; then
	echo "Every asset of $tag is already signed."
elif [ "$dryrun" = true ]; then
	echo "[dryrun] Would upload: ${new_asc[*]}"
else
	gh release upload "$tag" --repo "$repo" --clobber "${new_asc[@]}"
	echo "Uploaded ${#new_asc[@]} signatures to $tag."
fi
