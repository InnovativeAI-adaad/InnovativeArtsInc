"""Runtime composition facade for dependency construction across pipelines and CLIs."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from core.gatekeeper.authorization import AUTHORIZATION_HMAC_KEY_ENV
from core.gatekeeper.ratification import RATIFICATION_HMAC_KEY_ENV
from core.governance.control_plane import GovernanceControlPlane
from services.media_conductor.service import MediaConductor, MediaConductorPaths

class RuntimeDependencyValidationError(ValueError):
    pass

@dataclass(frozen=True)
class RuntimeCredentials:
    authorization_hmac_key: str | None
    ratification_hmac_key: str | None
    governance_hmac_key: str | None
    control_snapshot_hmac_key: str | None

@dataclass(frozen=True)
class RuntimeEndpoints:
    repo_root: Path
    media_job_schema_path: Path

@dataclass(frozen=True)
class RuntimeFeatureFlags:
    require_agent_enabled: bool = False
    production_mode: bool = False

@dataclass(frozen=True)
class RuntimePolicyPaths:
    runtime_policy_path: Path
    creative_policy_path: Path
    quality_rules_path: Path
    similarity_policy_path: Path

@dataclass(frozen=True)
class RuntimeConfig:
    credentials: RuntimeCredentials
    endpoints: RuntimeEndpoints
    feature_flags: RuntimeFeatureFlags
    policy_paths: RuntimePolicyPaths

@dataclass(frozen=True)
class RuntimeContext:
    config: RuntimeConfig
    gatekeeper_env: dict[str, str]
    media_generation_adapter: Any
    release_dsp_adapter: Any
    release_pro_adapter: Any
    governance_control_plane: GovernanceControlPlane
    media_conductor_paths: MediaConductorPaths

    def create_media_conductor(self, *, actor: str, handlers: dict[str, Any] | None = None) -> MediaConductor:
        return MediaConductor(paths=self.media_conductor_paths, actor=actor, handlers=handlers)

def build_runtime_context(config: RuntimeConfig) -> RuntimeContext:
    _validate_runtime_config(config)
    gatekeeper_env = {
        AUTHORIZATION_HMAC_KEY_ENV: config.credentials.authorization_hmac_key or "",
        RATIFICATION_HMAC_KEY_ENV: config.credentials.ratification_hmac_key or "",
    }
    governance = GovernanceControlPlane(
        agent_log_path=config.endpoints.repo_root / "AGENT_LOG.md",
        provenance_log_path=config.endpoints.repo_root / "registry/provenance_log.jsonl",
        runtime_control_config_path=config.policy_paths.creative_policy_path,
    )
    return RuntimeContext(
        config=config,
        gatekeeper_env=gatekeeper_env,
        media_generation_adapter=object(),
        release_dsp_adapter=object(),
        release_pro_adapter=object(),
        governance_control_plane=governance,
        media_conductor_paths=MediaConductorPaths.from_repo_root(config.endpoints.repo_root),
    )

def build_runtime_config_from_env(*, repo_root: str | Path = ".") -> RuntimeConfig:
    root = Path(repo_root)
    return RuntimeConfig(
        credentials=RuntimeCredentials(
            authorization_hmac_key=os.getenv(AUTHORIZATION_HMAC_KEY_ENV),
            ratification_hmac_key=os.getenv(RATIFICATION_HMAC_KEY_ENV),
            governance_hmac_key=os.getenv("ADAAD_GOVERNANCE_HMAC_KEY"),
            control_snapshot_hmac_key=os.getenv("ADAAD_CONTROL_SNAPSHOT_HMAC_KEY"),
        ),
        endpoints=RuntimeEndpoints(repo_root=root, media_job_schema_path=root / "projects/jrt/metadata/schema/media_job.schema.json"),
        feature_flags=RuntimeFeatureFlags(
            require_agent_enabled=os.getenv("IAI_REQUIRE_AGENT_ENABLED", "false").lower() == "true",
            production_mode=os.getenv("IAI_PRODUCTION_MODE", "false").lower() == "true",
        ),
        policy_paths=RuntimePolicyPaths(
            runtime_policy_path=root / "projects/jrt/metadata/agent_runtime_config.json",
            creative_policy_path=root / "projects/jrt/metadata/control_plane.runtime.json",
            quality_rules_path=root / "projects/jrt/metadata/quality_rules.json",
            similarity_policy_path=root / "core/agents/ip_agent/config/similarity_policy.v1.json",
        ),
    )

def _validate_runtime_config(config: RuntimeConfig) -> None:
    missing: list[str] = []
    if not config.endpoints.media_job_schema_path.exists():
        missing.append(f"media job schema path not found: {config.endpoints.media_job_schema_path}")
    if config.feature_flags.production_mode:
        for path in (
            config.policy_paths.runtime_policy_path,
            config.policy_paths.creative_policy_path,
            config.policy_paths.quality_rules_path,
            config.policy_paths.similarity_policy_path,
        ):
            if not path.exists():
                missing.append(f"policy path not found: {path}")
        if not config.credentials.authorization_hmac_key:
            missing.append(f"missing required env var for production mode: {AUTHORIZATION_HMAC_KEY_ENV}")
        if not config.credentials.ratification_hmac_key:
            missing.append(f"missing required env var for production mode: {RATIFICATION_HMAC_KEY_ENV}")
    if missing:
        raise RuntimeDependencyValidationError(
            "Runtime dependency validation failed. Resolve the following before execution:\n - " + "\n - ".join(missing)
        )
