from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from eric_motion_studio.domain import JointValues, ModelProfile, UNITREE_G1


class JointEditorWidget(QGroupBox):
    jointsChanged = Signal(object)

    def __init__(
        self,
        profile: ModelProfile = UNITREE_G1,
        parent=None,
    ) -> None:
        super().__init__("Joint editor", parent)
        self.setObjectName("jointEditorPanel")
        self.profile = profile
        self.spin_boxes: dict[str, QDoubleSpinBox] = {}

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
            form.addRow(name.replace("_joint", "").replace("_", " "), spin)
            self.spin_boxes[name] = spin

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

    def _emit_joints(self) -> None:
        self.jointsChanged.emit(self.current_joints())

    def current_joints(self) -> JointValues:
        return JointValues.from_mapping(
            {
                name: spin.value()
                for name, spin in self.spin_boxes.items()
            },
            self.profile,
        )

    def set_joints(self, joints: JointValues) -> None:
        blockers = [
            QSignalBlocker(spin)
            for spin in self.spin_boxes.values()
        ]
        for name, spin in self.spin_boxes.items():
            spin.setValue(joints.get(name))
        del blockers
