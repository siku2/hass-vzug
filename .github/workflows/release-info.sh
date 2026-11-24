#!/usr/bin/env bash
set -euo pipefail

domain=$(yq -r -oj '.domain' custom_components/*/manifest.json)
if [ -z "$domain" ]; then
	echo >&2 "No domain found in manifest.json. Please check your custom component."
	exit 1
fi
hacs_filename=$(yq -r '.filename' hacs.json)
if [ -z "$hacs_filename" ]; then
	echo >&2 "No filename found in hacs.json. Please check your HACS configuration."
	exit 1
fi

if [ -n "$INPUT_VERSION" ]; then
	version=$INPUT_VERSION
else
	echo >&2 "No version provided. Using the tag name as version."
	version=${REF_NAME#v}
fi
if ! [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
	echo >&2 "Version '$version' does not match SemVer format (e.g., 1.2.3 or 1.2.3-beta.1)."
	exit 1
fi

{
	echo "domain=$domain"
	echo "component_dir=custom_components/$domain"
	echo "hacs_filename=$hacs_filename"
	echo "version=$version"
	echo "tag_name=v$version"
} | tee -a "$GITHUB_OUTPUT"
