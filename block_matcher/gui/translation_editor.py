import os
import re
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QHBoxLayout, QTextEdit,
    QSplitter, QListWidget, QListWidgetItem, QWidget, QLabel, QMessageBox,
    QCheckBox, QGroupBox, QLineEdit, QSpinBox, QFormLayout, QTabWidget
)
from PyQt5.QtGui import (
    QFontDatabase, QFont, QColor, QTextDocument, 
    QTextCursor, QTextCharFormat, QPainter, QPen, QBrush, QIcon
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRect

from ..core.extract import DualOutputGenerator
from ..core.svg_manager import SvgManager

# --- WIDGET : BOUTON D'ALIGNEMENT ---
class AlignmentButton(QPushButton):
    """
    Bouton cyclique pour l'alignement (Gauche -> Centre -> Droite -> Justifié).
    """
    def __init__(self, initial_align="left", parent=None):
        super().__init__(parent)
        self.align_states = ["left", "center", "right", "justify"]
        
        if initial_align not in self.align_states:
            initial_align = "left"
        self.current_align = initial_align
        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Alignement : {self.get_label()}")
        self.clicked.connect(self.cycle_alignment)

    def get_value(self):
        return self.current_align

    def get_label(self):
        labels = {
            "left": "Gauche", 
            "center": "Centré", 
            "right": "Droite",
            "justify": "Justifié"
        }
        return labels.get(self.current_align, "?")

    def cycle_alignment(self):
        idx = self.align_states.index(self.current_align)
        new_idx = (idx + 1) % len(self.align_states)
        self.current_align = self.align_states[new_idx]
        self.setToolTip(f"Alignement : {self.get_label()}")
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width(); h = self.height()
        pen = QPen(QColor(60, 60, 60)); pen.setWidth(2)
        painter.setPen(pen)
        
        if self.current_align == "justify":
            lines_config = [(0.25, 0.8), (0.45, 0.8), (0.65, 0.8), (0.85, 0.8)]
        else:
            lines_config = [(0.3, 0.8), (0.5, 0.6), (0.7, 0.8)]
        
        for y_factor, width_factor in lines_config:
            line_w = w * 0.6 * width_factor
            y = h * y_factor
            if self.current_align == "left": x = w * 0.2
            elif self.current_align == "center": x = (w - line_w) / 2
            elif self.current_align == "right": x = w * 0.8 - line_w
            else: x = (w - line_w) / 2
            painter.drawLine(int(x), int(y), int(x + line_w), int(y))


class TrackingTextEdit(QTextEdit):
    focus_received = pyqtSignal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def focusInEvent(self, event):
        self.focus_received.emit(self)
        super().focusInEvent(event)


# --- NOUVEAU WIDGET : PROPRIÉTÉS DE LISTE ---
class ListPropertiesWidget(QGroupBox):
    """
    Panneau pour configurer si un bloc est une liste, sa puce et son indentation.
    Modifie directement le bloc passé en paramètre.
    """
    # NOUVEAU : signal émis quand le champ puce reçoit le focus
    bullet_focus = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__("Propriétés de Liste", parent)
        self.current_block = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Checkbox activateur
        self.chk_is_list = QCheckBox("Est une liste")
        self.chk_is_list.toggled.connect(self.on_toggled)
        layout.addWidget(self.chk_is_list)
        
        # Formulaire détails
        self.form_widget = QWidget()
        form_layout = QFormLayout()
        form_layout.setContentsMargins(0,0,0,0)
        
        self.txt_bullet = QLineEdit()
        self.txt_bullet.setPlaceholderText("Ex: 1. ou •")
        self.txt_bullet.textChanged.connect(self.on_change)
        # NOUVEAU : quand la puce prend le focus, on prévient le parent
        self.txt_bullet.installEventFilter(self)

        self.spin_indent = QSpinBox()
        self.spin_indent.setRange(0, 200)
        self.spin_indent.setValue(20) # Valeur par défaut raisonnable
        self.spin_indent.setSuffix(" pt")
        self.spin_indent.valueChanged.connect(self.on_change)
        
        self.chk_hang = QCheckBox("Retrait suspendu (Hang)")
        self.chk_hang.setToolTip("Si coché, les lignes suivantes sont alignées sous le texte (pas sous la puce).")
        self.chk_hang.setChecked(True)
        self.chk_hang.toggled.connect(self.on_change)

        form_layout.addRow("Puce/Num :", self.txt_bullet)
        form_layout.addRow("Retrait :", self.spin_indent)
        form_layout.addRow("", self.chk_hang)
        
        self.form_widget.setLayout(form_layout)
        layout.addWidget(self.form_widget)
        
        self.setLayout(layout)
        # Etat initial caché
        self.form_widget.setVisible(False)
        self.setEnabled(False) # Désactivé tant qu'aucun bloc sélectionné

    def eventFilter(self, obj, event):
        # On intercepte le focus sur txt_bullet
        if obj is self.txt_bullet and event.type() == event.FocusIn:
            # On émet le signal pour prévenir TranslationEditorDialog
            self.bullet_focus.emit(self.txt_bullet)
        return super().eventFilter(obj, event)

    def load_block(self, block):
        """Charge les données du bloc sélectionné."""
        self.current_block = block
        self.setEnabled(True)
        
        # On bloque les signaux pour éviter de déclencher on_change pendant le chargement
        self.chk_is_list.blockSignals(True)
        self.txt_bullet.blockSignals(True)
        self.spin_indent.blockSignals(True)
        self.chk_hang.blockSignals(True)
        
        # Lecture des valeurs (ou défauts)
        is_list = block.get('is_list', False)
        
        self.chk_is_list.setChecked(is_list)
        self.form_widget.setVisible(is_list)
        
        self.txt_bullet.setText(block.get('list_bullet', '•'))
        self.spin_indent.setValue(int(block.get('list_indent', 20)))
        self.chk_hang.setChecked(block.get('list_hang', True))
        
        # Rétablissement des signaux
        self.chk_is_list.blockSignals(False)
        self.txt_bullet.blockSignals(False)
        self.spin_indent.blockSignals(False)
        self.chk_hang.blockSignals(False)

    def on_toggled(self, checked):
        if not self.current_block:
            return
        self.current_block['is_list'] = checked
        self.form_widget.setVisible(checked)
        # Si on active, on s'assure que les valeurs par défaut sont présentes
        if checked:
            if 'list_bullet' not in self.current_block:
                self.current_block['list_bullet'] = ''
            if 'list_indent' not in self.current_block:
                self.current_block['list_indent'] = 20
            if 'list_hang' not in self.current_block:
                self.current_block['list_hang'] = True
            
            # Refresh UI pour afficher les défauts
            self.txt_bullet.setText(self.current_block['list_bullet'])
            self.spin_indent.setValue(self.current_block['list_indent'])

    def on_change(self):
        if not self.current_block:
            return
        # Sauvegarde immédiate dans le bloc en mémoire
        self.current_block['list_bullet'] = self.txt_bullet.text()
        self.current_block['list_indent'] = self.spin_indent.value()
        self.current_block['list_hang'] = self.chk_hang.isChecked()



class TranslationEditorDialog(QDialog):
    def __init__(self, session_data, session_root_path, parent=None):
        super().__init__(parent)
        self.session_data = session_data
        self.session_root = session_root_path
        self.setWindowTitle("Éditeur de Traduction")
        self.resize(1400, 900)

        self.current_editor = None
        self.current_default_style = None
        self.is_night_mode = False

        # Données
        raw_styles = self.session_data.get('global_styles', {})
        if isinstance(raw_styles, dict) and 'styles' in raw_styles:
            self.global_styles = raw_styles.get('styles', {})
        else:
            self.global_styles = raw_styles

        self.enriched_data = self.session_data.get('enriched_data', [])
        self.page_dimensions = self.session_data.get('page_dimensions', {})
        if 'translation_overrides' not in self.session_data:
            self.session_data['translation_overrides'] = {}
        self.translation_overrides = self.session_data['translation_overrides']
        
        # Cache Blocks
        self.block_map = {}
        for page in self.enriched_data:
            for block in page:
                if 'id' in block:
                    self.block_map[block['id']] = block
                # Ajout pour les groupes fusionnés
                if 'merge_group_id' in block:
                    gid = block['merge_group_id']
                    # On mappe l'ID du groupe vers le PREMIER bloc du groupe
                    # C'est dans ce bloc (ou tous) qu'on stockera les props de liste
                    if gid not in self.block_map:
                        self.block_map[gid] = block


        self.pdf_to_file_map = {}
        self.font_map = {}
        self.load_local_fonts()
        
        # Initialisation du gestionnaire SVG
        basename = self.session_data.get('basename', 'project')
        self.svg_manager = SvgManager(self.session_root, basename)

        self.generator = DualOutputGenerator(
            enriched_data=self.enriched_data,
            page_dimensions=self.page_dimensions,
            global_styles_data=self.session_data.get('global_styles', {})
        )

        self.rich_builder = RichTextBuilder(
            global_styles=self.global_styles,
            font_map=self.font_map,
            enriched_data=self.enriched_data
        )

        self.init_ui()
        self.load_data()
        self.load_style_palette()
        self.populate_images_list()
        self.apply_theme()

    def load_local_fonts(self):
        mapping_path = os.path.join(self.session_root, "font_mapping.json")
        fonts_dir = os.path.join(self.session_root, "fonts")
        if not os.path.exists(mapping_path): return
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                self.pdf_to_file_map = json.load(f)
        except: return

        for pdf_font, filename in self.pdf_to_file_map.items():
            if not filename: continue
            font_path = os.path.join(fonts_dir, filename)
            if os.path.exists(font_path):
                idx = QFontDatabase.addApplicationFont(font_path)
                if idx != -1:
                    families = QFontDatabase.applicationFontFamilies(idx)
                    if families: self.font_map[pdf_font] = families[0]

    def init_ui(self):
        main_layout = QVBoxLayout()
        
        top_bar = QHBoxLayout()
        self.chk_night_mode = QCheckBox("🌙 Mode Nuit (Fond sombre)")
        self.chk_night_mode.setStyleSheet("font-weight: bold; color: #555;")
        self.chk_night_mode.stateChanged.connect(self.toggle_night_mode)
        top_bar.addWidget(self.chk_night_mode)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Tableau
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Align", "Original", "Traduction"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 50)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        
        # CONNEXION SÉLECTION
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        
        splitter.addWidget(self.table)
        
        # Panneau Droite
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # 1. Palette
        lbl_palette = QLabel("Palette de Styles")
        lbl_palette.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        right_layout.addWidget(lbl_palette)
        
        self.default_style_widget = QWidget()
        self.default_style_widget.setStyleSheet("background: #e6f3ff; border: 1px solid #b3d9ff; border-radius: 4px;")
        def_layout = QVBoxLayout()
        def_layout.setContentsMargins(5, 5, 5, 5)
        lbl_def_title = QLabel("Style par défaut (Bloc)")
        lbl_def_title.setStyleSheet("font-size: 10px; color: #005cbf; font-weight: bold;")
        self.lbl_def_preview = QLabel("Sélectionnez un bloc")
        self.lbl_def_info = QLabel("...")
        self.lbl_def_info.setStyleSheet("color: gray; font-size: 9px;")
        def_layout.addWidget(lbl_def_title); def_layout.addWidget(self.lbl_def_preview); def_layout.addWidget(self.lbl_def_info)
        self.default_style_widget.setLayout(def_layout)
        self.default_style_widget.setCursor(Qt.PointingHandCursor)
        self.default_style_widget.mousePressEvent = self.apply_default_style
        right_layout.addWidget(self.default_style_widget)
        right_layout.addSpacing(10)
        
        # --- ONGLETS POUR STYLES ET IMAGES ---
        self.side_tabs = QTabWidget()
        self.side_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #C4C4C3; }
            QTabBar::tab { background: #E1E1E1; padding: 4px 10px; border: 1px solid #C4C4C3; border-bottom: none; }
            QTabBar::tab:selected { background: #FFF; font-weight: bold; }
        """)
        
        # Onglet 1: Styles Globaux
        styles_tab = QWidget()
        styles_layout = QVBoxLayout(styles_tab)
        styles_layout.setContentsMargins(2, 2, 2, 2)
        
        lbl_globals = QLabel("Styles Globaux (gs)")
        lbl_globals.setStyleSheet("font-weight: bold; font-size: 11px;")
        styles_layout.addWidget(lbl_globals)
        
        self.style_list = QListWidget()
        self.style_list.itemClicked.connect(self.apply_style_from_palette)
        styles_layout.addWidget(self.style_list)
        
        self.side_tabs.addTab(styles_tab, "Styles")
        
        # Onglet 2: Images SVG
        images_tab = QWidget()
        images_layout = QVBoxLayout(images_tab)
        images_layout.setContentsMargins(2, 2, 2, 2)
        
        lbl_images = QLabel("Insérer Image/SVG")
        lbl_images.setStyleSheet("font-weight: bold; font-size: 11px;")
        images_layout.addWidget(lbl_images)
        
        self.images_list = QListWidget()
        self.images_list.setIconSize(QSize(32, 32))
        self.images_list.setToolTip("Double-cliquez pour insérer l'image")
        self.images_list.itemClicked.connect(self.insert_svg_tag)
        images_layout.addWidget(self.images_list)
        
        btn_refresh_imgs = QPushButton("Rafraîchir")
        btn_refresh_imgs.clicked.connect(self.populate_images_list)
        images_layout.addWidget(btn_refresh_imgs)
        
        self.side_tabs.addTab(images_tab, "Images")
        
        right_layout.addWidget(self.side_tabs)
        
        # 2. Gestion Liste (NOUVEAU)
        right_layout.addSpacing(10)
        self.list_props_widget = ListPropertiesWidget()
        # NOUVEAU : quand la puce prend le focus, on met à jour current_editor
        self.list_props_widget.bullet_focus.connect(self.on_bullet_focus)
        right_layout.addWidget(self.list_props_widget)
        
        right_panel.setLayout(right_layout)
        right_panel.setMaximumWidth(320) # Légèrement plus large pour les onglets
        
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        btn_layout = QHBoxLayout()
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.close)
        self.btn_save = QPushButton("Sauvegarder")
        self.btn_save.setStyleSheet("background-color: #d4edda; color: #155724; font-weight: bold;")
        self.btn_save.clicked.connect(self.save_changes)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(btn_close)
        
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)
        
    def on_bullet_focus(self, widget):
        """
        Appelé quand le champ Puce/Num reçoit le focus.
        On bascule current_editor sur ce champ pour que la palette applique les styles sur la puce.
        """
        self.current_editor = widget
        # Pas de block_id pour ce widget, donc on ne met pas à jour le panneau de style par défaut ici.

    def on_table_selection_changed(self):
        """Met à jour le panneau Liste quand on change de ligne."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.list_props_widget.setEnabled(False)
            return
            
        row = selected_rows[0].row()
        id_item = self.table.item(row, 0)
        if not id_item: return
        
        block_id = id_item.text()
        if block_id in self.block_map:
            block = self.block_map[block_id]
            self.list_props_widget.load_block(block)

    def toggle_night_mode(self, state):
        self.is_night_mode = (state == Qt.Checked)
        self.apply_theme()

    def apply_theme(self):
        if self.is_night_mode:
            bg_target = "#2d2d2d"; bg_source = "#3a3a3a"; border = "none"
        else:
            bg_target = "#ffffff"; bg_source = "#f0f0f0"; border = "none"
        rows = self.table.rowCount()
        for r in range(rows):
            w_source = self.table.cellWidget(r, 2)
            if w_source: w_source.setStyleSheet(f"QTextEdit {{ background: {bg_source}; border: {border}; padding: 0px; }}")
            w_target = self.table.cellWidget(r, 3)
            if w_target: w_target.setStyleSheet(f"QTextEdit {{ background: {bg_target}; border: {border}; padding: 0px; }}")

    def update_default_style_panel(self, block_id):
        style = self.rich_builder._get_block_default_style(block_id)
        if not style:
            self.lbl_def_preview.setText("Non défini")
            self.lbl_def_info.setText(f"ID: {block_id}")
            self.current_default_style = None
            return
        fmt = self.rich_builder._create_char_format(style)
        font = fmt.font()
        font.setPointSizeF(min(font.pointSizeF(), 14))
        self.lbl_def_preview.setText("Aa Bb Cc 123")
        self.lbl_def_preview.setFont(font)
        col = fmt.foreground().color()
        self.lbl_def_preview.setStyleSheet(f"color: {col.name()};")
        font_name = style.get('police', 'Unknown')
        font_size = style.get('taille', '?')
        self.lbl_def_info.setText(f"{font_name} • {font_size}pt")
        self.current_default_style = style

    def apply_default_style(self, event):
        if not self.current_editor or not self.current_default_style: return
        fmt = self.rich_builder._create_char_format(self.current_default_style)
        
        if isinstance(self.current_editor, QTextEdit):
            cursor = self.current_editor.textCursor()
            cursor.setCharFormat(fmt)
            if not cursor.hasSelection(): self.current_editor.setTextCursor(cursor)
            self.current_editor.setFocus()

    def load_style_palette(self):
        self.style_list.clear()
        sorted_keys = sorted(self.global_styles.keys(), key=lambda x: int(x[2:]) if x[2:].isdigit() else 0)
        for gs_id in sorted_keys:
            style = self.global_styles[gs_id]
            item = QListWidgetItem(); self.style_list.addItem(item)
            widget = QWidget(); v_layout = QVBoxLayout(); v_layout.setContentsMargins(5, 5, 5, 5); v_layout.setSpacing(2)
            line1 = QHBoxLayout()
            lbl_id = QLabel(gs_id); lbl_id.setFixedWidth(35); lbl_id.setStyleSheet("color: #666; font-weight: bold; background: #eee; border-radius: 3px; padding: 2px;"); lbl_id.setAlignment(Qt.AlignCenter)
            lbl_preview = QLabel("Aa Bb Cc 123")
            fmt = self.rich_builder._create_char_format(style)
            font = fmt.font()
            font.setPointSizeF(min(font.pointSizeF(), 14))
            lbl_preview.setFont(font)
            col = fmt.foreground().color()
            lbl_preview.setStyleSheet(f"color: {col.name()};")
            line1.addWidget(lbl_id); line1.addWidget(lbl_preview); line1.addStretch()
            font_name = style.get('police', 'Unknown'); font_size = style.get('taille', '?')
            info_text = f"{font_name} • {font_size}pt"
            lbl_info = QLabel(info_text); lbl_info.setStyleSheet("color: gray; font-size: 10px; margin-left: 40px;")
            v_layout.addLayout(line1); v_layout.addWidget(lbl_info); widget.setLayout(v_layout)
            item.setSizeHint(widget.sizeHint())
            self.style_list.setItemWidget(item, widget)
            item.setData(Qt.UserRole, gs_id)

    def populate_images_list(self):
        """Charge les images disponibles depuis SvgManager"""
        self.images_list.clear()
        self.svg_manager.load_mapping()
        
        mapping = self.svg_manager.mapping_data
        
        for alias, data in mapping.items():
            file_name = data.get('file', '')
            file_path = self.svg_manager.svg_dir / file_name
            
            item = QListWidgetItem(alias)
            ratio = data.get('ratio_largeur_hauteur', 1.0)
            item.setToolTip(f"ID: {alias}\nFichier: {file_name}\nRatio: {ratio}")
            
            if file_path.exists():
                icon = QIcon(str(file_path))
                item.setIcon(icon)
            else:
                item.setText(f"❌ {alias}")
            
            item.setData(Qt.UserRole, alias)
            self.images_list.addItem(item)

    def insert_svg_tag(self, item):
        """Insère la balise SVG au curseur"""
        if not self.current_editor:
            QMessageBox.information(self, "Info", "Veuillez cliquer dans une zone de texte cible avant d'insérer une image.")
            return

        alias = item.data(Qt.UserRole)
        tag = f'<svg id="{alias}"/>'
        
        if isinstance(self.current_editor, QTextEdit):
            cursor = self.current_editor.textCursor()
            cursor.insertText(tag)
            self.current_editor.setFocus()
        elif isinstance(self.current_editor, QLineEdit):
            self.current_editor.insert(tag)
            self.current_editor.setFocus()

    def on_editor_focus(self, editor_widget):
        self.current_editor = editor_widget
        block_id = editor_widget.property("block_id")
        if block_id: self.update_default_style_panel(block_id)

    def apply_style_from_palette(self, item):
        if not self.current_editor:
            return

        gs_id = item.data(Qt.UserRole)
        style = self.global_styles.get(gs_id)
        if not style:
            return

        # CAS 1 : éditeur rich text (TQextEdit) -> comportement actuel
        if isinstance(self.current_editor, QTextEdit):
            fmt = self.rich_builder._create_char_format(style)
            cursor = self.current_editor.textCursor()
            cursor.mergeCharFormat(fmt)
            if not cursor.hasSelection():
                self.current_editor.setTextCursor(cursor)
            self.current_editor.setFocus()
            return

        # CAS 2 : champ Puce/Num (QLineEdit dans ListPropertiesWidget)
        if isinstance(self.current_editor, QLineEdit) and self.list_props_widget is not None:
            text = self.current_editor.text() or ""
            tagged = f"<{gs_id}>{text}</{gs_id}>"
            self.current_editor.setText(tagged)
            if self.list_props_widget.current_block is not None:
                self.list_props_widget.current_block['list_bullet'] = tagged
            self.current_editor.setFocus()
            return

    def highlight_style_from_cursor(self, editor):
        cursor = editor.textCursor()
        fmt = cursor.charFormat()
        found_gs_id = self.rich_builder.find_matching_style_id(fmt)
        if found_gs_id:
            for i in range(self.style_list.count()):
                item = self.style_list.item(i)
                if item.data(Qt.UserRole) == found_gs_id:
                    self.style_list.setCurrentItem(item); self.style_list.scrollToItem(item); break
        else: self.style_list.clearSelection()

    def load_data(self):
        try:
            items = self.generator._generate_translation_format(self.enriched_data)
            self.table.setRowCount(len(items))
            for row, item in enumerate(items):
                block_id = item['id']
                raw_source = item['source']
                override_text = self.translation_overrides.get(block_id, raw_source)
                
                self.table.setItem(row, 0, QTableWidgetItem(block_id))
                
                # Align
                current_align = "left"
                if block_id in self.block_map: current_align = self.block_map[block_id].get('align', 'left')
                align_btn = AlignmentButton(current_align)
                w_container = QWidget(); l_container = QHBoxLayout(w_container); l_container.setContentsMargins(0,0,0,0); l_container.setAlignment(Qt.AlignCenter); l_container.addWidget(align_btn)
                self.table.setCellWidget(row, 1, w_container)
                w_container.setProperty("align_btn", align_btn)
                
                doc_source = self.rich_builder.build_document(block_id, raw_source)
                edit_source = TrackingTextEdit(); edit_source.setDocument(doc_source); edit_source.setReadOnly(True); edit_source.setProperty("block_id", block_id)
                edit_source.focus_received.connect(self.on_editor_focus)
                edit_source.cursorPositionChanged.connect(lambda w=edit_source: self.highlight_style_from_cursor(w))
                self.table.setCellWidget(row, 2, edit_source)
                
                doc_target = self.rich_builder.build_document(block_id, override_text)
                edit_target = TrackingTextEdit(); edit_target.setDocument(doc_target); edit_target.setProperty("block_id", block_id)
                edit_target.focus_received.connect(self.on_editor_focus)
                edit_target.cursorPositionChanged.connect(lambda w=edit_target: self.highlight_style_from_cursor(w))
                self.table.setCellWidget(row, 3, edit_target)
                
                doc_height = doc_source.size().height()
                self.table.setRowHeight(row, max(35, int(doc_height + 2)))
        except Exception as e:
            print(f"[ERROR] load_data: {e}")

    def save_changes(self):
        print("[INFO] Début de la sauvegarde...")
        changes_count = 0; align_changes_count = 0
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 0)
            if not id_item: continue
            block_id = id_item.text()
            
            widget_target = self.table.cellWidget(row, 3)
            widget_source = self.table.cellWidget(row, 2)
            if widget_target:
                tagged_target = self.rich_builder.document_to_tagged_text(widget_target.document(), block_id)
                tagged_source = self.rich_builder.document_to_tagged_text(widget_source.document(), block_id) if widget_source else ""
                if tagged_source != tagged_target:
                    self.translation_overrides[block_id] = tagged_target
                    changes_count += 1
                else:
                    if block_id in self.translation_overrides: del self.translation_overrides[block_id]
            
            w_container = self.table.cellWidget(row, 1)
            if w_container:
                align_btn = w_container.property("align_btn")
                if align_btn and block_id in self.block_map:
                    new_align = align_btn.get_value()
                    block = self.block_map[block_id]
                    old_align = block.get('align', 'left')
                    if new_align != old_align:
                        block['align'] = new_align
                        align_changes_count += 1

        if changes_count >= 0 or align_changes_count >= 0:
            try:
                session_file = os.path.join(self.session_root, f"{self.session_data.get('session_name', 'session')}_session.json")
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(self.session_data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "Sauvegarde réussie", f"{changes_count} traductions modifiées.\n{align_changes_count} alignements modifiés.\nPropriétés de listes mises à jour.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Échec sauvegarde : {e}")

class RichTextBuilder:
    def __init__(self, global_styles, font_map, enriched_data):
        self.global_styles = global_styles; self.font_map = font_map; self.enriched_data = enriched_data
        self.block_defaults_cache = {}
        self._build_cache()
    def _build_cache(self):
        if not isinstance(self.enriched_data, list): return
        for page in self.enriched_data:
            if not isinstance(page, list): continue
            for block in page:
                def_style = block.get('default_style')
                if not def_style: continue
                if 'id' in block: self.block_defaults_cache[block['id']] = def_style
                if 'merge_group_id' in block:
                    merge_id = block['merge_group_id']
                    if merge_id not in self.block_defaults_cache: self.block_defaults_cache[merge_id] = def_style
    def _get_block_default_style(self, block_id): return self.block_defaults_cache.get(block_id, {})
    def _create_char_format(self, style_dict):
        fmt = QTextCharFormat()
        pdf_font = style_dict.get('police', 'Arial')
        qt_family = self.font_map.get(pdf_font)
        if qt_family is None: qt_family = 'Arial'
        font = QFont(qt_family)
        try: font.setPointSizeF(float(style_dict.get('taille', 10)))
        except: font.setPointSizeF(10.0)
        lname = str(pdf_font).lower()
        if "bold" in lname or "black" in lname: font.setBold(True)
        if "italic" in lname or "oblique" in lname or "ita" in lname: font.setItalic(True)
        fmt.setFont(font)
        try: c = int(style_dict.get('couleur', 0)); color = QColor((c >> 16) & 255, (c >> 8) & 255, c & 255); fmt.setForeground(color)
        except: fmt.setForeground(QColor(0,0,0))
        return fmt
    def find_matching_style_id(self, fmt, block_default_style=None):
        if block_default_style:
            def_fmt = self._create_char_format(block_default_style)
            if self._formats_are_equal(fmt, def_fmt): return None
        for gs_id, style_dict in self.global_styles.items():
            ref_fmt = self._create_char_format(style_dict)
            if self._formats_are_equal(fmt, ref_fmt): return gs_id
        return None
    def _formats_are_equal(self, fmt1, fmt2):
        f1, f2 = fmt1.font(), fmt2.font()
        if abs(f1.pointSizeF() - f2.pointSizeF()) > 0.5: return False
        if f1.family() != f2.family(): return False
        if f1.weight() != f2.weight(): return False
        if f1.italic() != f2.italic(): return False
        if fmt1.foreground().color() != fmt2.foreground().color(): return False
        return True
    def build_document(self, block_id, text_source):
        doc = QTextDocument(); doc.setDocumentMargin(0); cursor = QTextCursor(doc)
        default_style = self._get_block_default_style(block_id); default_format = self._create_char_format(default_style)
        segments = []; tag_pattern = re.compile(r'<(gs\d+)>(.*?)</\1>|<svg id="([^"]*)"\s*/>|([^<]+)', re.DOTALL)
        for match in tag_pattern.finditer(text_source):
            if match.group(1): 
                gs_id = match.group(1); content = match.group(2); style = self.global_styles.get(gs_id, default_style)
                if content: segments.append({'text': content, 'format': self._create_char_format(style)})
            elif match.group(3):
                # SVG tag - on l'affiche comme texte pour l'instant dans l'éditeur (ou placeholder)
                svg_id = match.group(3)
                segments.append({'text': f'<svg id="{svg_id}"/>', 'format': default_format})
            elif match.group(4):
                content = match.group(4)
                if content: segments.append({'text': content, 'format': default_format})
        corrected = []
        for i, seg in enumerate(segments):
            if corrected:
                prev = corrected[-1]
                if not prev['text'].endswith((' ', '\n')) and not seg['text'].startswith((' ', '\n')): corrected.append({'text': ' ', 'format': prev['format']})
            corrected.append(seg)
        for seg in corrected:
            text_clean = re.sub(r' +', ' ', seg['text'])
            cursor.setCharFormat(seg['format']); cursor.insertText(text_clean)
        return doc
    def document_to_tagged_text(self, doc, block_id):
        output = ""; current_gs = None; default_style = self._get_block_default_style(block_id)
        block = doc.begin()
        while block.isValid():
            iter_frag = block.begin()
            while not iter_frag.atEnd():
                frag = iter_frag.fragment()
                if frag.isValid():
                    text = frag.text(); fmt = frag.charFormat()
                    # Si c'est un tag SVG littéral (inséré comme texte), on le laisse tel quel
                    # La logique ici est simple : tout texte avec style est wrappé.
                    # Si le texte est <svg id="..."/>, il sera wrappé si son style diffère du défaut,
                    # ce qui n'est pas grave, mais idéalement il devrait être neutre.
                    
                    gs_id = self.find_matching_style_id(fmt, default_style)
                    if gs_id != current_gs:
                        if current_gs is not None: output += f"</{current_gs}>"
                        if gs_id is not None: output += f"<{gs_id}>"
                        current_gs = gs_id
                    output += text
                iter_frag += 1
            if current_gs is not None: output += f"</{current_gs}>"; current_gs = None
            if block.next().isValid(): output += "\n"
            block = block.next()
        return output
