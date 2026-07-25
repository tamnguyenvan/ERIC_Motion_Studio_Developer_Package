from __future__ import annotations

import logging

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from eric_motion_studio.domain import UNITREE_G1, JointValues, ModelProfile
from eric_motion_studio.ui.icons import load_icon

LOGGER = logging.getLogger("eric_motion_studio")


class JointEditorWidget(QGroupBox):
    jointsChanged = Signal(object)
    returnPreviewNeutralRequested = Signal()
    addNeutralKeyframeRequested = Signal()
    savePoseRequested = Signal(object)
    loadPoseRequested = Signal()

    def __init__(
        self,
        profile: ModelProfile = UNITREE_G1,
        parent=None,
    ) -> None:
        super().__init__("Joint editor", parent)
        self.setObjectName("jointEditorPanel")
        self.profile = profile
        self.spin_boxes: dict[str, QDoubleSpinBox] = {}
        self.reset_buttons: dict[str, QToolButton] = {}
        self.lock_checkboxes: dict[str, QCheckBox] = {}
        self._copied_pose: JointValues | None = None
        self.reset_button = QPushButton("RESET ALL TO NEUTRAL")
        self.reset_button.setObjectName("resetJointDefaultsButton")
        self.reset_button.clicked.connect(self.reset_defaults)

        content = QWidget()
        form = QFormLayout(content)
        for name in profile.joint_names:
            limit = profile.limits[name]
            spin = QDoubleSpinBox()
            spin.setObjectName(f"joint_{name}")
            spin.setDecimals(3)
            spin.setSingleStep(0.01)
            spin.setRange(limit.lower, limit.upper)
            spin.setSuffix(" rad")
            spin.valueChanged.connect(self._emit_joints)
            reset = QToolButton()
            reset.setObjectName(f"resetJointButton_{name}")
            reset.setAutoRaise(True)
            reset.setFixedSize(24, 24)
            reset.setIcon(load_icon("reset_joint.png"))
            reset.setText("↺")
            reset.setToolTip(f"Reset {name.replace('_joint', '').replace('_', ' ')} to default")
            reset.clicked.connect(lambda _checked=False, joint=name: self.reset_joint(joint))
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(spin, 1)
            row_layout.addWidget(reset)
            form.addRow(name.replace("_joint", "").replace("_", " "), row)
            self.spin_boxes[name] = spin
            self.reset_buttons[name] = reset

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        lock_group = QGroupBox("Joint Locks")
        lock_layout = QGridLayout(lock_group)
        lock_specs = (
            ("LOCK LEGS", self.profile.groups.get("legs", ())),
            ("LOCK WAIST", self.profile.groups.get("waist", ())),
            ("LOCK LEFT ARM", self.profile.groups.get("left_arm", ())),
            ("LOCK RIGHT ARM", self.profile.groups.get("right_arm", ())),
            ("LOCK ROOT", ()),
        )
        for index, (label, joints) in enumerate(lock_specs):
            checkbox = QCheckBox(label)
            checkbox.setObjectName(f"{label.casefold().replace(' ', '_')}_lock")
            checkbox.setToolTip(
                "Root locking is reserved for the fixed model base."
                if not joints
                else f"Prevent changes to {label.removeprefix('LOCK ').casefold()} joints"
            )
            checkbox.toggled.connect(self._lock_changed)
            self.lock_checkboxes[label] = checkbox
            lock_layout.addWidget(checkbox, index // 3, index % 3)

        preset_layout = QGridLayout()
        self.return_preview_button = QPushButton("RETURN PREVIEW TO NEUTRAL")
        self.return_preview_button.setObjectName("returnPreviewNeutralButton")
        self.add_neutral_button = QPushButton("ADD NEUTRAL KEYFRAME")
        self.add_neutral_button.setObjectName("addNeutralKeyframeButton")
        self.copy_pose_button = QPushButton("COPY CURRENT POSE")
        self.copy_pose_button.setObjectName("copyCurrentPoseButton")
        self.apply_pose_button = QPushButton("APPLY POSE")
        self.apply_pose_button.setObjectName("applyCopiedPoseButton")
        self.save_pose_button = QPushButton("SAVE POSE")
        self.save_pose_button.setObjectName("savePoseButton")
        self.load_pose_button = QPushButton("LOAD POSE")
        self.load_pose_button.setObjectName("loadPoseButton")
        self.mirror_arms_button = QPushButton("MIRROR ARMS")
        self.mirror_arms_button.setObjectName("mirrorArmsButton")
        self.mirror_legs_button = QPushButton("MIRROR LEGS")
        self.mirror_legs_button.setObjectName("mirrorLegsButton")
        preset_buttons = (
            self.return_preview_button,
            self.add_neutral_button,
            self.copy_pose_button,
            self.apply_pose_button,
            self.save_pose_button,
            self.load_pose_button,
            self.mirror_arms_button,
            self.mirror_legs_button,
        )
        for index, button in enumerate(preset_buttons):
            preset_layout.addWidget(button, index // 2, index % 2)
        self.return_preview_button.clicked.connect(self.returnPreviewNeutralRequested)
        self.add_neutral_button.clicked.connect(self.addNeutralKeyframeRequested)
        self.copy_pose_button.clicked.connect(self.copy_current_pose)
        self.apply_pose_button.clicked.connect(self.apply_copied_pose)
        self.save_pose_button.clicked.connect(
            lambda: self.savePoseRequested.emit(self.current_joints())
        )
        self.load_pose_button.clicked.connect(self.loadPoseRequested)
        self.mirror_arms_button.clicked.connect(self.mirror_arms)
        self.mirror_legs_button.clicked.connect(self.mirror_legs)

        layout = QVBoxLayout(self)
        layout.addWidget(self.reset_button)
        layout.addWidget(scroll)
        layout.addWidget(lock_group)
        layout.addLayout(preset_layout)
        self._update_lock_widgets()

    def _emit_joints(self) -> None:
        self.jointsChanged.emit(self.current_joints())

    def current_joints(self) -> JointValues:
        return JointValues.from_mapping(
            {name: spin.value() for name, spin in self.spin_boxes.items()},
            self.profile,
        )

    def _locked_joints(self) -> set[str]:
        groups = {
            "LOCK LEGS": self.profile.groups.get("legs", ()),
            "LOCK WAIST": self.profile.groups.get("waist", ()),
            "LOCK LEFT ARM": self.profile.groups.get("left_arm", ()),
            "LOCK RIGHT ARM": self.profile.groups.get("right_arm", ()),
        }
        return {
            joint
            for label, group in groups.items()
            if self.lock_checkboxes[label].isChecked()
            for joint in group
        }

    def _apply_locks(self, joints: JointValues) -> JointValues:
        values = joints.to_mapping()
        current = self.current_joints()
        for name in self._locked_joints():
            values[name] = current.get(name)
        return JointValues.from_mapping(values, self.profile)

    def _lock_changed(self, _checked: bool) -> None:
        self._update_lock_widgets()
        LOGGER.info(
            "joint_lock_changed",
            extra={"context": {"locked_joints": sorted(self._locked_joints())}},
        )

    def _update_lock_widgets(self) -> None:
        locked = self._locked_joints()
        for name, spin in self.spin_boxes.items():
            enabled = name not in locked
            spin.setEnabled(enabled)
            self.reset_buttons[name].setEnabled(enabled)

    def set_joints(self, joints: JointValues, *, respect_locks: bool = False) -> None:
        if respect_locks:
            joints = self._apply_locks(joints)
        blockers = [QSignalBlocker(spin) for spin in self.spin_boxes.values()]
        for name, spin in self.spin_boxes.items():
            spin.setValue(joints.get(name))
        del blockers

    def reset_defaults(self) -> None:
        """Restore the model's neutral pose and publish it as the preview pose."""
        self.set_joints(JointValues.neutral(self.profile), respect_locks=True)
        self.jointsChanged.emit(self.current_joints())

    def reset_joint(self, name: str) -> None:
        """Restore one joint to its neutral/default value."""
        try:
            spin = self.spin_boxes[name]
        except KeyError as error:
            raise KeyError(f"Unknown joint: {name}") from error
        if name in self._locked_joints():
            return
        with QSignalBlocker(spin):
            spin.setValue(0.0)
        self.jointsChanged.emit(self.current_joints())

    def copy_current_pose(self) -> None:
        self._copied_pose = self.current_joints()
        LOGGER.info("pose_copied")

    def apply_copied_pose(self) -> None:
        if self._copied_pose is None:
            return
        self.set_joints(self._copied_pose, respect_locks=True)
        self.jointsChanged.emit(self.current_joints())
        LOGGER.info("pose_applied", extra={"context": {"locks_applied": True}})

    def mirror_arms(self) -> None:
        mapping = (
            ("left_shoulder_pitch_joint", "right_shoulder_pitch_joint", 1),
            ("left_shoulder_roll_joint", "right_shoulder_roll_joint", -1),
            ("left_shoulder_yaw_joint", "right_shoulder_yaw_joint", -1),
            ("left_elbow_joint", "right_elbow_joint", -1),
            ("left_wrist_roll_joint", "right_wrist_roll_joint", -1),
            ("left_wrist_pitch_joint", "right_wrist_pitch_joint", 1),
            ("left_wrist_yaw_joint", "right_wrist_yaw_joint", -1),
        )
        values = self.current_joints().to_mapping()
        for left, right, sign in mapping:
            values[right] = values[left] * sign
        self.set_joints(JointValues.from_mapping(values, self.profile), respect_locks=True)
        self.jointsChanged.emit(self.current_joints())
        LOGGER.info("arms_mirrored")

    def mirror_legs(self) -> None:
        mapping = (
            ("left_hip_pitch_joint", "right_hip_pitch_joint", 1),
            ("left_hip_roll_joint", "right_hip_roll_joint", -1),
            ("left_hip_yaw_joint", "right_hip_yaw_joint", -1),
            ("left_knee_joint", "right_knee_joint", 1),
            ("left_ankle_pitch_joint", "right_ankle_pitch_joint", 1),
            ("left_ankle_roll_joint", "right_ankle_roll_joint", -1),
        )
        values = self.current_joints().to_mapping()
        for left, right, sign in mapping:
            values[right] = values[left] * sign
        self.set_joints(JointValues.from_mapping(values, self.profile), respect_locks=True)
        self.jointsChanged.emit(self.current_joints())
        LOGGER.info("legs_mirrored")
