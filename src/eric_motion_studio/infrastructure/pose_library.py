"""Built-in and custom pose library with deterministic ranked search."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path

from eric_motion_studio.domain import JointValues, Pose
from eric_motion_studio.gestures.normalization import normalize_text, tokenize
from eric_motion_studio.infrastructure.formats import PoseRepository

POSE_LIBRARY_SCHEMA_VERSION = 1
POSE_ID_KEY = "pose_id"
POSE_NAME_KEY = "pose_name"
POSE_DESCRIPTION_KEY = "pose_description"
POSE_ALIASES_KEY = "pose_aliases"
POSE_TAGS_KEY = "pose_tags"
POSE_BODY_REGIONS_KEY = "pose_body_regions"
POSE_ORIGIN_KEY = "library_origin"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class PoseLibraryError(ValueError):
    pass


class PoseOrigin(StrEnum):
    BUILTIN = "builtin"
    USER = "user"


@dataclass(frozen=True, slots=True)
class PoseLibraryEntry:
    entry_id: str
    display_name: str
    description: str
    aliases: tuple[str, ...]
    tags: tuple[str, ...]
    body_regions: tuple[str, ...]
    origin: PoseOrigin
    editable: bool
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class _BuiltinPose:
    entry: PoseLibraryEntry
    pose: Pose


def pose_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "untitled-pose"


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _metadata(pose: Pose, **updates: object) -> tuple[tuple[str, object], ...]:
    values = dict(pose.metadata)
    values.update(updates)
    return tuple(sorted(values.items()))


def _mirror_arms(joints: JointValues) -> JointValues:
    values = joints.to_mapping()
    for left, right, sign in (
        ("left_shoulder_pitch_joint", "right_shoulder_pitch_joint", 1),
        ("left_shoulder_roll_joint", "right_shoulder_roll_joint", -1),
        ("left_shoulder_yaw_joint", "right_shoulder_yaw_joint", -1),
        ("left_elbow_joint", "right_elbow_joint", -1),
        ("left_wrist_roll_joint", "right_wrist_roll_joint", -1),
        ("left_wrist_pitch_joint", "right_wrist_pitch_joint", 1),
        ("left_wrist_yaw_joint", "right_wrist_yaw_joint", -1),
    ):
        left_value = values[left]
        right_value = values[right]
        values[left] = right_value * sign
        values[right] = left_value * sign
    values["waist_yaw_joint"] *= -1
    values["waist_roll_joint"] *= -1
    return JointValues.from_mapping(values, joints.profile)


def _body_regions(joints: JointValues) -> tuple[str, ...]:
    active = {name for name, value in joints.to_mapping().items() if abs(value) > 1e-6}
    regions: list[str] = []
    if any(
        name.startswith("left_") and any(token in name for token in ("shoulder", "elbow", "wrist"))
        for name in active
    ):
        regions.append("left arm")
    if any(
        name.startswith("right_") and any(token in name for token in ("shoulder", "elbow", "wrist"))
        for name in active
    ):
        regions.append("right arm")
    if any(name.startswith("waist_") for name in active):
        regions.append("waist")
    if any(token in name for name in active for token in ("hip", "knee", "ankle")):
        regions.append("legs")
    return tuple(regions or ("full body",))


def _search_score(entry: PoseLibraryEntry, query: str) -> int:
    normalized = normalize_text(query)
    if not normalized:
        return 1
    query_tokens = set(tokenize(normalized))
    name = normalize_text(entry.display_name)
    aliases = tuple(normalize_text(value) for value in entry.aliases)
    description = normalize_text(entry.description)
    tags = tuple(normalize_text(value) for value in entry.tags)
    regions = tuple(normalize_text(value) for value in entry.body_regions)
    fields = (name, *aliases, description, *tags, *regions)

    score = 0
    if normalized == name:
        score += 1200
    if normalized in aliases:
        score += 1100
    if name.startswith(normalized):
        score += 700
    for field in fields:
        if normalized and normalized in field:
            score += 450
        field_tokens = set(tokenize(field))
        overlap = len(query_tokens.intersection(field_tokens))
        score += overlap * 120
        if query_tokens and query_tokens.issubset(field_tokens):
            score += 300
    similarity = max(
        (SequenceMatcher(None, normalized, field).ratio() for field in fields if field),
        default=0.0,
    )
    if similarity >= 0.55:
        score += round(similarity * 250)
    name_token_similarity = max(
        (SequenceMatcher(None, normalized, token).ratio() for token in tokenize(name)),
        default=0.0,
    )
    if name_token_similarity >= 0.7:
        score += round(name_token_similarity * 400)
    return score


class PoseLibrary:
    def __init__(
        self,
        poses_dir: Path,
        definitions_path: Path,
        stages_path: Path,
        *,
        repository: PoseRepository | None = None,
    ) -> None:
        self.poses_dir = Path(poses_dir)
        self.repository = repository or PoseRepository()
        self._builtins = self._load_builtins(
            Path(definitions_path),
            Path(stages_path),
        )

    def entries(self) -> tuple[PoseLibraryEntry, ...]:
        users: list[PoseLibraryEntry] = []
        for path in sorted(self.poses_dir.glob("*.json")):
            try:
                pose = self.repository.load(path)
            except (OSError, ValueError):
                continue
            metadata = dict(pose.metadata)
            users.append(
                PoseLibraryEntry(
                    entry_id=f"user:{path.name}",
                    display_name=str(metadata.get(POSE_NAME_KEY) or path.stem),
                    description=str(metadata.get(POSE_DESCRIPTION_KEY) or ""),
                    aliases=_string_tuple(metadata.get(POSE_ALIASES_KEY)),
                    tags=_string_tuple(metadata.get(POSE_TAGS_KEY)),
                    body_regions=_string_tuple(metadata.get(POSE_BODY_REGIONS_KEY)),
                    origin=PoseOrigin.USER,
                    editable=True,
                    path=path,
                )
            )
        return (*(item.entry for item in self._builtins.values()), *users)

    def search(self, query: str) -> tuple[PoseLibraryEntry, ...]:
        entries = self.entries()
        if not normalize_text(query):
            return entries
        ranked = ((score, entry) for entry in entries if (score := _search_score(entry, query)) > 0)
        return tuple(
            entry
            for _score, entry in sorted(
                ranked,
                key=lambda item: (
                    -item[0],
                    item[1].origin is PoseOrigin.USER,
                    item[1].display_name.casefold(),
                ),
            )
        )

    def load(self, entry_id: str) -> tuple[Pose, Path | None]:
        if entry_id.startswith("builtin:"):
            pose_id = entry_id.removeprefix("builtin:")
            try:
                return self._builtins[pose_id].pose, None
            except KeyError as error:
                raise KeyError(f"Unknown built-in pose: {pose_id}") from error
        path = self._user_path(entry_id)
        return self.repository.load(path), path

    def create(self, joints: JointValues, name: str) -> tuple[Pose, Path]:
        display_name = self._available_name(name)
        pose = Pose(
            joints=joints,
            metadata=tuple(
                sorted(
                    {
                        POSE_ID_KEY: pose_slug(display_name).replace("-", "_"),
                        POSE_NAME_KEY: display_name,
                        POSE_DESCRIPTION_KEY: "",
                        POSE_ALIASES_KEY: [],
                        POSE_TAGS_KEY: ["custom"],
                        POSE_BODY_REGIONS_KEY: list(_body_regions(joints)),
                        POSE_ORIGIN_KEY: PoseOrigin.USER.value,
                    }.items()
                )
            ),
        )
        path = self._available_path(display_name)
        self.repository.save(path, pose)
        return pose, path

    def update(self, entry_id: str, joints: JointValues) -> tuple[Pose, Path]:
        pose, path = self.load(entry_id)
        if path is None:
            raise ValueError("Built-in poses cannot be updated")
        updated = replace(
            pose,
            joints=joints,
            metadata=_metadata(
                pose,
                **{POSE_BODY_REGIONS_KEY: list(_body_regions(joints))},
            ),
        )
        self.repository.save(path, updated)
        return updated, path

    def rename(self, entry_id: str, name: str) -> tuple[Pose, Path]:
        pose, path = self.load(entry_id)
        if path is None:
            raise ValueError("Built-in poses cannot be renamed")
        display_name = name.strip()
        if not display_name:
            raise ValueError("Pose name must not be empty")
        renamed = replace(
            pose,
            metadata=_metadata(
                pose,
                **{POSE_NAME_KEY: display_name},
            ),
        )
        self.repository.save(path, renamed)
        return renamed, path

    def duplicate(self, entry_id: str) -> tuple[Pose, Path]:
        source, _source_path = self.load(entry_id)
        metadata = dict(source.metadata)
        source_name = str(metadata.get(POSE_NAME_KEY) or "Pose")
        display_name = self._available_copy_name(source_name)
        duplicate = Pose(
            joints=source.joints,
            simulation_only=source.simulation_only,
            model_ref=source.model_ref,
            metadata=_metadata(
                source,
                **{
                    POSE_ID_KEY: pose_slug(display_name).replace("-", "_"),
                    POSE_NAME_KEY: display_name,
                    POSE_ORIGIN_KEY: PoseOrigin.USER.value,
                },
            ),
        )
        path = self._available_path(display_name)
        self.repository.save(path, duplicate)
        return duplicate, path

    def delete(self, entry_id: str) -> Path:
        path = self._user_path(entry_id)
        path.unlink()
        return path

    def _available_name(self, requested: str) -> str:
        base = requested.strip() or "Untitled Pose"
        names = {entry.display_name.casefold() for entry in self.entries()}
        if base.casefold() not in names:
            return base
        index = 2
        while f"{base} {index}".casefold() in names:
            index += 1
        return f"{base} {index}"

    def _available_copy_name(self, source_name: str) -> str:
        base = re.sub(r"\s+Copy(?:\s+\d+)?$", "", source_name, flags=re.IGNORECASE)
        names = {entry.display_name.casefold() for entry in self.entries()}
        candidate = f"{base} Copy"
        if candidate.casefold() not in names:
            return candidate
        index = 2
        while f"{candidate} {index}".casefold() in names:
            index += 1
        return f"{candidate} {index}"

    def _available_path(self, name: str) -> Path:
        stem = pose_slug(name)
        path = self.poses_dir / f"{stem}.json"
        index = 2
        while path.exists():
            path = self.poses_dir / f"{stem}-{index}.json"
            index += 1
        return path

    def _user_path(self, entry_id: str) -> Path:
        if not entry_id.startswith("user:"):
            raise ValueError("Built-in poses cannot be modified or deleted")
        name = entry_id.removeprefix("user:")
        if Path(name).name != name:
            raise ValueError("Pose library entry is invalid")
        path = self.poses_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def _load_builtins(
        self,
        definitions_path: Path,
        stages_path: Path,
    ) -> dict[str, _BuiltinPose]:
        definitions = _load_object(definitions_path)
        stages = _load_object(stages_path)
        if definitions.get("schema_version") != POSE_LIBRARY_SCHEMA_VERSION:
            raise PoseLibraryError("pose library schema_version must be 1")
        raw_definitions = definitions.get("poses")
        raw_stage_poses = stages.get("poses")
        if not isinstance(raw_definitions, list) or not isinstance(raw_stage_poses, Mapping):
            raise PoseLibraryError("pose library resources are invalid")

        builtins: dict[str, _BuiltinPose] = {}
        for raw in raw_definitions:
            definition = _definition(raw)
            pose_id = definition["id"]
            source_id = definition["source_pose"]
            if pose_id in builtins:
                raise PoseLibraryError(f"duplicate built-in pose id: {pose_id}")
            try:
                raw_joints = raw_stage_poses[source_id]
            except KeyError as error:
                raise PoseLibraryError(
                    f"built-in pose {pose_id!r} references unknown stage pose {source_id!r}"
                ) from error
            if not isinstance(raw_joints, Mapping):
                raise PoseLibraryError(f"stage pose {source_id!r} must be an object")
            try:
                joints = JointValues.from_mapping(raw_joints)
            except (TypeError, ValueError) as error:
                raise PoseLibraryError(f"stage pose {source_id!r} has invalid joints") from error
            if definition["mirror_arms"]:
                joints = _mirror_arms(joints)
            entry = PoseLibraryEntry(
                entry_id=f"builtin:{pose_id}",
                display_name=definition["name"],
                description=definition["description"],
                aliases=definition["aliases"],
                tags=definition["tags"],
                body_regions=definition["body_regions"],
                origin=PoseOrigin.BUILTIN,
                editable=False,
            )
            pose = Pose(
                joints=joints,
                metadata=tuple(
                    sorted(
                        {
                            POSE_ID_KEY: pose_id,
                            POSE_NAME_KEY: definition["name"],
                            POSE_DESCRIPTION_KEY: definition["description"],
                            POSE_ALIASES_KEY: list(definition["aliases"]),
                            POSE_TAGS_KEY: list(definition["tags"]),
                            POSE_BODY_REGIONS_KEY: list(definition["body_regions"]),
                            POSE_ORIGIN_KEY: PoseOrigin.BUILTIN.value,
                        }.items()
                    )
                ),
            )
            builtins[pose_id] = _BuiltinPose(entry, pose)
        return builtins


def _load_object(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PoseLibraryError(f"Could not load {path}: {error}") from error
    if not isinstance(payload, Mapping):
        raise PoseLibraryError(f"{path} must contain an object")
    return payload


def _definition(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise PoseLibraryError("pose definition must be an object")
    pose_id = raw.get("id")
    name = raw.get("name")
    source_pose = raw.get("source_pose")
    description = raw.get("description")
    if not isinstance(pose_id, str) or not _IDENTIFIER.fullmatch(pose_id):
        raise PoseLibraryError("pose definition id is invalid")
    if not isinstance(name, str) or not name.strip():
        raise PoseLibraryError(f"pose definition {pose_id!r} has an invalid name")
    if not isinstance(source_pose, str) or not source_pose:
        raise PoseLibraryError(f"pose definition {pose_id!r} has an invalid source_pose")
    if not isinstance(description, str):
        raise PoseLibraryError(f"pose definition {pose_id!r} has an invalid description")
    mirror_arms = raw.get("mirror_arms", False)
    if not isinstance(mirror_arms, bool):
        raise PoseLibraryError(f"pose definition {pose_id!r} has invalid mirror_arms")
    aliases = _required_strings(raw.get("aliases"), pose_id, "aliases")
    tags = _required_strings(raw.get("tags"), pose_id, "tags")
    regions = _required_strings(raw.get("body_regions"), pose_id, "body_regions")
    return {
        "id": pose_id,
        "name": name.strip(),
        "source_pose": source_pose,
        "description": description.strip(),
        "mirror_arms": mirror_arms,
        "aliases": aliases,
        "tags": tags,
        "body_regions": regions,
    }


def _required_strings(value: object, pose_id: str, field: str) -> tuple[str, ...]:
    values = _string_tuple(value)
    if not values:
        raise PoseLibraryError(f"pose definition {pose_id!r} has invalid {field}")
    return values
