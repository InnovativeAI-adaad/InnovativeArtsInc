#!/bin/bash
# ADAAD Sovereign Ledger Repository Initializer
# Target: InnovativeArtsInc

set -euo pipefail

reset_registry=false

for arg in "$@"; do
  case "$arg" in
    --reset)
      reset_registry=true
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: $0 [--reset]" >&2
      exit 1
      ;;
  esac
done

mkdir -p core/{adaad_engine,agents/{mutation_agent,media_agent,deployment_agent,ip_agent},orchestration}
mkdir -p projects/jrt/{audio/{masters,stems,suno_exports},lyrics/{lean_on_somethin,sovereign_ledger,raw_drafts},metadata,visuals/{cover_art,concepts,svg_assets},rollout/{marketing_copy,platform_assets}}
mkdir -p docs pipelines registry

# Create placeholder manifests for agent readability unless preserved
if [[ "$reset_registry" == true ]]; then
  : > registry/asset_index.db
  echo "Reset registry/asset_index.db"
else
  if [[ -f registry/asset_index.db ]]; then
    echo "Preserved registry/asset_index.db"
  else
    : > registry/asset_index.db
    echo "Created registry/asset_index.db"
  fi
fi

if [[ "$reset_registry" == true ]]; then
  : > registry/provenance_log.jsonl
  echo "Reset registry/provenance_log.jsonl"
else
  if [[ -f registry/provenance_log.jsonl ]]; then
    echo "Preserved registry/provenance_log.jsonl"
  else
    : > registry/provenance_log.jsonl
    echo "Created registry/provenance_log.jsonl"
  fi
fi

if [[ "$reset_registry" == true ]]; then
  cat > registry/version_manifest.json <<'JSON'
{"version": "9.34.0", "status": "initializing"}
JSON
  echo "Reset registry/version_manifest.json"
else
  if [[ -f registry/version_manifest.json ]]; then
    echo "Preserved registry/version_manifest.json"
  else
    cat > registry/version_manifest.json <<'JSON'
{"version": "9.34.0", "status": "initializing"}
JSON
    echo "Created registry/version_manifest.json"
  fi
fi

echo "Architecture deployed. Spine established."
