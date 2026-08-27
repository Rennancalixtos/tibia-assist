from __future__ import annotations

TOKENS = {
    "bg": "#14161c",
    "surface": "#1c1f27",
    "surface_alt": "#232733",
    "border": "#2e323f",
    "text": "#e7e7ea",
    "text_dim": "#9298a8",
    "accent": "#39ff14",
    "accent_dim": "#2bbf10",
    "success": "#3ddc84",
    "warning": "#f5b400",
    "danger": "#ff5c5c",
}

_QSS_TEMPLATE = """
* {{
    font-family: "Segoe UI", sans-serif;
    outline: none;
}}

QWidget {{
    background-color: transparent;
    color: {text};
}}

QMainWindow, #Sidebar, #Header, #DashboardPage, #SettingsPage, #LogsPage, #AboutPage {{
    background-color: {bg};
}}

#Sidebar {{
    background-color: {surface};
    border-right: 1px solid {border};
}}

#SidebarLogo {{
    color: {accent};
    font-size: 20px;
    font-weight: 700;
}}

#SidebarVersion {{
    color: {text_dim};
    font-size: 11px;
}}

QPushButton#NavButton {{
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 6px;
    color: {text_dim};
    font-size: 13px;
}}

QPushButton#NavButton:hover {{
    background-color: {surface_alt};
    color: {text};
}}

QPushButton#NavButton:checked {{
    background-color: {surface_alt};
    color: {accent};
    font-weight: 600;
}}

#SessionInfoCard {{
    background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: 8px;
}}

#SessionInfoUser {{
    color: {text};
    font-weight: 600;
    font-size: 12px;
}}

#SessionInfoExpiry {{
    color: {text_dim};
    font-size: 11px;
}}

#HeaderTitle {{
    color: {text};
    font-size: 20px;
    font-weight: 700;
}}

#HeaderSubtitle {{
    color: {text_dim};
    font-size: 12px;
}}

QFrame#Card, QFrame#ModuleCard {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 10px;
}}

#ModuleCardTitle {{
    color: {text};
    font-size: 14px;
    font-weight: 700;
}}

#StatLabel {{
    color: {text_dim};
    font-size: 11px;
}}

#StatValue {{
    color: {text};
    font-size: 13px;
    font-weight: 600;
}}

QPushButton {{
    background-color: {surface_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 12px;
}}

QPushButton:hover {{
    background-color: {border};
}}

QPushButton:disabled {{
    color: {text_dim};
}}

QPushButton#ActionPrimary {{
    background-color: {accent};
    color: #0b1a06;
    border: none;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 700;
}}

QPushButton#ActionPrimary:disabled {{
    background-color: {border};
    color: {text_dim};
}}

QPushButton#ActionPrimary:hover:!disabled {{
    background-color: {accent_dim};
}}

QPushButton#ActionSecondary {{
    background-color: {surface_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 14px;
}}

QPushButton#ActionSecondary:disabled {{
    color: {text_dim};
}}

QPushButton#ActionSecondary:hover:!disabled {{
    background-color: {border};
}}

QPushButton#ActionDanger {{
    background-color: transparent;
    color: {danger};
    border: 1px solid {danger};
    border-radius: 6px;
    padding: 7px 14px;
}}

QPushButton#ActionDanger:hover {{
    background-color: rgba(255, 92, 92, 0.12);
}}

QLabel#StatusBadge {{
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
}}

QLabel#StatusBadge[state="running"] {{
    background-color: rgba(61, 220, 132, 0.16);
    color: {success};
}}

QLabel#StatusBadge[state="paused"] {{
    background-color: rgba(245, 180, 0, 0.16);
    color: {warning};
}}

QLabel#StatusBadge[state="stopped"] {{
    background-color: rgba(146, 152, 168, 0.16);
    color: {text_dim};
}}

QLabel#StatusBadge[state="error"] {{
    background-color: rgba(255, 92, 92, 0.16);
    color: {danger};
}}

QLabel#InfoIcon {{
    color: {accent};
    font-weight: 700;
}}

#WarningBanner {{
    background-color: rgba(255, 92, 92, 0.10);
    border: 1px solid rgba(255, 92, 92, 0.35);
    border-radius: 8px;
    color: {danger};
    font-size: 11px;
}}

#FooterText {{
    color: {text_dim};
    font-size: 11px;
}}

QGroupBox {{
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
    color: {text};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {text_dim};
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 4px 6px;
    color: {text};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {accent_dim};
}}

QCheckBox, QRadioButton {{
    color: {text};
    spacing: 6px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border};
    background-color: {surface_alt};
}}

QCheckBox::indicator {{
    border-radius: 3px;
}}

QRadioButton::indicator {{
    border-radius: 7px;
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {accent};
    border: 1px solid {accent_dim};
}}

QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {border};
    border: 1px solid {border};
}}

QPlainTextEdit, QTextEdit {{
    background-color: #0e1015;
    color: {accent};
    border: 1px solid {border};
    border-radius: 6px;
    font-family: Consolas, monospace;
}}

QScrollArea {{
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}

QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 5px;
    min-height: 24px;
}}

QToolTip {{
    background-color: {surface_alt};
    color: {text};
    border: 1px solid {border};
    padding: 4px 6px;
}}
"""


def build_stylesheet() -> str:
    return _QSS_TEMPLATE.format(**TOKENS)
