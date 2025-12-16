import os
import json
import re

from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QComboBox, QVBoxLayout, QLabel,
    QPushButton, QLineEdit, QHeaderView, QTableWidgetItem
)
from PyQt5.QtGui import QFontDatabase, QFont
from PyQt5.QtCore import Qt

class FontMappingPanel(QWidget):
    def __init__(self, session_path, pdf_path):
        super().__init__()
        self.session_root = session_path
        self.pdf_path = pdf_path
        self.font_mapping_path = os.path.join(self.session_root, "font_mapping.json")
        self.fonts_dir = os.path.join(self.session_root, "fonts")
        self.font_mapping = self.load_font_mapping()
        self.load_local_fonts()
        self.init_ui()
        self.populate_font_table()
        self.update_all_preview_labels()

    def save_font_mapping(self):
        try:
            with open(self.font_mapping_path, "w", encoding="utf-8") as f:
                json.dump(self.font_mapping, f, indent=2, ensure_ascii=False)
            print("[DEBUG] Mapping sauvegardé avec succès.")
        except Exception as e:
            print(f"[ERROR] Échec de sauvegarde du mapping : {e}")

    def get_pdf_fonts(self):
        import fitz  # PyMuPDF
        fonts_found = set()
        if not os.path.isfile(self.pdf_path):
            print("[ERROR] Fichier PDF introuvable.")
            return []
        try:
            doc = fitz.open(self.pdf_path)
            for page in doc:
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            font_name = span.get("font")
                            if font_name:
                                fonts_found.add(font_name)
            doc.close()
        except Exception as e:
            print(f"[ERROR] Exception lors de l'extraction des polices : {e}")
            return []
        return sorted(fonts_found)

    def load_font_mapping(self):
        if os.path.isfile(self.font_mapping_path):
            print(f"[DEBUG] Chargement du fichier de mapping existant : {self.font_mapping_path}")
            with open(self.font_mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        else:
            mapping = {}
            pdf_fonts = self.get_pdf_fonts()
            if not pdf_fonts:
                print("[WARNING] Aucune police extraite du PDF pour initialiser le mapping")
            for font_name in pdf_fonts:
                mapping[font_name] = ""
            with open(self.font_mapping_path, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)
        return mapping
        
    def load_local_fonts(self):
        # 1. Nettoyage préalable
        if not os.path.isdir(self.fonts_dir): os.makedirs(self.fonts_dir)
        self.fonts_local_info = []
        
        # Instance pour Qt5
        font_db = QFontDatabase()
        
        # Dictionnaire temporaire pour dédoublonner : clé = (famille, style), valeur = path
        unique_fonts = {}

        # 2. Chargement des fichiers
        # On fait deux passes ou on trie pour charger les fichiers "spécifiques" (ex: Bold) avant les génériques ?
        # En réalité, Qt gère ça, mais on veut savoir QUEL fichier a apporté QUEL style.
        
        # Malheureusement QFontDatabase ne dit pas "ce style vient de ce fichier précis".
        # Il dit "Pour cette famille (qui est un agrégat de fichiers), voici les styles dispos".
        
        # ASTUCE : On va ajouter les fichiers UN PAR UN, et regarder ce qui change/apparait.
        # C'est lourd mais précis.
        
        # On vide tout d'abord pour être propre (si refresh)
        # Note: removeAllApplicationFonts() ne marche que si on a gardé les IDs.
        # Ici on suppose qu'on repart de zéro ou que l'OS gère.
        
        font_files = [f for f in os.listdir(self.fonts_dir) if f.lower().endswith((".ttf", ".otf"))]
        
        for filename in font_files:
            font_path = os.path.join(self.fonts_dir, filename)
            
            # On charge ce fichier spécifique
            font_id = QFontDatabase.addApplicationFont(font_path)
            
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    family = families[0]
                    # On récupère les styles *déclarés* par ce fichier
                    # Attention: Qt peut retourner tous les styles de la famille déjà chargés par d'autres fichiers !
                    # C'est là le piège.
                    
                    # Pour contourner, on se fie au fait qu'on veut juste lister ce qui est disponible
                    # On va stocker le fichier comme "source" pour cette combinaison Famille+Style.
                    
                    # Pour être plus juste, on associe ce fichier à TOUS les styles que Qt rapporte pour cette famille
                    # C'est une approximation acceptable : si Arial.ttf permet "Bold", alors mapper Arial.ttf pour du Bold est valide.
                    
                    styles = font_db.styles(family)
                    for style in styles:
                        key = (family, style)
                        # Si on a déjà cette combinaison, est-ce qu'on l'écrase ?
                        # On peut préférer le fichier dont le nom contient le style (ex: "Arial_Bold.ttf" > "Arial.ttf" pour Bold)
                        
                        if key not in unique_fonts:
                            unique_fonts[key] = font_path
                        else:
                            # Heuristique simple : si le nom du fichier contient le style, on le priorise
                            current_path = unique_fonts[key]
                            current_name = os.path.basename(current_path).lower()
                            new_name = filename.lower()
                            style_lower = style.lower()
                            
                            if style_lower in new_name and style_lower not in current_name:
                                unique_fonts[key] = font_path

        # 3. Conversion en liste pour l'IHM
        for (family, style), path in unique_fonts.items():
            self.fonts_local_info.append((family, path, style))
            
        # Tri pour un affichage groupé
        self.fonts_local_info.sort(key=lambda x: (x[0], x[2]))


    def init_ui(self):
        layout = QVBoxLayout()
        refresh_btn = QPushButton("Rafraîchir polices locales")
        refresh_btn.clicked.connect(self.refresh_local_fonts)
        self.font_table = QTableWidget()
        self.font_table.setColumnCount(3)
        self.font_table.setHorizontalHeaderLabels(["Police PDF", "Police locale", "Aperçu"])
        self.font_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.preview_edit = QLineEdit()
        self.preview_edit.setPlaceholderText("Texte d'aperçu modifiable pour toutes les lignes")
        self.preview_edit.textChanged.connect(self.on_preview_text_changed)
        layout.addWidget(refresh_btn)
        layout.addWidget(self.font_table)
        layout.addWidget(QLabel("Texte d'aperçu"))
        layout.addWidget(self.preview_edit)
        self.setLayout(layout)
        self.resize(900, 430)

    def populate_font_table(self):
        pdf_fonts = list(self.font_mapping.keys())
        self.font_table.setRowCount(len(pdf_fonts))
        for i, pdf_font in enumerate(pdf_fonts):
            self.font_table.setItem(i, 0, QTableWidgetItem(pdf_font))
            combo = QComboBox()
            selected_label = None
            
            sorted_fonts = sorted(self.fonts_local_info, key=lambda x: (x[0], x[2]))
            
            for family, path, style in sorted_fonts:
                label = f"{family} ({style})"
                combo.addItem(label, {"path": path, "style": style, "family": family})
                
                mapping_file = self.font_mapping.get(pdf_font, "")
                if mapping_file and os.path.basename(path) == mapping_file:
                    selected_label = label

            if selected_label:
                idx = combo.findText(selected_label)
                if idx >= 0: combo.setCurrentIndex(idx)
            
            combo.currentIndexChanged.connect(lambda idx, row=i: self.on_local_font_changed(row, idx))
            self.font_table.setCellWidget(i, 1, combo)
            
            preview_label = QLabel("")
            preview_label.setAlignment(Qt.AlignCenter)
            self.font_table.setCellWidget(i, 2, preview_label)
        
        self.font_table.resizeColumnsToContents()

    def refresh_local_fonts(self):
        QFontDatabase.removeAllApplicationFonts()
        self.load_local_fonts()
        self.populate_font_table()
        self.update_all_preview_labels()

    def on_local_font_changed(self, row, index):
        combo = self.font_table.cellWidget(row, 1)
        data = combo.itemData(combo.currentIndex())
        
        pdf_font = list(self.font_mapping.keys())[row]
        if data:
            font_path = data["path"]
            font_filename = os.path.basename(font_path)
            self.font_mapping[pdf_font] = font_filename
        else:
            self.font_mapping[pdf_font] = ""
            
        self.save_font_mapping()
        self.update_preview_font(row)

    def on_preview_text_changed(self, text):
        self.update_all_preview_labels()

    def update_all_preview_labels(self):
        text = self.preview_edit.text()
        count = self.font_table.rowCount()
        for row in range(count):
            preview_label = self.font_table.cellWidget(row, 2)
            combo = self.font_table.cellWidget(row, 1)
            display_text = text if text else combo.currentText()
            preview_label.setText(display_text)
            self.update_preview_font(row)

    def update_preview_font(self, row):
        combo = self.font_table.cellWidget(row, 1)
        preview_label = self.font_table.cellWidget(row, 2)
        data = combo.itemData(combo.currentIndex())
        
        if data:
            family = data["family"]
            style = data["style"]
            
            # ✅ INSTANCE CRÉÉE ICI AUSSI
            font_db = QFontDatabase()
            # ✅ APPEL SUR L'INSTANCE
            font = font_db.font(family, style, 14)
            
            if font.family() != family:
                font = QFont(family, 14)
                if "Bold" in style: font.setBold(True)
                if "Italic" in style: font.setItalic(True)
            
            preview_label.setFont(font)
        else:
            preview_label.setFont(QFont("Arial", 14))
