#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Panneaux de l'interface utilisateur pour validation - VERSION AMÉLIORÉE
Avec splitters et sections collapsibles
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QTextEdit, QCheckBox,
    QGroupBox, QGraphicsScene, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter, QToolButton
)
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtCore import Qt, pyqtSignal
from typing import Dict, Any


class CollapsibleGroupBox(QGroupBox):
    """GroupBox collapsible avec bouton toggle"""
    
    collapsed_changed = pyqtSignal(bool)
    
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        
        self.is_collapsed = False
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        
        # Layout principal du GroupBox
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 25, 0, 5)  # Espace pour le titre
        main_layout.addWidget(self.content_widget)
        
        # Bouton toggle dans le titre
        self.toggle_button = QToolButton(self)
        self.toggle_button.setText("▼")
        self.toggle_button.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                font-weight: bold;
            }
        """)
        self.toggle_button.setFixedSize(20, 20)
        self.toggle_button.move(5, 2)
        self.toggle_button.clicked.connect(self.toggle_collapse)
    
    def set_content_layout(self, layout):
        """Définir le layout du contenu"""
        # Supprimer l'ancien layout
        while self.content_layout.count():
            self.content_layout.takeAt(0)
        
        # Transférer les widgets
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                self.content_layout.addWidget(item.widget())
            elif item.layout():
                self.content_layout.addLayout(item.layout())
    
    def toggle_collapse(self):
        """Basculer l'état collapsed"""
        self.set_collapsed(not self.is_collapsed)
    
    def set_collapsed(self, collapsed: bool):
        """Définir l'état collapsed"""
        self.is_collapsed = collapsed
        self.content_widget.setVisible(not collapsed)
        self.toggle_button.setText("▶" if collapsed else "▼")
        self.collapsed_changed.emit(collapsed)
        
        # Ajuster la taille minimale
        if collapsed:
            self.setMinimumHeight(30)
            self.setMaximumHeight(30)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)


class PDFViewerPanel(QWidget):
    """Panneau de visualisation PDF"""
    
    def __init__(self, parent_interface):
        """
        Initialiser le panneau
        
        Args:
            parent_interface: Interface parente
        """
        super().__init__()
        self.parent_interface = parent_interface
        self.view = None
        self.show_all_spans_cb = None
        self._init_ui()
    
    def _init_ui(self):
        """Créer l'interface du panneau"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar de zoom
        zoom_layout = QHBoxLayout()
        
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedWidth(40)
        zoom_out_btn.clicked.connect(self.parent_interface.zoom_out)
        
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(40)
        zoom_in_btn.clicked.connect(self.parent_interface.zoom_in)
        
        zoom_reset_btn = QPushButton("100%")
        zoom_reset_btn.setFixedWidth(60)
        zoom_reset_btn.clicked.connect(self.parent_interface.zoom_reset)
        
        self.show_all_spans_cb = QCheckBox("Tous spans")
        self.show_all_spans_cb.setChecked(False)
        self.show_all_spans_cb.stateChanged.connect(self.parent_interface.refresh_display)
        
        zoom_layout.addWidget(QLabel("🔍 Zoom:"))
        zoom_layout.addWidget(zoom_out_btn)
        zoom_layout.addWidget(zoom_in_btn)
        zoom_layout.addWidget(zoom_reset_btn)
        zoom_layout.addSpacing(20)
        zoom_layout.addWidget(self.show_all_spans_cb)
        zoom_layout.addStretch()
        
        layout.addLayout(zoom_layout)
        
        # Vue graphique
        self.view = QGraphicsView(self.parent_interface.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        layout.addWidget(self.view)


class ControlPanel(QWidget):
    """Panneau de contrôle principal avec splitters et sections collapsibles"""
    
    def __init__(self, parent_interface):
        """
        Initialiser le panneau
        
        Args:
            parent_interface: Interface parente
        """
        super().__init__()
        self.parent_interface = parent_interface
        
        # Widgets
        self.prev_btn = None
        self.next_btn = None
        self.page_label = None
        self.blocks_list = None
        self.stats_group = None
        self.stats_label = None
        self.block_info_label = None
        self.preserve_empty_btn = None
        self.include_isolated_btn = None
        self.spans_table = None
        self.move_up_btn = None
        self.move_down_btn = None
        self.remove_span_btn = None
        self.available_spans_list = None
        self.undo_btn = None
        self.redo_btn = None
        self.create_block_btn = None
        
        self._init_ui()
    
    def _init_ui(self):
        """Créer l'interface du panneau avec splitters"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Navigation (toujours visible, fixe)
        layout.addWidget(self._create_navigation_group())
        
        # Splitter vertical pour les sections principales
        self.main_splitter = QSplitter(Qt.Vertical)
        
        # Zone 1 : Liste des blocs + Statistiques
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        top_layout.addWidget(self._create_blocks_list_group())
        top_layout.addWidget(self._create_stats_group())
        
        self.main_splitter.addWidget(top_widget)
        
        # Zone 2 : Détails + Spans
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        
        middle_layout.addWidget(self._create_block_detail_group())
        middle_layout.addWidget(self._create_spans_group())
        
        self.main_splitter.addWidget(middle_widget)
        
        # Zone 3 : Spans disponibles + Actions
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        bottom_layout.addWidget(self._create_available_spans_group())
        bottom_layout.addWidget(self._create_actions_group())
        
        self.main_splitter.addWidget(bottom_widget)
        
        # Restaurer les proportions du splitter vertical (si disponibles)
        if hasattr(self.parent_interface, 'prefs'):
            saved_sizes = self.parent_interface.prefs.get('splitters.control_vertical', [300, 300, 200])
            self.main_splitter.setSizes(saved_sizes)
        else:
            # Proportions par défaut
            self.main_splitter.setStretchFactor(0, 3)
            self.main_splitter.setStretchFactor(1, 3)
            self.main_splitter.setStretchFactor(2, 2)
        
        layout.addWidget(self.main_splitter)
    
    def _create_navigation_group(self) -> QGroupBox:
        """Créer le groupe de navigation"""
        group = QGroupBox("📄 Navigation")
        layout = QVBoxLayout()
        
        page_nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(40)
        self.prev_btn.clicked.connect(self.parent_interface.prev_page)
        
        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(40)
        self.next_btn.clicked.connect(self.parent_interface.next_page)
        
        self.page_label = QLabel("Page 1/1")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setStyleSheet("font-weight: bold;")
        
        page_nav_layout.addWidget(self.prev_btn)
        page_nav_layout.addWidget(self.page_label, 1)
        page_nav_layout.addWidget(self.next_btn)
        
        layout.addLayout(page_nav_layout)
        group.setLayout(layout)
        group.setMaximumHeight(80)
        
        return group
    
    def _create_blocks_list_group(self) -> QGroupBox:
        """Créer le groupe de liste des blocs"""
        group = QGroupBox("📋 Blocs de cette page")
        layout = QVBoxLayout()
        
        self.blocks_list = QListWidget()
        self.blocks_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.blocks_list.itemClicked.connect(
            lambda item: self.parent_interface.on_block_list_click(item)
        )
        
        layout.addWidget(self.blocks_list)
        group.setLayout(layout)
        
        return group
    
    def _create_stats_group(self) -> CollapsibleGroupBox:
        """Créer le groupe de statistiques (collapsible)"""
        self.stats_group = CollapsibleGroupBox("📊 Statistiques")
        layout = QVBoxLayout()
        
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet("font-size: 9pt;")
        
        layout.addWidget(self.stats_label)
        self.stats_group.set_content_layout(layout)
        
        # Ajouter un bouton toggle rapide
        toggle_btn = QPushButton("📊 Masquer stats")
        toggle_btn.setCheckable(True)
        toggle_btn.setMaximumHeight(25)
        toggle_btn.setStyleSheet("font-size: 9pt;")
        toggle_btn.toggled.connect(lambda checked: self._toggle_stats(checked, toggle_btn))
        
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.stats_group)
        wrapper_layout.addWidget(toggle_btn)
        
        return wrapper
    
    def _toggle_stats(self, collapsed: bool, button: QPushButton):
        """Toggle des statistiques"""
        self.stats_group.set_collapsed(collapsed)
        button.setText("📊 Afficher stats" if collapsed else "📊 Masquer stats")
    
    def _create_block_detail_group(self) -> CollapsibleGroupBox:
        """Créer le groupe de détails du bloc (collapsible)"""
        group = CollapsibleGroupBox("🔍 Bloc Sélectionné")
        layout = QVBoxLayout()
        
        self.block_info_label = QLabel("Aucun bloc")
        self.block_info_label.setWordWrap(True)
        self.block_info_label.setStyleSheet("font-size: 9pt;")
        layout.addWidget(self.block_info_label)
        
        # Actions du bloc
        actions = QHBoxLayout()
        
        self.preserve_empty_btn = QPushButton("🔒 Conserver")
        self.preserve_empty_btn.clicked.connect(self.parent_interface.toggle_preserve_empty)
        self.preserve_empty_btn.setEnabled(False)
        
        self.include_isolated_btn = QPushButton("✅ Inclure")
        self.include_isolated_btn.clicked.connect(self.parent_interface.toggle_include_isolated)
        self.include_isolated_btn.setEnabled(False)
        
        actions.addWidget(self.preserve_empty_btn)
        actions.addWidget(self.include_isolated_btn)
        
        layout.addLayout(actions)
        group.set_content_layout(layout)
        
        return group
    
    def _create_spans_group(self) -> QGroupBox:
        """Créer le groupe des spans associés"""
        group = QGroupBox("📝 Spans Associés")
        layout = QVBoxLayout()
        
        # Table des spans - SEULEMENT 2 COLONNES
        self.spans_table = QTableWidget()
        self.spans_table.setColumnCount(2)  # ← 2 colonnes uniquement
        self.spans_table.setHorizontalHeaderLabels(["Texte", "Font"])  # ← Headers
        
        # La colonne 0 (Texte) prend tout l'espace disponible
        self.spans_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        
        # La colonne 1 (Font) s'adapte au contenu
        self.spans_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        
        self.spans_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.spans_table.itemSelectionChanged.connect(self.parent_interface.on_span_table_selection)
        
        # Afficher les numéros de ligne à gauche (remplace la colonne #)
        self.spans_table.verticalHeader().setVisible(True)
        
        # Permettre le word wrap dans les cellules
        self.spans_table.setWordWrap(True)
        
        # Ajuster automatiquement la hauteur des lignes au contenu
        self.spans_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        layout.addWidget(self.spans_table)
        
        # Boutons de gestion
        span_btns = QHBoxLayout()
        
        self.move_up_btn = QPushButton("▲")
        self.move_up_btn.setFixedWidth(40)
        self.move_up_btn.clicked.connect(self.parent_interface.move_span_up)
        self.move_up_btn.setToolTip("Déplacer le span vers le haut (↑)")
        
        self.move_down_btn = QPushButton("▼")
        self.move_down_btn.setFixedWidth(40)
        self.move_down_btn.clicked.connect(self.parent_interface.move_span_down)
        self.move_down_btn.setToolTip("Déplacer le span vers le bas (↓)")
        
        self.remove_span_btn = QPushButton("✖ Retirer")
        self.remove_span_btn.clicked.connect(self.parent_interface.remove_span)
        self.remove_span_btn.setToolTip("Retirer le span du bloc (Del)")
        
        for btn in [self.move_up_btn, self.move_down_btn, self.remove_span_btn]:
            btn.setEnabled(False)
        
        span_btns.addWidget(self.move_up_btn)
        span_btns.addWidget(self.move_down_btn)
        span_btns.addWidget(self.remove_span_btn)
        span_btns.addStretch()
        
        layout.addLayout(span_btns)
        group.setLayout(layout)
        
        return group
    
    def _create_available_spans_group(self) -> QGroupBox:
        """Créer le groupe des spans disponibles"""
        group = QGroupBox("🔖 Isolated Spans Disponibles")
        layout = QVBoxLayout()
        
        self.available_spans_list = QListWidget()
        self.available_spans_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.available_spans_list.itemClicked.connect(self._on_span_clicked)
        
        layout.addWidget(self.available_spans_list)
        
        add_btn = QPushButton("➕ Ajouter au Bloc")
        add_btn.clicked.connect(self.parent_interface.add_spans_to_block)
        add_btn.setToolTip("Ajouter les spans sélectionnés au bloc MinerU sélectionné (A)")
        
        layout.addWidget(add_btn)
        
        # Label explicatif
        help_label = QLabel("💡 Sélectionnez plusieurs ISO dans la liste\ndes blocs pour créer un nouveau bloc")
        help_label.setStyleSheet("color: #666; font-size: 8pt;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        group.setLayout(layout)
        return group

    def _on_span_clicked(self, item):
        """
        Gère le clic sur un span dans la liste des disponibles.
        Délègue la gestion du clic à la fenêtre principale.
        """
        span_data = item.data(Qt.UserRole)
        if span_data:
            self.parent_interface.on_available_span_clicked(span_data)


            
    # def on_available_span_clicked(self, span_data: Dict[str, Any]):
        # """
        # Gère le clic sur un span dans la liste des disponibles.
        # Transmet l'état du clavier pour la sélection multiple.
        # """
        # from PyQt5.QtWidgets import QApplication
        # from PyQt5.QtCore import Qt

        # # Étape 1: Retrouver le bloc parent du span
        # parent_block = None
        # for block in self.data_manager.get_page_blocks():
            # if block.get('block_type') == 'isolated_span':
                # spans_in_block = block.get('matching_spans', [])
                # if spans_in_block and spans_in_block[0].get('id') == span_data.get('id'):
                    # parent_block = block
                    # break

        # if not parent_block:
            # return

        # # Étape 2: Trouver l'item correspondant dans la QListWidget principale
        # item_to_click = None
        # for i in range(self.control_panel.blocks_list.count()):
            # item = self.control_panel.blocks_list.item(i)
            # if item and item.data(Qt.UserRole).get('id') == parent_block.get('id'):
                # item_to_click = item
                # break

        # # Étape 3: Si on a trouvé l'item, on simule un clic dessus
        # if item_to_click:
            # modifiers = QApplication.keyboardModifiers()
            # self.on_block_list_click(item_to_click, modifiers)


    # def _on_span_clicked(self, item):
        # """Gérer le clic sur un span - sélection simple par défaut"""
        # # Si pas de modificateur (Ctrl/Shift), effacer les autres
        # from PyQt5.QtWidgets import QApplication
        # modifiers = QApplication.keyboardModifiers()
        
        # from PyQt5.QtCore import Qt
        # if not (modifiers & (Qt.ControlModifier | Qt.ShiftModifier)):
            # # Clic simple - effacer les autres sélections
            # self.available_spans_list.clearSelection()
            # item.setSelected(True)
        
        # span = item.data(Qt.UserRole)
        # # Récupérer le bloc parent de ce span
        # for block in self.parent_interface.data_manager.get_page_blocks():
            # if block.get('block_type') == 'isolated_span':
                # for s in block.get('matching_spans', []):
                    # if s['id'] == span['id']:
                        # self.parent_interface.select_isolated_block(block)  # ← APPEL
                        # return
    
    def _create_actions_group(self) -> QGroupBox:
        """Créer le groupe des actions"""
        group = QGroupBox("⚡ Actions")
        layout = QVBoxLayout()
        
        # Bouton créer bloc
        self.create_block_btn = QPushButton("🔗 Créer Bloc depuis ISO")
        self.create_block_btn.clicked.connect(self.parent_interface.create_block_from_selection)
        self.create_block_btn.setToolTip("Sélectionner plusieurs isolated_spans (Ctrl+Clic) et cliquer (C)")
        self.create_block_btn.setStyleSheet("background: #2196F3; color: white; font-weight: bold;")
        layout.addWidget(self.create_block_btn)
        
        layout.addWidget(QLabel("─" * 20))
        
        # Undo/Redo
        undo_redo_layout = QHBoxLayout()
        
        self.undo_btn = QPushButton("↶")
        self.undo_btn.setFixedWidth(40)
        self.undo_btn.clicked.connect(self.parent_interface.undo)
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Annuler (Ctrl+Z)")
        
        self.redo_btn = QPushButton("↷")
        self.redo_btn.setFixedWidth(40)
        self.redo_btn.clicked.connect(self.parent_interface.redo)
        self.redo_btn.setEnabled(False)
        self.redo_btn.setToolTip("Refaire (Ctrl+Y)")
        
        undo_redo_layout.addWidget(self.undo_btn)
        undo_redo_layout.addWidget(self.redo_btn)
        undo_redo_layout.addStretch()
        
        layout.addLayout(undo_redo_layout)
        
        layout.addWidget(QLabel("─" * 20))
        
        # Sauvegarder
        save_btn = QPushButton("💾 Générer fichiers de traduction")
        save_btn.clicked.connect(self.parent_interface.generate_translation_format_and_metadata_files)
        save_btn.setStyleSheet("background: #4CAF50; color: white; font-weight: bold;")
        save_btn.setToolTip("Génère _pour_traduction.json, _formatage.json et métadonnées (Ctrl+E)")
        
        template_btn = QPushButton("🖼️ Générer Template PDF")
        template_btn.clicked.connect(self.parent_interface.generate_pdf_template_file)
        template_btn.setStyleSheet("background: #2196F3; color: white; font-weight: bold;")
        
        layout.addWidget(save_btn)
        layout.addWidget(template_btn)
        
        group.setLayout(layout)
        group.setMaximumHeight(200)
        
        return group
    
    def update_navigation(self, current_page: int, total_pages: int):
        """Mettre à jour les contrôles de navigation"""
        self.page_label.setText(f"Page {current_page + 1}/{total_pages}")
        self.prev_btn.setEnabled(current_page > 0)
        self.next_btn.setEnabled(current_page < total_pages - 1)
    
    def populate_blocks_list(self, page_blocks: list):
        """Remplir la liste des blocs avec compteurs séparés"""
        self.blocks_list.clear()
        
        normal_idx = 0
        isolated_idx = 0
        
        for block in page_blocks:
            # Blocs MinerU normaux
            if block.get('block_type') and block.get('block_type') != 'isolated_span':
                spans = len(block.get('matching_spans', []))
                content = block.get('content', '')[:40]
                
                if spans == 0 and block.get('preserve_empty'):
                    icon = "🔒"
                    bg = QColor(220, 180, 220)
                elif spans == 0:
                    icon = "❌"
                    bg = QColor(255, 220, 150)
                elif block.get('match_source') == 'manual':
                    icon = "🖊"
                    bg = QColor(200, 255, 200)
                else:
                    icon = "✓"
                    bg = QColor(220, 240, 255)
                
                item = QListWidgetItem(f"{icon} B{normal_idx} ({spans}): {content}...")
                item.setData(Qt.UserRole, block)
                item.setBackground(bg)
                self.blocks_list.addItem(item)
                normal_idx += 1
            
            # Isolated spans
            elif block.get('block_type') == 'isolated_span':
                span = (block.get('matching_spans') or [{}])[0]
                content = span.get('text', '')[:30]
                include = block.get('include_in_output', True)
                
                icon = "✅" if include else "⬜"
                bg = QColor(200, 255, 200) if include else QColor(240, 240, 240)
                
                item = QListWidgetItem(f"{icon} ISO{isolated_idx}: {content}...")
                item.setData(Qt.UserRole, block)
                item.setBackground(bg)
                self.blocks_list.addItem(item)
                isolated_idx += 1
    
    def update_stats(self, page_blocks: list):
        """Mettre à jour les statistiques"""
        total = len([b for b in page_blocks if b.get('block_type') != 'isolated_span'])
        with_spans = len([
            b for b in page_blocks 
            if len(b.get('matching_spans', [])) > 0 and b.get('block_type') != 'isolated_span'
        ])
        manual = len([b for b in page_blocks if b.get('match_source') == 'manual'])
        preserved = len([b for b in page_blocks if b.get('preserve_empty')])
        isolated = len([b for b in page_blocks if b.get('block_type') == 'isolated_span'])
        iso_incl = len([
            b for b in page_blocks 
            if b.get('block_type') == 'isolated_span' and b.get('include_in_output')
        ])
        
        stats = f"<b>Blocs MinerU:</b> {total}<br>"
        stats += f"<b>Avec spans:</b> {with_spans}<br>"
        stats += f"<b>Manuels:</b> {manual}<br>"
        stats += f"<b>Vides conservés:</b> {preserved}<br>"
        stats += f"<hr><b>Isolated:</b> {isolated}<br>"
        stats += f"<b>Inclus:</b> {iso_incl}"
        
        self.stats_label.setText(stats)
    
    def update_button_states(self, undo_enabled: bool, redo_enabled: bool):
        """Mettre à jour l'état des boutons undo/redo"""
        self.undo_btn.setEnabled(undo_enabled)
        self.redo_btn.setEnabled(redo_enabled)


