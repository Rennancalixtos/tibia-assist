from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from gui.qt.components.log_panel import LogPanel
from gui.qt.components.warning_banner import WarningBanner
from gui.qt.controller import DISCLAIMER, Controller
from gui.qt.dialogs.module_config.auto_loot import AutoLootModuleView
from gui.qt.dialogs.module_config.cavebot import CavebotModuleView
from gui.qt.dialogs.module_config.fishing import FishingModuleView
from gui.qt.dialogs.module_config.runemaker import RuneMakerModuleView
from gui.qt.dialogs.module_config.target import TargetModuleView
from gui.qt.dialogs.module_config.training import TrainingModuleView


class DashboardPage(QWidget):
    def __init__(self, controller: Controller, main_window, log_overlay, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardPage")
        self.controller = controller
        self.log_overlay = log_overlay

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(16)

        grid = QGridLayout()
        grid.setSpacing(16)
        self.fishing_view = FishingModuleView(controller, main_window)
        self.runemaker_view = RuneMakerModuleView(controller, main_window)
        self.target_view = TargetModuleView(controller, main_window)
        self.training_view = TrainingModuleView(controller, main_window)
        self.cavebot_view = CavebotModuleView(controller, main_window)
        self.auto_loot_view = AutoLootModuleView(controller, main_window)
        grid.addWidget(self.fishing_view.card, 0, 0)
        grid.addWidget(self.runemaker_view.card, 0, 1)
        grid.addWidget(self.target_view.card, 1, 0)
        grid.addWidget(self.training_view.card, 1, 1)
        grid.addWidget(self.cavebot_view.card, 2, 0, 1, 2)
        grid.addWidget(self.auto_loot_view.card, 3, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        options_box = QVBoxLayout()
        options_box.setSpacing(6)
        options_title = QLabel("Opções")
        options_title.setObjectName("ModuleCardTitle")
        options_box.addWidget(options_title)

        self.dry_run_check = QCheckBox("Modo teste (não envia cliques/teclas para o jogo)")
        self.dry_run_check.setChecked(controller.dry_run_enabled)
        self.dry_run_check.toggled.connect(controller.toggle_dry_run)
        options_box.addWidget(self.dry_run_check)

        auto_food_row = QHBoxLayout()
        self.auto_food_check = QCheckBox("Auto Food")
        self.auto_food_check.toggled.connect(self._on_auto_food_toggled)
        self.auto_food_status_label = QLabel("parado")
        self.auto_food_status_label.setObjectName("StatLabel")
        auto_food_row.addWidget(self.auto_food_check)
        auto_food_row.addWidget(self.auto_food_status_label)
        auto_food_row.addStretch(1)
        options_box.addLayout(auto_food_row)
        controller.auto_food_state_changed.connect(self._on_auto_food_state)
        controller.auto_food_counter_changed.connect(self.auto_food_status_label.setText)

        self.log_overlay_check = QCheckBox("Logs na tela do jogo")
        self.log_overlay_check.setChecked(controller.log_overlay_enabled)
        self.log_overlay_check.toggled.connect(self._on_log_overlay_toggled)
        options_box.addWidget(self.log_overlay_check)

        self.log_panel_check = QCheckBox("Mostrar logs na aplicação")
        self.log_panel_check.setChecked(controller.log_panel_enabled)
        self.log_panel_check.toggled.connect(self._on_log_panel_toggled)
        options_box.addWidget(self.log_panel_check)

        layout.addLayout(options_box)

        self.shared_log = LogPanel(title="Log", max_lines=500)
        self.shared_log.setVisible(controller.log_panel_enabled)
        layout.addWidget(self.shared_log)

        self.warning_banner = WarningBanner(DISCLAIMER)
        layout.addWidget(self.warning_banner)

        self.footer_label = QLabel("")
        self.footer_label.setObjectName("FooterText")
        self.footer_label.setWordWrap(True)
        layout.addWidget(self.footer_label)

        self.admin_warning = WarningBanner()
        layout.addWidget(self.admin_warning)

        layout.addStretch(1)

        controller.log_line.connect(self._on_log_line)

        if controller.log_overlay_enabled:
            self.log_overlay.show()

        self._refresh_footer()

    def _on_auto_food_toggled(self, checked: bool) -> None:
        ok = self.controller.toggle_auto_food(checked)
        if checked and not ok:
            self.auto_food_check.blockSignals(True)
            self.auto_food_check.setChecked(False)
            self.auto_food_check.blockSignals(False)

    def _on_auto_food_state(self, state: str) -> None:
        self.auto_food_status_label.setText(state)
        if state == "stopped":
            self.auto_food_check.blockSignals(True)
            self.auto_food_check.setChecked(False)
            self.auto_food_check.blockSignals(False)

    def _on_log_overlay_toggled(self, checked: bool) -> None:
        self.controller.toggle_log_overlay(checked)
        if checked:
            self.log_overlay.show()
        else:
            self.log_overlay.hide()

    def _on_log_panel_toggled(self, checked: bool) -> None:
        self.controller.toggle_log_panel(checked)
        self.shared_log.setVisible(checked)

    def _on_log_line(self, line: str) -> None:
        self.shared_log.append(line)
        self.log_overlay.append(line)

    def _refresh_footer(self) -> None:
        admin_ok = self.controller.admin_ok()
        self.footer_label.setText(
            f"Administrador: {'Sim' if admin_ok else 'Não'}  |  "
            f"Escape de emergência: mova o mouse para o canto superior esquerdo da tela."
        )
        if not admin_ok:
            self.admin_warning.set_text(
                "Sem privilégio de administrador: clique/tecla sintético pode não ter "
                "efeito se o cliente do jogo rodar elevado. Feche e abra o programa de novo "
                "aceitando o pedido de elevação (UAC) do Windows."
            )
        else:
            self.admin_warning.set_text("")
