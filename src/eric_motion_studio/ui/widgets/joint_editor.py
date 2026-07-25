from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from eric_motion_studio.domain import UNITREE_G1, JointValues, ModelProfile


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
        self.reset_buttons: dict[str, QToolButton] = {}
        self.reset_button = QPushButton("RESET DEFAULTS")
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
            reset.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
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
        layout = QVBoxLayout(self)
        layout.addWidget(self.reset_button)
        layout.addWidget(scroll)

    def _emit_joints(self) -> None:
        self.jointsChanged.emit(self.current_joints())

    def current_joints(self) -> JointValues:
        return JointValues.from_mapping(
            {name: spin.value() for name, spin in self.spin_boxes.items()},
            self.profile,
        )

    def set_joints(self, joints: JointValues) -> None:
        blockers = [QSignalBlocker(spin) for spin in self.spin_boxes.values()]
        for name, spin in self.spin_boxes.items():
            spin.setValue(joints.get(name))
        del blockers

    def reset_defaults(self) -> None:
        """Restore the model's neutral pose and publish it as the preview pose."""
        self.set_joints(JointValues.neutral(self.profile))
        self.jointsChanged.emit(self.current_joints())

    def reset_joint(self, name: str) -> None:
        """Restore one joint to its neutral/default value."""
        try:
            spin = self.spin_boxes[name]
        except KeyError as error:
            raise KeyError(f"Unknown joint: {name}") from error
        with QSignalBlocker(spin):
            spin.setValue(0.0)
        self.jointsChanged.emit(self.current_joints())
