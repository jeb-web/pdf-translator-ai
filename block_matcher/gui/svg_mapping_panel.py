# gui/svg_mapping_panel.py
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox, QFileDialog, QInputDialog,
    QLabel, QAbstractItemView
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QSize
from ..core.svg_manager import SvgManager

class SvgMappingPanel(QWidget):
    """
    Panneau de gestion des mappings SVG/Images.
    """
    def __init__(self, session_root, basename, parent=None):
        super().__init__(parent)
        self.manager = SvgManager(session_root, basename)
        self.initUI()
        self.refresh_table()

    def initUI(self):
        layout = QVBoxLayout(self)

        # -- Titre et Info --
        info_label = QLabel(
            f"Gestion des images pour le projet : <b>{self.manager.basename}</b><br>"
            f"Fichier : {self.manager.mapping_file.name}"
        )
        layout.addWidget(info_label)

        # -- Tableau --
        self.table = QTableWidget()
        
        # Définition des colonnes : Aperçu, Alias, Fichier, Réf. Texte, Ratio L/H, Ajust. V
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Aperçu", "Alias (ID)", "Fichier", "Ref. Texte", "Ratio L/H", "Ajust. V"
        ])
        
        # Ajustement des colonnes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # Aperçu
        header.setSectionResizeMode(1, QHeaderView.Stretch)          # Alias
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Fichier
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Taille
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Ratio
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents) # Ajust. V
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(32, 32))
        
        # Connexion pour éditer les cellules directement
        self.table.cellChanged.connect(self.on_cell_changed)
        
        layout.addWidget(self.table)

        # -- Boutons --
        btn_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("➕ Ajouter Image...")
        self.add_btn.clicked.connect(self.add_image_dialog)
        
        self.del_btn = QPushButton("🗑️ Supprimer")
        self.del_btn.clicked.connect(self.delete_selected)
        
        self.rename_btn = QPushButton("✏️ Renommer Alias")
        self.rename_btn.clicked.connect(self.rename_alias_dialog)
        
        self.reload_btn = QPushButton("🔄 Recharger JSON")
        self.reload_btn.clicked.connect(self.reload_data)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.rename_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.reload_btn)
        
        layout.addLayout(btn_layout)

    def refresh_table(self):
        """Recharge les données dans le tableau."""
        self.table.blockSignals(True) # Éviter de déclencher cellChanged pendant le remplissage
        self.table.setRowCount(0)
        
        row = 0
        for alias, data in self.manager.mapping_data.items():
            self.table.insertRow(row)
            
            # 1. Aperçu (Icon)
            file_name = data.get('file', '')
            file_path = self.manager.svg_dir / file_name
            icon_item = QTableWidgetItem()
            if file_path.exists():
                icon_item.setIcon(QIcon(str(file_path)))
                icon_item.setToolTip(str(file_path))
            else:
                icon_item.setText("❌")
            icon_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # Read-only
            self.table.setItem(row, 0, icon_item)

            # 2. Alias
            alias_item = QTableWidgetItem(alias)
            alias_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # Read-only, renommage via bouton
            self.table.setItem(row, 1, alias_item)
            
            # 3. Fichier
            file_item = QTableWidgetItem(file_name)
            file_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # Read-only
            self.table.setItem(row, 2, file_item)

            # 4. Taille Ref (Editable)
            val_taille = str(data.get('taille_texte_reference', 10.5))
            self.table.setItem(row, 3, QTableWidgetItem(val_taille))

            # 5. Ratio (Editable)
            val_ratio = str(data.get('ratio_largeur_hauteur', 1.0))
            self.table.setItem(row, 4, QTableWidgetItem(val_ratio))

            # 6. Ajustement Vertical (Editable)
            val_v = str(data.get('ajustement_vertical', 0))
            self.table.setItem(row, 5, QTableWidgetItem(val_v))
            
            # Stocker l'alias dans l'item 0 pour référence facile si besoin
            self.table.item(row, 0).setData(Qt.UserRole, alias)
            
            row += 1
            
        self.table.blockSignals(False)

    def add_image_dialog(self):
        """Ouvre un dialogue pour choisir un fichier image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image", "", "Images (*.png *.svg *.jpg)"
        )
        if not file_path:
            return

        # Demander l'alias
        default_alias = os.path.splitext(os.path.basename(file_path))[0]
        # On ajoute un préfixe par défaut s'il n'y en a pas, pour faire propre
        suggestion = f"img_{default_alias}" if not default_alias.startswith("img_") else default_alias
        
        alias, ok = QInputDialog.getText(
            self, "Alias de l'image", "Entrez un identifiant unique (alias) :",
            text=suggestion
        )
        
        if ok and alias:
            if alias in self.manager.mapping_data:
                QMessageBox.warning(self, "Erreur", "Cet alias existe déjà.")
                return
            
            if self.manager.add_image(file_path, alias):
                self.refresh_table()
                QMessageBox.information(self, "Succès", f"Image ajoutée avec l'alias '{alias}'")
            else:
                QMessageBox.critical(self, "Erreur", "Impossible de copier l'image.\nVérifiez la console pour plus de détails.")



    def delete_selected(self):
        """Supprime la ligne sélectionnée."""
        row = self.table.currentRow()
        if row < 0:
            return
            
        alias = self.table.item(row, 1).text()
        reply = QMessageBox.question(
            self, "Confirmer", f"Supprimer l'entrée '{alias}' ?\n(Le fichier image ne sera pas effacé du disque)",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.manager.remove_entry(alias)
            self.refresh_table()

    def rename_alias_dialog(self):
        """Renomme l'alias sélectionné."""
        row = self.table.currentRow()
        if row < 0:
            return

        old_alias = self.table.item(row, 1).text()
        new_alias, ok = QInputDialog.getText(
            self, "Renommer", f"Nouvel alias pour '{old_alias}' :", text=old_alias
        )
        
        if ok and new_alias and new_alias != old_alias:
            if self.manager.rename_alias(old_alias, new_alias):
                self.refresh_table()
            else:
                QMessageBox.warning(self, "Erreur", "Alias invalide ou déjà existant.")

    def reload_data(self):
        """Recharge les données depuis le fichier JSON."""
        self.manager.load_mapping()
        self.refresh_table()

    def on_cell_changed(self, row, column):
        """Gère l'édition directe dans la table."""
        # Seules les colonnes 3 (Taille), 4 (Ratio), 5 (Ajust V) sont éditables
        if column not in [3, 4, 5]: 
            return
            
        alias = self.table.item(row, 1).text()
        new_value_str = self.table.item(row, column).text()
        
        try:
            # Conversion en float
            new_value = float(new_value_str)
                
            # Mapping colonne -> clé JSON
            key_map = {
                3: 'taille_texte_reference',
                4: 'ratio_largeur_hauteur',
                5: 'ajustement_vertical'
            }
            
            key = key_map.get(column)
            if key:
                self.manager.update_entry(alias, key, new_value)
                
        except ValueError:
            pass
