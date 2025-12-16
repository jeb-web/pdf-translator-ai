#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fenêtre principale de l'interface de validation
"""
import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter, QStatusBar,
    QMessageBox, QTableWidgetItem, QListWidgetItem, QAction, QMenuBar,
    QDialog, QVBoxLayout
)

from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from typing import Dict, Any

import fitz  # ✓ AJOUTER CETTE LIGNE (PyMuPDF)

# --- NOUVEAUX IMPORTS ---
from ..core.session_manager import save_session

# --- IMPORTS ORIGINAUX ---
from ..core.data_manager import DataManager
from ..core.state_manager import StateManager
from ..core.pdf_renderer import PDFRenderer
# La fonction originale 'save_validation_metadata' sera appelée par 'export_for_reconstruction'
from ..core.metadata_manager import save_validation_metadata
from ..widgets.block_rect import ResizableBlockRect
from ..widgets.isolated_rect import ClickableIsolatedRect
from .panels import PDFViewerPanel, ControlPanel
from .shortcuts import setup_shortcuts
from ..utils.preferences import PreferencesManager
from .font_mapping_panel import FontMappingPanel
from .svg_mapping_panel import SvgMappingPanel
from ..core.translator import AutoTranslator

# block_matcher/gui/main_window.py

import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, 
    QStatusBar, QAction, QMessageBox, QGraphicsScene, QGraphicsView
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence, QPainter
from PyQt5.QtWidgets import QInputDialog
# Import du nouveau module
from ..core.pdf_builder import PDFBuilder


import fitz  # ✓ IMPORT MANQUANT - PyMuPDF

import traceback
import logging

class BlockValidationInterface(QMainWindow):
    """Interface principale de validation des blocs"""
    
    def __init__(self, session_data: dict):
        super().__init__()

        self.session_data = session_data
        self.basename = self.session_data["basename"]
        self.pdf_path = self.session_data["pdf_path"]

        self.data_manager = DataManager(self.session_data["enriched_data"])
        self.state_manager = StateManager()
        self.state_manager.session_data = self.session_data
        self.pdf_renderer = PDFRenderer(self.pdf_path)

        initial_zoom = self.session_data.get("ui_state", {}).get("zoom_level", 1.0)
        self.pdf_renderer.set_zoom(initial_zoom)

        self.current_block = None
        self.selected_blocks = []
        self.current_span = None

        self.mineru_rects = []
        self.span_rects = []
        from PyQt5.QtWidgets import QGraphicsScene
        self.scene = QGraphicsScene()

        self.pdf_panel = None
        self.control_panel = None
        self.main_splitter = None

        self.save_action = None
        self.export_action = None

        self.prefs = PreferencesManager(self.basename)

        # Update des default_style selon règles métier
        for page_blocks in self.data_manager.enriched_data:
            for block in page_blocks:
                self.update_block_default_style(block)

        # Synchronisation forcée
        self.session_data['enriched_data'] = self.data_manager.enriched_data

        self.initUI()

        last_page = self.session_data.get("ui_state", {}).get("current_page", 0)
        self.load_page(last_page)


    
    def initUI(self):
        """Initialiser l'interface utilisateur"""
        self.setWindowTitle(f"Block Validator - {self.basename}")
        
        # --- MENU FICHIER ---
        menubar = self.menuBar()
        filemenu = menubar.addMenu("Fichier")
        
        # Action Enregistrer la Session
        self.save_action = QAction("Enregistrer la Session", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setStatusTip("Enregistrer l'état actuel de votre travail")
        self.save_action.triggered.connect(self.save_current_session)
        self.save_action.setEnabled(True)  # ✓ Toujours actif
        filemenu.addAction(self.save_action)
        
        filemenu.addSeparator()
        
        # Action Exporter pour Reconstruction
        self.export_action = QAction("Exporter pour Reconstruction...", self)
        self.export_action.setStatusTip("Génère les fichiers finaux pour la reconstruction PDF")
        self.export_action.triggered.connect(self.export_for_reconstruction)
        self.export_action.setEnabled(True)  # ✓ Toujours actif
        filemenu.addAction(self.export_action)
        
        filemenu.addSeparator()
        
        # Action Quitter
        quit_action = QAction("Quitter", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.setStatusTip("Quitter l'application")
        quit_action.triggered.connect(self.close)
        filemenu.addAction(quit_action)
        
        # Restaurer la fenêtre depuis les préférences
        is_maximized = self.prefs.get("window.maximized", False)
        if is_maximized:
            self.showMaximized()
        else:
            x = self.prefs.get("window.x", 50)
            y = self.prefs.get("window.y", 50)
            width = self.prefs.get("window.width", 1800)
            height = self.prefs.get("window.height", 1000)
            self.setGeometry(max(0, x), max(0, y), width, height)
        
        # Widget central et layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Splitter principal horizontal
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.control_panel = ControlPanel(self)
        self.pdf_panel = PDFViewerPanel(self)
        
        self.main_splitter.addWidget(self.control_panel)
        self.main_splitter.addWidget(self.pdf_panel)
                
        # Restaurer les tailles du splitter
        saved_sizes = self.prefs.get("splitters.main_horizontal", [400, 1400])
        self.main_splitter.setSizes(saved_sizes)
        
        main_layout.addWidget(self.main_splitter)
        
        # Barre de statut
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        # Configuration des raccourcis clavier
        setup_shortcuts(self)
        
        # Mise à jour du statut
        self.update_status()
        self.update_menu_state()  # ✓ NOUVELLE LIGNE - Mettre à jour l'état du menu
        
        # Dans la création du menu "Édition"
        editmenu = menubar.addMenu("Édition")
        
        # Bouton Fusionner
        self.merge_btn = QAction("Fusionner blocs", self)
        self.merge_btn.setShortcut("Ctrl+M")
        self.merge_btn.setStatusTip("Fusionner les blocs sélectionnés")
        self.merge_btn.triggered.connect(self.merge_selected_blocks)
        self.merge_btn.setEnabled(False)  # Désactivé par défaut
        editmenu.addAction(self.merge_btn)

        # Bouton Défusionner
        self.unmerge_btn = QAction("Défusionner blocs", self)
        self.unmerge_btn.setShortcut("Ctrl+U")
        self.unmerge_btn.setStatusTip("Défusionner les blocs sélectionnés")
        self.unmerge_btn.triggered.connect(self.unmerge_selected_blocks)
        self.unmerge_btn.setEnabled(False)  # Désactivé par défaut
        editmenu.addAction(self.unmerge_btn)
        
        tools_menu = menubar.addMenu("Outils")
        open_font_mapping_action = QAction("Mapping des polices...", self)
        open_font_mapping_action.setStatusTip("Ouvrir le panneau modale de mapping des polices")
        open_font_mapping_action.triggered.connect(self.show_font_mapping_dialog)
     
        open_svg_mapping_action = QAction("Gestion des images/SVG...", self)
        open_svg_mapping_action.setStatusTip("Gérer les images et leurs alias pour le projet")
        open_svg_mapping_action.triggered.connect(self.show_svg_mapping_dialog)
        tools_menu.addAction(open_svg_mapping_action)

        tools_menu.addAction(open_font_mapping_action)
        action_editor = QAction("Éditeur de Traduction", self)
        action_editor.triggered.connect(self.show_translation_editor)
        tools_menu.addAction(action_editor)

        tools_menu.addSeparator()
        action_build = QAction("Générer PDF Final...", self)
        action_build.setShortcut("Ctrl+B")
        action_build.triggered.connect(self.generate_final_pdf)
        tools_menu.addAction(action_build)

        action_translate = QAction("Traduction Automatique (IA)...", self)
        action_translate.setShortcut("Ctrl+T")
        action_translate.triggered.connect(self.show_auto_translate_dialog)
        tools_menu.addAction(action_translate)

    def update_menu_state(self):
        """Mettre à jour l'état du menu selon le contexte"""
        # Ces actions sont toujours activées tant qu'une session existe
        has_session = bool(self.session_data)
        has_page = has_session and len(self.data_manager.enriched_data) > 0
        
        if self.save_action:
            self.save_action.setEnabled(has_session)
        
        if self.export_action:
            self.export_action.setEnabled(has_page)
    
    def save_current_session(self):
        try:
            if self.session_data.get("enriched_data") is not self.data_manager.enriched_data:
                self.session_data["enriched_data"] = self.data_manager.enriched_data

            if hasattr(self.data_manager, 'global_styles') and hasattr(self.data_manager, 'block_additional_style_refs'):
                self.session_data['global_styles'] = {
                    'styles': self.data_manager.global_styles,
                    'block_style_refs': self.data_manager.block_additional_style_refs
                }

            if "ui_state" not in self.session_data:
                self.session_data["ui_state"] = {}

            self.session_data["ui_state"]["current_page"] = self.data_manager.current_page
            self.session_data["ui_state"]["zoom_level"] = self.pdf_renderer.zoom_level

            basename = self.session_data.get('basename', 'unknown')
            session_file = f"{basename}_session.json"

            save_session(self.session_data, session_file)

            if hasattr(self, 'statusbar') and self.statusbar is not None:
                self.statusbar.showMessage("Session enregistrée ✓", 3000)

        except Exception as e:
            QMessageBox.critical(self, "Erreur de Sauvegarde", f"Impossible d'enregistrer la session:\n{e}")


    
    def export_for_reconstruction(self):
        """
        Exporter les fichiers _formatage.json et _pour_traduction.json en utilisant
        la persistance des styles globaux dans la session.
        Inclut les overrides de traduction (corrections manuelles).
        """
        try:
            from ..core.extract import DualOutputGenerator

            # Récupérer les styles globaux existants (rétrocompatibilité)
            global_styles_data = self.session_data.get('global_styles', {
                'styles': {},
                'block_style_refs': {}
            })
            
            # --- AJOUT : Récupération des overrides ---
            overrides = self.session_data.get('translation_overrides', {})
            # ----------------------------------------

            # Créer une instance du générateur avec les styles existants ET les overrides
            generator = DualOutputGenerator(
                enriched_data=self.session_data['enriched_data'],
                page_dimensions=self.session_data.get('page_dimensions', {}),
                global_styles_data=global_styles_data,
                translation_overrides=overrides  # <--- PASSAGE DES CORRECTIONS ICI
            )

            # Générer le formatage AVANT la traduction (ordre important)
            formatting_data = generator._generate_formatting_format(self.session_data['enriched_data'])
            translation_data = generator._generate_translation_format(self.session_data['enriched_data'])

            # Mettre à jour la session avec les styles mis à jour du générateur
            self.session_data['global_styles'] = {
                'styles': generator.global_styles,
                'block_style_refs': generator.block_additional_style_refs
            }

            # Sauvegarder la session automatiquement
            self.state_manager.save_current_session()

            # Sauvegarder les fichiers JSON
            basename = self.session_data.get('basename', 'output')
            formatage_file = f"{basename}_formatage.json"
            traduction_file = f"{basename}_pour_traduction.json"

            with open(formatage_file, 'w', encoding='utf-8') as f:
                json.dump(formatting_data, f, indent=2, ensure_ascii=False)

            with open(traduction_file, 'w', encoding='utf-8') as f:
                json.dump(translation_data, f, indent=2, ensure_ascii=False)

            # Info utilisateur
            msg = "Export terminé avec succès."
            if overrides:
                msg += f"\n({len(overrides)} corrections manuelles appliquées)"
            
            self.statusbar.showMessage(msg, 4000)
            QMessageBox.information(self, "Export réussi", f"{msg}\n\nFichiers générés :\n- {formatage_file}\n- {traduction_file}")

        except Exception as e:
            QMessageBox.critical(self, "Erreur export", f"Erreur lors de l'export:\n{e}")



    
    def load_page(self, pagenum: int):
        """Charger et afficher une page"""
        if pagenum < 0 or pagenum >= len(self.data_manager.enriched_data):
            return
        
        self.data_manager.current_page = pagenum
        self.current_block = None
        self.current_span = None
        
        # Mettre à jour la navigation
        self.control_panel.update_navigation(pagenum, len(self.data_manager.enriched_data))
        
        # Dessiner la page
        self.draw_page()
        
        # Remplir la liste des blocs
        self.populate_blocks_list()
        
        # Mettre à jour les statistiques
        self.update_page_stats()
        
        # Effacer la sélection
        self.clear_block_selection()
        
        # Mettre à jour le statut
        self.update_status()
        self.update_menu_state()
        
        self.populate_available_spans()  # ← Ajouter cet appel
    
    def draw_page(self):
        """Dessiner la page PDF avec overlays et ajuster l'ordre d'affichage (Z-Order)"""
        
        # Arrêt des clignotements éventuels
        self.stop_all_blinks()
        
        page_blocks = self.data_manager.get_page_blocks()
        show_all = self.pdf_panel.show_all_spans_cb.isChecked()
        
        # Rendu de base (crée les items dans la scène)
        self.mineru_rects, self.span_rects = self.pdf_renderer.render_page_with_overlays(
            self.scene,
            self.data_manager.current_page,
            page_blocks,
            self,
            show_all
        )
        
        # --- AJUSTEMENT DU Z-ORDER (Pour faciliter la saisie des blocs) ---
        # Ordre souhaité du fond vers le premier plan :
        # 1. Image PDF (géré par renderer, souvent Z=0)
        # 2. Spans (texte fin) -> Z=1
        # 3. Blocs (conteneurs) -> Z=10 (pour être attrapables)
        # 4. Sélection / Highlight -> Z=100 (géré dynamiquement lors du clic)

        # 1. Mettre les Spans en arrière-plan (Z=1)
        if self.span_rects:
            for span_id, rect_item in self.span_rects.items():
                try:
                    if rect_item.scene():
                        rect_item.setZValue(1)
                except RuntimeError:
                    pass

        # 2. Mettre les Blocs au premier plan (Z=10)
        if self.mineru_rects:
            for block_id, rect_item in self.mineru_rects.items():
                try:
                    if rect_item.scene():
                        # On met un ZValue plus élevé pour qu'ils captent les clics en priorité
                        rect_item.setZValue(10)
                        
                        # Si c'est le bloc courant, on le met encore plus haut
                        if self.current_block and self.current_block.get('id') == block_id:
                            rect_item.setZValue(20)
                except RuntimeError:
                    pass

        # Appliquer les styles de fusion visuels
        self.apply_merge_styling_to_list(self.data_manager.get_page_blocks())
        self.render_merge_outlines(self.data_manager.get_page_blocks())
        
        # Repeupler la liste des spans disponibles pour l'UI
        self.populate_available_spans()



    def apply_merge_styling_to_list(self, pageblocks):
        """Marquer les blocs fusionnés dans la liste avec numéro de merge"""
        from PyQt5.QtCore import Qt
        
        try:
            # Parcourir TOUS les items de la liste
            for i in range(self.control_panel.blocks_list.count()):
                item = self.control_panel.blocks_list.item(i)
                if not item:
                    continue
                    
                block = item.data(Qt.UserRole)
                if not block:
                    continue
                
                # Récupérer le texte actuel
                text = item.text()
                
                # Retirer ancien préfixe si présent
                if text.startswith("🔗"):
                    # Trouver la fin du préfixe (format: 🔗 M12345#0 NomBloc)
                    parts = text.split(" ", 2)
                    if len(parts) >= 3:
                        text = parts[2]  # Garder seulement le nom du bloc
                    else:
                        text = parts[-1]
                
                # SI le bloc est fusionné
                if block.get("merge_group_id"):
                    merge_order = block.get("merge_order", 0)
                    merge_id = block.get("merge_group_id", "")
                    # Extraire le numéro du merge_id (ex: MERGE_12345 → 12345)
                    merge_num = merge_id.split("_")[-1] if "_" in merge_id else merge_id
                    item.setText(f"🔗 M{merge_num}#{merge_order} {text}")
                else:
                    # Bloc normal : s'assurer qu'il n'y a pas de préfixe
                    item.setText(text)
                        
        except Exception as e:
            print(f"Erreur apply_merge_styling: {e}")





    def render_merge_outlines(self, pageblocks):
        """Dessiner les contours magenta des blocs fusionnés"""
        from PyQt5.QtGui import QPen, QColor
        from PyQt5.QtCore import Qt
        
        try:
            for block in pageblocks:
                if "merge_group_id" in block:
                    block_id = block.get("id")
                    if block_id in self.mineru_rects:
                        rect_item = self.mineru_rects[block_id]
                        merge_pen = QPen(QColor(255, 0, 255), 3, Qt.SolidLine)
                        rect_item.setPen(merge_pen)
        except Exception as e:
            print(f"Erreur render_merge_outlines: {e}")



    def populate_blocks_list(self):
        """Remplir la liste des blocs"""
        page_blocks = self.data_manager.get_page_blocks()
        self.control_panel.populate_blocks_list(page_blocks)
        self.apply_merge_styling_to_list(page_blocks)
    
    def update_page_stats(self):
        """Mettre à jour les statistiques de la page"""
        page_blocks = self.data_manager.get_page_blocks()
        self.control_panel.update_stats(page_blocks)
    
    def select_mineru_block(self, block: Dict[str, Any]):
        """Sélectionner un bloc MinerU"""
        self.current_block = block
        self.current_span = None
        self.populate_spans_table()
        self.draw_page()
        self.update_status()
        self.update_menu_state()
    
    def select_isolated_block(self, block):
        """Sélectionner un isolatedspan"""
        self.current_block = block
        self.current_span = None
        self.draw_page()
        self.highlight_current_block() 
        self.update_status()
        self.update_menu_state()
 
    def on_block_list_click(self, item, modifiers=None):
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt

        block_clicked = item.data(Qt.UserRole)
        if not block_clicked:
            return

        if modifiers is None:
            modifiers = QApplication.keyboardModifiers()
        
        is_ctrl_click = (modifiers & Qt.ControlModifier)

        if len(self.selected_blocks) == 1 and self.selected_blocks[0]['id'] == block_clicked['id'] and not is_ctrl_click:
            item.setSelected(True)
            return

        if is_ctrl_click:
            if any(b['id'] == block_clicked['id'] for b in self.selected_blocks):
                self.selected_blocks = [b for b in self.selected_blocks if b['id'] != block_clicked['id']]
                item.setSelected(False)
            else:
                self.selected_blocks.append(block_clicked)
                item.setSelected(True)
        else:
            self.control_panel.blocks_list.clearSelection()
            item.setSelected(True)
            self.selected_blocks = [block_clicked]

        self.current_block = block_clicked

        if not is_ctrl_click:
            self.update_block_details()
            self.highlight_current_block()
        
        # ✅ NOUVEAU : Faire clignoter tous les blocs sélectionnés
        rects_to_blink = []
        for block in self.selected_blocks:
            block_id = block.get('id')
            if block_id in self.mineru_rects:
                rects_to_blink.append(self.mineru_rects[block_id])
        self.blink_items(rects_to_blink)
        
        self.update_merge_buttons_state()
        self.update_status()


    def update_merge_buttons_state(self):
        """Mettre à jour l'état des boutons Fusionner/Défusionner"""
        
        # ✅ CORRECTION : Vérifier AUSSI la sélection dans available_spans_list
        selected_span_items = self.control_panel.available_spans_list.selectedItems()
        
        # Si des isolated spans sont sélectionnés dans available_spans_list
        if selected_span_items and len(selected_span_items) >= 1:
            # Cas : Isolated spans sélectionnés dans la liste des disponibles
            self.control_panel.create_block_btn.setText("🔗 Créer Bloc depuis ISO")
            self.control_panel.create_block_btn.setStyleSheet("background: #2196F3; color: white; font-weight: bold;")
            self.control_panel.create_block_btn.setEnabled(True)  # ✅ Toujours activé si au moins 1 span
            try:
                self.control_panel.create_block_btn.clicked.disconnect()
            except:
                pass
            self.control_panel.create_block_btn.clicked.connect(self.create_block_from_selection)
            
            # Désactiver Fusionner/Défusionner
            self.merge_btn.setEnabled(False)
            self.unmerge_btn.setEnabled(False)
            return
        
        # Sinon, gérer la sélection dans blocks_list
        if len(self.selected_blocks) == 1 and self.selected_blocks[0].get('match_source') == 'manual':
            # Cas : Un bloc custom sélectionné → bouton Supprimer
            self.control_panel.create_block_btn.setText("🗑️ Supprimer Bloc Custom")
            self.control_panel.create_block_btn.setStyleSheet("background: #f44336; color: white; font-weight: bold;")
            self.control_panel.create_block_btn.setEnabled(True)
            try:
                self.control_panel.create_block_btn.clicked.disconnect()
            except:
                pass
            self.control_panel.create_block_btn.clicked.connect(self.delete_custom_block)
        else:
            # Cas : Autres sélections → bouton Créer (désactivé si < 2 isolated)
            self.control_panel.create_block_btn.setText("🔗 Créer Bloc depuis ISO")
            self.control_panel.create_block_btn.setStyleSheet("background: #2196F3; color: white; font-weight: bold;")
            isolated_selected = [b for b in self.selected_blocks if b.get('block_type') == 'isolated_span']
            self.control_panel.create_block_btn.setEnabled(len(isolated_selected) >= 1)  # ✅ >= 1 au lieu de >= 2
            try:
                self.control_panel.create_block_btn.clicked.disconnect()
            except:
                pass
            self.control_panel.create_block_btn.clicked.connect(self.create_block_from_selection)
        
        # Fusionner : actif si 2+ blocs sélectionnés ET aucun n'est déjà fusionné
        has_unmerged = any("merge_group_id" not in b for b in self.selected_blocks)
        self.merge_btn.setEnabled(len(self.selected_blocks) >= 2 and has_unmerged)
        
        # Défusionner : actif si au moins 1 bloc avec merge_group_id
        has_merged = any("merge_group_id" in b for b in self.selected_blocks)
        self.unmerge_btn.setEnabled(has_merged)


    def delete_custom_block(self):
        from PyQt5.QtWidgets import QMessageBox
        
        if len(self.selected_blocks) != 1:
            return
        
        block = self.selected_blocks[0]
        if block.get('match_source') != 'manual':
            return
        
        reply = QMessageBox.question(self, 'Confirmer', 
                                     f"Supprimer le bloc custom '{block['id']}' ?", 
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        self.save_state()
        page_blocks = self.data_manager.get_page_blocks()
        
        # ✅ CORRECTION : Trouver le bloc par ID au lieu d'utiliser remove()
        block_id = block.get('id')
        block_to_remove = None
        
        for b in page_blocks:
            if b.get('id') == block_id:
                block_to_remove = b
                break
        
        if not block_to_remove:
            QMessageBox.warning(self, "Erreur", f"Bloc '{block_id}' introuvable")
            return
        
        # Restaurer les isolated_span
        for span in block_to_remove.get('matching_spans', []):
            span_id = span.get('id')
            
            # Trouver l'isolated_span d'origine
            for page_block in page_blocks:
                if page_block.get('block_type') == 'isolated_span':
                    for iso_span in page_block.get('matching_spans', []):
                        if iso_span.get('id') == span_id:
                            page_block['is_consumed'] = False
                            page_block['include_in_output'] = True
                            iso_span['matched_to_block'] = page_block.get('id')
                            break
        
        # ✅ Supprimer le bloc trouvé
        page_blocks.remove(block_to_remove)
        
        self.selected_blocks = []
        self.current_block = None
        self.refresh_display()
        
        QMessageBox.information(self, "Bloc supprimé", f"Bloc '{block_id}' supprimé avec succès.")


    def unmerge_selected_blocks(self):
        """Défusionner les blocs sélectionnés"""
        print(f"\n=== UNMERGE CALLED ===")
        print(f"selected_blocks count: {len(self.selected_blocks)}")
        for b in self.selected_blocks:
            print(f"  - {b.get('id')}: merge_group_id={b.get('merge_group_id')}")
        
        try:
            block_ids = [b["id"] for b in self.selected_blocks]
            print(f"Calling unmerge_blocks with IDs: {block_ids}")
            
            self.data_manager.unmerge_blocks(block_ids)
            
            # ✅ Recharger depuis enriched_data
            self.selected_blocks = []
            for page_blocks in self.data_manager.enriched_data:
                if isinstance(page_blocks, list):
                    for block in page_blocks:
                        if isinstance(block, dict) and block.get("id") in block_ids:
                            self.selected_blocks.append(block)
                            print(f"Reloaded block {block.get('id')}: merge_group_id={block.get('merge_group_id')}")
            
            self.statusbar.showMessage(
                f"✅ {len(block_ids)} bloc(s) défusionnés", 
                3000
            )
            
            self.populate_blocks_list()
            self.update_merge_buttons_state()
            
            # ✅ CRUCIAL : Rafraîchir d'abord pour recréer les rectangles
            self.draw_page()
            
            # ✅ CORRECTION : Récupérer les NOUVEAUX rectangles APRÈS draw_page()
            rects_to_blink = []
            for block in self.selected_blocks:
                block_id = block.get('id')
                if block_id in self.mineru_rects:
                    rects_to_blink.append(self.mineru_rects[block_id])
            
            # Maintenant on peut clignoter en toute sécurité
            if rects_to_blink:
                self.blink_items(rects_to_blink)
            
            self.update_merge_buttons_state()
            
            print(f"=== UNMERGE COMPLETE ===\n")
        
        except Exception as e:
            import traceback
            print(f"UNMERGE ERROR: {e}")
            print(traceback.format_exc())
            QMessageBox.critical(self, "Erreur", f"Défusion échouée: {str(e)}")


    def merge_selected_blocks(self):
        """Fusionner les blocs sélectionnés"""
        from PyQt5.QtWidgets import QMessageBox
        
        if len(self.selected_blocks) < 2:
            QMessageBox.warning(self, "Erreur", "Sélectionnez au moins 2 blocs")
            return
        
        if any("merge_group_id" in b for b in self.selected_blocks):
            QMessageBox.warning(self, "Erreur", "Un bloc sélectionné est déjà fusionné")
            return
        
        try:
            block_ids = [b["id"] for b in self.selected_blocks]
            merge_group_id = self.data_manager.merge_blocks(block_ids)
            
            # ✅ CRUCIAL - Recharger les blocs depuis enriched_data
            self.selected_blocks = []
            for page_blocks in self.data_manager.enriched_data:
                if isinstance(page_blocks, list):
                    for block in page_blocks:
                        if isinstance(block, dict) and block.get("id") in block_ids:
                            self.selected_blocks.append(block)
            
            self.statusbar.showMessage(
                f"✅ {len(block_ids)} blocs fusionnés (ID: {merge_group_id})", 
                3000
            )
            
            self.populate_blocks_list()
            self.update_merge_buttons_state()
            
            # ✅ CRUCIAL : Rafraîchir d'abord
            self.draw_page()
            
            # ✅ CORRECTION : Récupérer les NOUVEAUX rectangles APRÈS draw_page()
            rects_to_blink = []
            for block in self.selected_blocks:
                block_id = block.get('id')
                if block_id in self.mineru_rects:
                    rects_to_blink.append(self.mineru_rects[block_id])
            
            # Clignoter en toute sécurité
            if rects_to_blink:
                self.blink_items(rects_to_blink)
            
            self.update_merge_buttons_state()
            
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Erreur", f"Fusion échouée: {str(e)}")




    
    def clear_block_selection(self):
        """Effacer la sélection actuelle"""
        self.current_block = None
        self.current_span = None
        self.draw_page()
        self.update_status()
        self.update_menu_state()
    
    def highlight_current_block(self):
        """Activer le highlight avec clignotement du bloc sélectionné et gestion Z-Order"""
        # Désactiver tous les highlights et remettre Z-Order standard
        for blockid, rectitem in self.mineru_rects.items():
            from ..widgets.isolated_rect import ClickableIsolatedRect
            from ..widgets.block_rect import ResizableBlockRect
            
            try:
                # Reset Z-Value standard pour les blocs
                rectitem.setZValue(10) 
                
                if isinstance(rectitem, (ClickableIsolatedRect, ResizableBlockRect)):
                    rectitem.update_style(highlighted=False)
                else:
                    rectitem.setSelected(False)
            except RuntimeError:
                pass
        
        # Activer le highlight du bloc courant et le monter au premier plan
        if self.current_block:
            block_id = self.current_block.get('id')
            if block_id in self.mineru_rects:
                rectitem = self.mineru_rects[block_id]
                try:
                    # Mettre le bloc sélectionné AU-DESSUS de tout le reste
                    rectitem.setZValue(100)
                    
                    if isinstance(rectitem, ClickableIsolatedRect):
                        rectitem.update_style(highlighted=True)
                except RuntimeError:
                    pass




    # ========================================================================
    # DÉTAILS DU BLOC
    # ========================================================================
    
    def update_block_details(self):
        """Mettre à jour les détails du bloc sélectionné (ou sélection multiple)"""
        
        # Vérifier si plusieurs isolated_spans sont sélectionnés
        selected_items = self.control_panel.blocks_list.selectedItems()
        selected_isolated = [
            item.data(Qt.UserRole) for item in selected_items 
            if item.data(Qt.UserRole).get('block_type') == 'isolated_span'
        ]
        
        # CAS 1 : Plusieurs isolated_spans sélectionnés
        if len(selected_isolated) > 1:
            included_count = sum(1 for b in selected_isolated if b.get('include_in_output', True))
            excluded_count = len(selected_isolated) - included_count
            
            info = f"<b>Type:</b> Sélection multiple<br>"
            info += f"<b>Isolated spans:</b> {len(selected_isolated)}<br>"
            info += f"<b>Inclus:</b> {included_count}<br>"
            info += f"<b>Exclus:</b> {excluded_count}"
            
            self.control_panel.block_info_label.setText(info)
            self.control_panel.include_isolated_btn.setEnabled(True)
            
            # Déterminer l'action à proposer
            if included_count > excluded_count:
                self.control_panel.include_isolated_btn.setText(f"⬜ Exclure les {len(selected_isolated)}")
            else:
                self.control_panel.include_isolated_btn.setText(f"✅ Inclure les {len(selected_isolated)}")
            
            self.control_panel.preserve_empty_btn.setEnabled(False)
            self.control_panel.spans_table.setRowCount(0)
            self.populate_available_spans()
            return
        
        # CAS 2 : Aucun bloc sélectionné
        if not self.current_block:
            self.control_panel.block_info_label.setText("Aucun bloc")
            self.control_panel.spans_table.setRowCount(0)
            self.populate_available_spans()
            self.control_panel.preserve_empty_btn.setEnabled(False)
            self.control_panel.include_isolated_btn.setEnabled(False)
            return
        
        # CAS 3 : Rafraîchir référence du bloc courant
        for block in self.data_manager.get_page_blocks():
            if block['id'] == self.current_block['id']:
                self.current_block = block
                break
        
        block = self.current_block
        
        # CAS 4 : Un seul isolated_span sélectionné
        if block.get('block_type') == 'isolated_span':
            span = (block.get('matching_spans') or [{}])[0]
            include = block.get('include_in_output', True)
            
            info = f"<b>Type:</b> Isolated Span<br>"
            info += f"<b>ID:</b> {block['id']}<br>"
            info += f"<b>Texte:</b> {span.get('text', '')[:100]}<br>"
            info += f"<b>Font:</b> {span.get('font_name')} {span.get('font_size')}<br>"
            info += f"<b>Statut:</b> {'✅ Inclus' if include else '⬜ Exclu'}"
            
            self.control_panel.block_info_label.setText(info)
            self.control_panel.include_isolated_btn.setEnabled(True)
            self.control_panel.include_isolated_btn.setText("⬜ Exclure" if include else "✅ Inclure")
            self.control_panel.preserve_empty_btn.setEnabled(False)
            self.control_panel.spans_table.setRowCount(0)
            self.populate_available_spans()
            return
        
        # CAS 5 : Bloc MinerU normal
        spans = len(block.get('matching_spans', []))
        info = f"<b>ID:</b> {block['id']}<br>"
        info += f"<b>Type:</b> {block.get('block_type')}<br>"
        info += f"<b>Spans:</b> {spans}<br>"
        info += f"<b>Source:</b> {block.get('match_source', 'auto')}"
        
        self.control_panel.block_info_label.setText(info)
        self.control_panel.preserve_empty_btn.setEnabled(spans == 0)
        self.control_panel.include_isolated_btn.setEnabled(False)
        
        if spans == 0:
            self.control_panel.preserve_empty_btn.setText(
                "🔓 Déconserver" if block.get('preserve_empty') else "🔒 Conserver"
            )
        
        self.populate_spans_table()
        self.populate_available_spans()
    
    def populate_spans_table(self):
        """Remplir la table des spans associés"""
        self.control_panel.spans_table.setRowCount(0)
        if not self.current_block:
            return
        
        spans = self.current_block.get('matching_spans', [])
        self.control_panel.spans_table.setRowCount(len(spans))
        
        for idx, span in enumerate(spans):
            # Colonne 0 : Texte complet (sans troncature)
            text_item = QTableWidgetItem(span['text'])
            text_item.setToolTip(span['text'])  # Tooltip avec le texte complet
            self.control_panel.spans_table.setItem(idx, 0, text_item)
            
            # Colonne 1 : Font (nom + taille)
            font_name = span.get('font_name', 'N/A')
            font_size = span.get('font_size', 'N/A')
            font_info = f"{font_name} {font_size}"
            font_item = QTableWidgetItem(font_info)
            self.control_panel.spans_table.setItem(idx, 1, font_item)
    
    def populate_available_spans(self):
        """
        Remplir la liste des spans disponibles (isolated_spans).
        CORRIGÉ : N'exclut les spans que si le bloc sélectionné est un bloc MinerU normal.
        """
        self.control_panel.available_spans_list.clear()
        
        available = []
        exclude_ids = set() # Par défaut, on n'exclut rien
        
        # Si un bloc MinerU (et non un isolated_span) est sélectionné,
        # on prépare les ID de ses spans pour ne pas les proposer à l'ajout.
        if self.current_block and self.current_block.get('block_type') != 'isolated_span':
            exclude_ids = set(s['id'] for s in self.current_block.get('matching_spans', []))
        
        # Récupérer tous les spans de tous les blocs 'isolated_span'
        for block in self.data_manager.get_page_blocks():
            if block.get('block_type') == 'isolated_span':
                # On ne prend que le premier span, car un isolated_span n'en a qu'un
                span_list = block.get('matching_spans', [])
                if span_list:
                    span = span_list[0]
                    if span.get('id') not in exclude_ids:
                        # On stocke le bloc parent avec le span pour retrouver son statut
                        available.append({'span': span, 'parent_block': block})
        
        # Trier par position (haut en bas, gauche à droite)
        available.sort(key=lambda item: (item['span']['bbox_pixels'][1], item['span']['bbox_pixels'][0]))
        
        # Afficher avec indicateur d'inclusion
        for item_data in available:
            span = item_data['span']
            parent_block = item_data['parent_block']
            is_included = parent_block.get('include_in_output', True)
            
            icon = "✅" if is_included else "⬜"
            text = f"{icon} S{span.get('id', '?')}: {span.get('text', '')[:40]}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, span) # On garde le span comme donnée
            
            if is_included:
                item.setBackground(QColor(240, 255, 240))
            else:
                item.setBackground(QColor(240, 240, 240))
            
            self.control_panel.available_spans_list.addItem(item)


    
    # ========================================================================
    # GESTION DES SPANS
    # ========================================================================
    
    def on_span_table_selection(self):
        """Gérer la sélection dans la table des spans"""
        has_sel = len(self.control_panel.spans_table.selectedIndexes()) > 0
        self.control_panel.move_up_btn.setEnabled(has_sel)
        self.control_panel.move_down_btn.setEnabled(has_sel)
        self.control_panel.remove_span_btn.setEnabled(has_sel)
    
    def on_span_clicked(self, span_data: Dict[str, Any]):
        """
        Gérer le clic sur un span dans la vue PDF
        
        Args:
            span_data: Données du span cliqué
        """
        if not self.current_block:
            return
        spans = self.current_block.get('matching_spans', [])
        if span_data in spans:
            self.control_panel.spans_table.selectRow(spans.index(span_data))
            

    def on_available_span_clicked(self, span_data: Dict[str, Any]):
        """
        Gère le clic sur un isolated span dans la liste des disponibles.
        ✅ Gère aussi la multi-sélection avec clignotement.
        """
        from PyQt5.QtGui import QPen, QColor
        
        # ✅ Récupérer TOUS les spans sélectionnés
        selected_items = self.control_panel.available_spans_list.selectedItems()
        selected_span_ids = [item.data(Qt.UserRole).get('id') for item in selected_items]
        
        print(f"[DEBUG] Spans sélectionnés: {len(selected_span_ids)}")
        
        # ✅ DEBUG : Vérifier le statut des blocs parents
        page_blocks = self.data_manager.get_page_blocks()
        for span_id in selected_span_ids:
            for block in page_blocks:
                if block.get('block_type') == 'isolated_span':
                    spans_in_block = block.get('matching_spans', [])
                    if spans_in_block and spans_in_block[0].get('id') == span_id:
                        print(f"[DEBUG] Span {span_id}:")
                        print(f"  - Bloc ID: {block.get('id')}")
                        print(f"  - include_in_output: {block.get('include_in_output', True)}")
                        print(f"  - is_consumed: {block.get('is_consumed', False)}")
                        break
        
        if len(selected_span_ids) == 1:
            # Un seul span : comportement actuel
            self.selected_isolated_span = span_data
            
            if hasattr(self.control_panel, 'include_isolated_btn'):
                parent_block = None
                for block in self.data_manager.get_page_blocks():
                    if block.get('block_type') == 'isolated_span':
                        spans_in_block = block.get('matching_spans', [])
                        if spans_in_block and spans_in_block[0].get('id') == span_data.get('id'):
                            parent_block = block
                            break
                
                if parent_block:
                    include = parent_block.get('include_in_output', True)
                    self.control_panel.include_isolated_btn.setEnabled(True)
                    self.control_panel.include_isolated_btn.setText("Exclure" if include else "Inclure")
        else:
            # Plusieurs spans : activer le bouton pour action groupée
            if hasattr(self.control_panel, 'include_isolated_btn'):
                self.control_panel.include_isolated_btn.setEnabled(True)
                self.control_panel.include_isolated_btn.setText(f"Inclure/Exclure ({len(selected_span_ids)})")
        
        # ✅ CRUCIAL : Mettre à jour selected_blocks pour que update_merge_buttons_state fonctionne
        page_blocks = self.data_manager.get_page_blocks()
        self.selected_blocks = []
        
        for span_id in selected_span_ids:
            for block in page_blocks:
                if block.get('block_type') == 'isolated_span':
                    spans_in_block = block.get('matching_spans', [])
                    if spans_in_block and spans_in_block[0].get('id') == span_id:
                        self.selected_blocks.append(block)
                        break
        
        print(f"[DEBUG] selected_blocks mis à jour: {len(self.selected_blocks)}")
        
        # ✅ Mettre à jour l'état du bouton Créer/Supprimer
        self.update_merge_buttons_state()
        
        # ✅ Faire clignoter TOUS les spans sélectionnés
        rects_to_blink = []
        print(f"[DEBUG] Total span_rects disponibles: {len(self.span_rects)}")
        
        for span_id in selected_span_ids:
            if span_id in self.span_rects:
                print(f"[DEBUG] ✓ Rect trouvé pour span {span_id}")
                rects_to_blink.append(self.span_rects[span_id])
            else:
                print(f"[DEBUG] ✗ Rect NON trouvé pour span {span_id}")
        
        print(f"[DEBUG] Rectangles à clignoter: {len(rects_to_blink)}")
        
        if rects_to_blink:
            self.blink_items(rects_to_blink)
        else:
            print(f"[DEBUG] ⚠ Aucun rectangle trouvé pour clignoter")



        
    def move_span_up(self):
        """Déplacer le span sélectionné vers le haut"""
        row = self.control_panel.spans_table.currentRow()
        if row <= 0 or not self.current_block:
            return
        
        self.save_state()
        spans = self.current_block['matching_spans']
        spans[row], spans[row-1] = spans[row-1], spans[row]
        self.current_block['match_source'] = 'manual'
        
        self.populate_spans_table()
        self.control_panel.spans_table.selectRow(row - 1)
        self.refresh_display()
    
    def move_span_down(self):
        """Déplacer le span sélectionné vers le bas"""
        if not self.current_block:
            return
        
        row = self.control_panel.spans_table.currentRow()
        spans = self.current_block['matching_spans']
        if row < 0 or row >= len(spans) - 1:
            return
        
        self.save_state()
        spans[row], spans[row+1] = spans[row+1], spans[row]
        self.current_block['match_source'] = 'manual'
        
        self.populate_spans_table()
        self.control_panel.spans_table.selectRow(row + 1)
        self.refresh_display()
    
    def remove_span(self):
        """
        Retirer le(s) span(s) sélectionné(s) du bloc et RECRÉER les blocs isolated_span correspondants.
        """
        if not self.current_block:
            return

        selected_rows = set(index.row() for index in self.control_panel.spans_table.selectedIndexes())
        if not selected_rows:
            return

        self.save_state()
        spans_to_remove = []
        
        # 1. Identifier les spans à retirer
        for row in sorted(selected_rows, reverse=True):
            if row < len(self.current_block['matching_spans']):
                spans_to_remove.append(self.current_block['matching_spans'][row])

        if not spans_to_remove:
            return

        page_blocks = self.data_manager.get_page_blocks()
        current_page_idx = self.data_manager.current_page
        
        # Récupérer les dimensions de la page pour recalculer les positions absolues
        page_dims = [595, 842] # Valeur par défaut
        if self.session_data.get('page_dimensions') and current_page_idx in self.session_data['page_dimensions']:
             page_dims = self.session_data['page_dimensions'][current_page_idx]

        for removed_span in spans_to_remove:
            removed_id = removed_span['id']
            
            # A. Retirer du bloc courant
            self.current_block['matching_spans'] = [
                s for s in self.current_block['matching_spans']
                if s['id'] != removed_id
            ]
            
            # B. Nettoyer le span
            removed_span['matched_to_block'] = None
            
            # C. Recréer le bloc isolated_span
            # On vérifie d'abord s'il n'existe pas déjà (par sécurité)
            exists = False
            for block in page_blocks:
                if block.get('block_type') == 'isolated_span':
                    for s in block.get('matching_spans', []):
                        if s['id'] == removed_id:
                            exists = True
                            block['is_consumed'] = False
                            block['include_in_output'] = True
                            break
            
            if not exists:
                # Calcul de la géométrie
                bbox_norm = removed_span.get('bbox_normalized', [0,0,0,0])
                pos_x = bbox_norm[0] * page_dims[0]
                pos_y = bbox_norm[1] * page_dims[1]
                width = (bbox_norm[2] - bbox_norm[0]) * page_dims[0]
                
                # Reconstruction de l'objet bloc
                new_iso_block = {
                    'id': f"page{current_page_idx+1}_isolated_pymupdf_{removed_id}",
                    'block_type': 'isolated_span',
                    'content': removed_span['text'],
                    'styled_content': removed_span['text'],
                    'position_xy': [pos_x, pos_y],
                    'max_allowable_width': width,
                    'default_style': {
                        "police": removed_span.get('font_name'),
                        "taille": removed_span.get('font_size'),
                        "couleur": removed_span.get('color_rgb')
                    },
                    'additional_styles': {},
                    'matching_spans': [removed_span],
                    'include_in_output': True,
                    'is_consumed': False,
                    'source': 'pymupdf_isolated'
                }
                
                # Ajout à la liste principale
                page_blocks.append(new_iso_block)

        # Marquer le bloc courant comme modifié manuellement
        self.current_block['match_source'] = 'manual'
        
        # Si le bloc courant est vide, on peut choisir de le supprimer ou de le garder vide
        # (Ici on le garde vide mais avec flag preserve_empty optionnel, ou on laisse l'utilisateur gérer)

        # Mise à jour complète UI
        self.update_block_details()
        self.refresh_display()      # Redessine les rectangles
        self.update_page_stats()
        self.populate_blocks_list()
        self.populate_available_spans() # Le span doit apparaître maintenant

        count = len(spans_to_remove)
        self.statusbar.showMessage(f"✓ {count} span(s) retiré(s) et rendu(s) disponible(s)", 2000)

    
    def add_spans_to_block(self):
        """
        Ajoute les spans sélectionnés au bloc courant.
        RÈGLE MÉTIER : Si le bloc était vide, il adopte immédiatement 
        le style du premier span ajouté.
        """
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import Qt
        import copy  # Import nécessaire

        if not self.current_block:
            QMessageBox.warning(self, "Aucun bloc sélectionné", "Sélectionnez un bloc cible.")
            return

        if self.current_block.get('block_type') == 'isolated_span':
            return

        items = self.control_panel.available_spans_list.selectedItems()
        if not items:
            return

        self.save_state()
        page_blocks = self.data_manager.get_page_blocks()
        spans_added = 0

        current_spans = self.current_block.get('matching_spans', [])
        was_empty_before = (len(current_spans) == 0)
        
        first_span_style = None

        for item in items:
            span = item.data(Qt.UserRole)
            
            if first_span_style is None:
                first_span_style = {
                    "police": span.get('font_name', 'Arial'),
                    "taille": span.get('font_size', 12),
                    "couleur": span.get('color_rgb', [0, 0, 0])
                }

            for block in page_blocks[:]:
                if block.get('block_type') == 'isolated_span':
                    for s in block.get('matching_spans', [])[:]:
                        if s['id'] == span['id']:
                            block['matching_spans'].remove(s)
                            if not block['matching_spans']:
                                page_blocks.remove(block)
                            s['matched_to_block'] = self.current_block['id']
                            self.current_block.setdefault('matching_spans', []).append(s)
                            spans_added += 1
                            break

        if spans_added > 0 and was_empty_before and first_span_style:
            # ✅ CORRECTION CRITIQUE : Utiliser deepcopy
            self.current_block['default_style'] = copy.deepcopy(first_span_style)
            
            if 'enriched_data' in self.session_data:
                found = False
                for p_blocks in self.session_data['enriched_data']:
                    for b in p_blocks:
                        if isinstance(b, dict) and b.get('id') == self.current_block.get('id'):
                            # ✅ CORRECTION : deepcopy
                            b['default_style'] = copy.deepcopy(first_span_style)
                            found = True
                            break
                    if found:
                        break

        self.current_block['match_source'] = 'manual'
        self.update_block_details()
        self.refresh_display()
        self.update_page_stats()
        self.populate_blocks_list()

        self.statusbar.showMessage(f"✓ {spans_added} span(s) ajouté(s)", 2000)



    
    # ========================================================================
    # ACTIONS SUR LES BLOCS
    # ========================================================================
    
    def toggle_preserve_empty(self):
        """Basculer l'état de préservation d'un bloc vide"""
        if not self.current_block:
            return
        
        self.save_state()
        self.current_block['preserve_empty'] = not self.current_block.get('preserve_empty', False)
        
        self.update_block_details()
        self.refresh_display()
        self.populate_blocks_list()
    
    def toggle_include_isolated(self):
        """Basculer l'inclusion d'un ou plusieurs isolated_spans"""
        
        # ✅ Lire la sélection depuis available_spans_list (pas blocks_list)
        selected_items = self.control_panel.available_spans_list.selectedItems()
        selected_span_data = [item.data(Qt.UserRole) for item in selected_items]
        
        if len(selected_span_data) == 0:
            self.statusbar.showMessage("Veuillez sélectionner au moins 1 isolated span", 2000)
            return
        
        # Trouver les blocs parents
        page_blocks = self.data_manager.get_page_blocks()
        selected_blocks = []
        
        for span_data in selected_span_data:
            span_id = span_data.get('id')
            for block in page_blocks:
                if block.get('block_type') == 'isolated_span':
                    spans_in_block = block.get('matching_spans', [])
                    if spans_in_block and spans_in_block[0].get('id') == span_id:
                        selected_blocks.append(block)
                        break
        
        if len(selected_blocks) == 0:
            return
        
        self.save_state()
        
        # Déterminer l'action
        included_count = sum(1 for b in selected_blocks if b.get('include_in_output', True))
        new_state = included_count <= len(selected_blocks) / 2
        
        # Appliquer
        for block in selected_blocks:
            block['include_in_output'] = new_state
        
        action = "inclus" if new_state else "exclus"
        self.statusbar.showMessage(f"✓ {len(selected_blocks)} isolated_span(s) {action}", 2000)
        
        self.populate_available_spans()
        self.update_page_stats()
        self.refresh_display()


        
    def update_block_bbox(self, block: Dict[str, Any], rect, pos):
        """
        Mettre à jour la bbox d'un bloc après redimensionnement
        
        Args:
            block: Bloc à mettre à jour
            rect: Nouveau rectangle
            pos: Nouvelle position
        """
        doc = fitz.open(self.pdf_path)
        page = doc.load_page(self.data_manager.current_page)
        scale = 2.0 * self.pdf_renderer.zoom_level
        
        x0 = (rect.x() + pos.x()) / (page.rect.width * scale)
        y0 = (rect.y() + pos.y()) / (page.rect.height * scale)
        x1 = x0 + rect.width() / (page.rect.width * scale)
        y1 = y0 + rect.height() / (page.rect.height * scale)
        
        if 'mineru_original' in block:
            block['mineru_original']['bbox'] = [x0, y0, x1, y1]
            block['match_source'] = 'manual'
        
        doc.close()
    
    def create_block_from_selection(self):
        from PyQt5.QtWidgets import QMessageBox

        # ✅ CORRECTION : Accepter la sélection depuis available_spans_list OU blocks_list
        selected_isolated_blocks = []
        
        # Cas 1 : Sélection depuis available_spans_list
        selected_span_items = self.control_panel.available_spans_list.selectedItems()
        if selected_span_items:
            selected_span_data = [item.data(Qt.UserRole) for item in selected_span_items]
            page_blocks = self.data_manager.get_page_blocks()
            
            for span_data in selected_span_data:
                span_id = span_data.get('id')
                for block in page_blocks:
                    if block.get('block_type') == 'isolated_span':
                        spans_in_block = block.get('matching_spans', [])
                        if spans_in_block and spans_in_block[0].get('id') == span_id:
                            selected_isolated_blocks.append(block)
                            break
        else:
            # Cas 2 : Sélection depuis blocks_list (comportement actuel)
            selected_isolated_blocks = [b for b in self.selected_blocks if b.get('block_type') == 'isolated_span']
        
        if len(selected_isolated_blocks) < 1:
            QMessageBox.warning(self, "Sélection vide", "Veuillez sélectionner au moins un isolated_span")
            return

        self.save_state()
        
        all_spans = [s for iso in selected_isolated_blocks for s in iso.get('matching_spans', [])]
        
        if not all_spans:
            QMessageBox.warning(self, "Erreur", "Aucun span trouvé dans les blocs sélectionnés")
            return

        min_x = min(s['bbox_pixels'][0] for s in all_spans)
        min_y = min(s['bbox_pixels'][1] for s in all_spans)
        max_x = max(s['bbox_pixels'][2] for s in all_spans)
        max_y = max(s['bbox_pixels'][3] for s in all_spans)

        page_blocks = self.data_manager.get_page_blocks()
        existing_ids = {b['id'] for b in page_blocks}
        new_id_num = 0
        while f"page{self.data_manager.current_page+1}_custom_{new_id_num}" in existing_ids:
            new_id_num += 1
        new_block_id = f"page{self.data_manager.current_page+1}_custom_{new_id_num}"

        first_span = all_spans[0]
        default_style = {
            "police": first_span.get('font_name', 'Arial'),
            "taille": first_span.get('font_size', 12),
            "couleur": first_span.get('color_rgb', [0, 0, 0])
        }

        doc = fitz.open(self.pdf_path)
        page = doc.load_page(self.data_manager.current_page)
        norm_bbox = [min_x / page.rect.width, min_y / page.rect.height, max_x / page.rect.width, max_y / page.rect.height]
        doc.close()

        new_block = {
            'id': new_block_id,
            'content': ' '.join(s['text'] for s in all_spans),
            'block_type': 'text',
            'matching_spans': all_spans,
            'match_source': 'manual',
            'styled_content': ' '.join(s['text'] for s in all_spans),
            'position_xy': [min_x, min_y],
            'max_allowable_width': max_x - min_x,
            'default_style': default_style,
            'additional_styles': {},
            'preserve_empty': False,
            'include_in_output': True,
            'align': 'left',  # <--- AJOUTE ICI (valeur par défaut pour nouveaux blocs)
            'mineru_original': {'bbox': norm_bbox, 'type': 'text'}
        }

        # Marquer les isolated_span comme consommés
        for iso_block in selected_isolated_blocks:
            iso_id = iso_block.get('id')
            
            # Modifier directement dans page_blocks
            for block in page_blocks:
                if block.get('id') == iso_id:
                    block['is_consumed'] = True
                    block['include_in_output'] = False
                    break
            
            # Réassigner les spans
            for span in iso_block.get('matching_spans', []):
                span['matched_to_block'] = new_block_id

        page_blocks.append(new_block)
        self.selected_blocks = [new_block]
        self.current_block = new_block
        
        self.save_current_session()
        self.refresh_display()
        
        QMessageBox.information(self, "Bloc créé", f"Nouveau bloc '{new_block_id}' créé avec {len(all_spans)} spans.")



    
    # ========================================================================
    # UNDO/REDO
    # ========================================================================
    
    def save_state(self):
        """Sauvegarder l'état actuel pour undo"""
        self.state_manager.save_state(self.data_manager.enriched_data)
        self.control_panel.update_button_states(
            self.state_manager.can_undo(),
            self.state_manager.can_redo()
        )
    
    def undo(self):
        """Annuler la dernière action"""
        state = self.state_manager.undo()
        if state is not None:
            self.data_manager.enriched_data = state
            self.load_page(self.data_manager.current_page)
            self.control_panel.update_button_states(
                self.state_manager.can_undo(),
                self.state_manager.can_redo()
            )
    
    def redo(self):
        """Refaire l'action annulée"""
        state = self.state_manager.redo()
        if state is not None:
            self.data_manager.enriched_data = state
            self.load_page(self.data_manager.current_page)
            self.control_panel.update_button_states(
                self.state_manager.can_undo(),
                self.state_manager.can_redo()
            )
    

    def generate_translation_format_and_metadata_files(self):
        """
        Génère les fichiers JSON de traduction, formatage et
        le fichier de métadonnées de validation.
        Inclut les corrections manuelles (overrides).
        """
        reply = QMessageBox.question(
            self, 'Générer Traduction et Métadonnées',
            'Générer les fichiers traduction, formatage et métadonnées ?',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        try:
            from ..core.extract import DualOutputGenerator
            import json

            global_styles_data = self.session_data.get('global_styles', {
                'styles': {}, 'block_style_refs': {}
            })
            
            # --- AJOUT CRITIQUE : Récupérer les overrides ---
            overrides = self.session_data.get('translation_overrides', {})
            print(f"[DEBUG BUTTON] Overrides envoyés : {len(overrides)}")
            # ----------------------------------------------

            generator = DualOutputGenerator(
                enriched_data=self.data_manager.enriched_data,
                page_dimensions=None,
                global_styles_data=global_styles_data,
                translation_overrides=overrides  # <--- PASSAGE DES CORRECTIONS
            )

            # Récupérer dimensions pages (code extrait de save_corrections)
            generator.page_dimensions = {}
            doc = fitz.open(self.pdf_path)
            for i in range(len(doc)):
                page = doc.load_page(i)
                generator.page_dimensions[i] = [page.rect.width, page.rect.height]
            doc.close()

            # Compléter les métadonnées manquantes
            for page_blocks in self.data_manager.enriched_data:
                if isinstance(page_blocks, list):
                    for block in page_blocks:
                        if isinstance(block, dict) and block.get('block_type') != 'isolated_span':
                            if 'position_xy' not in block and 'mineru_original' in block and 'bbox' in block['mineru_original']:
                                bbox = block['mineru_original']['bbox']
                                page_dims = generator.page_dimensions.get(0, [595, 842])
                                block['position_xy'] = [bbox[0] * page_dims[0], bbox[1] * page_dims[1]]
                            if 'max_allowable_width' not in block and 'mineru_original' in block and 'bbox' in block['mineru_original']:
                                bbox = block['mineru_original']['bbox']
                                page_dims = generator.page_dimensions.get(0, [595, 842])
                                block['max_allowable_width'] = (bbox[2] - bbox[0]) * page_dims[0]

            # GÉNÉRER LES 3 FICHIERS
            formatting_data = generator._generate_formatting_format(self.data_manager.enriched_data)
            translation_data = generator._generate_translation_format(self.data_manager.enriched_data)

            # Mettre à jour session avec styles
            self.session_data['global_styles'] = {
                'styles': generator.global_styles,
                'block_style_refs': generator.block_additional_style_refs
            }

            # Sauvegarder JSON
            trans_file = f'{self.basename}_pour_traduction.json'
            fmt_file = f'{self.basename}_formatage.json'

            with open(trans_file, 'w', encoding='utf-8') as f:
                json.dump(translation_data, f, indent=2, ensure_ascii=False)
            with open(fmt_file, 'w', encoding='utf-8') as f:
                json.dump(formatting_data, f, indent=2, ensure_ascii=False)

            # GÉNÉRER MÉTADONNÉES + SAUVEGARDER SESSION
            self.save_current_session()
            meta_file = save_validation_metadata(self.basename, self.data_manager.enriched_data)

            msg = f'✅ Fichiers générés :\n• {trans_file}\n• {fmt_file}\n• {meta_file}'
            if overrides:
                msg += f"\n\n(Inclut {len(overrides)} corrections manuelles)"

            QMessageBox.information(self, 'Succès', msg)
            self.statusbar.showMessage("✅ Traduction, formatage et métadonnées générés", 6000)

        except Exception as e:
            import traceback
            QMessageBox.critical(self, 'Erreur', f'Erreur génération traduction:\n{e}\n\n{traceback.format_exc()}')



    def generate_pdf_template_file(self):
        """
        Génère uniquement le fichier template PDF vide,
        sans générer les JSON ou métadonnées associées.
        """
        reply = QMessageBox.question(
            self, 'Générer Template PDF',
            'Générer le fichier template PDF (sans texte) ?',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        try:
            from ..core.extract import DualOutputGenerator

            global_styles_data = self.session_data.get('global_styles', {
                'styles': {}, 'block_style_refs': {}
            })

            generator = DualOutputGenerator(
                enriched_data=self.data_manager.enriched_data,
                page_dimensions=self.session_data.get('page_dimensions', {}),
                global_styles_data=global_styles_data
            )

            template_file = f"{self.basename}_template.pdf"
            generator.create_clean_template(self.pdf_path, template_file, self.data_manager.enriched_data)

            QMessageBox.information(self, "Succès", f'✅ Template PDF généré :\n{template_file}')
            self.statusbar.showMessage(f"✅ Template PDF : {template_file}", 4000)

        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Erreur", f'Erreur template PDF:\n{e}\n\n{traceback.format_exc()}')
            self.statusbar.showMessage("❌ Erreur template PDF", 4000)

    def update_block_default_style(self, block):
        """
        Met à jour le style par défaut du bloc.
        RÈGLES STRICTES :
        1. Si bloc VIDE : Appliquer style majoritaire (copie unique).
        2. Si bloc NON VIDE mais style INVALIDE (Unknown/Helvetica) : Réparer avec style du 1er span.
        3. Si bloc NON VIDE et style VALIDE : NE RIEN FAIRE.
        """
        import copy
        
        if not isinstance(block, dict):
            return

        # Définition stricte de ce qui est "invalide"
        INVALID_FONTS = [None, '', 'Unknown', 'Helvetica']
        
        current_style = block.get('default_style', {})
        if not isinstance(current_style, dict):
            current_style = {}

        current_font = current_style.get('police')
        spans = block.get('matching_spans', [])

        # --- CAS 1 : Le bloc a déjà du contenu ---
        if len(spans) > 0:
            # On ne touche à rien si la police actuelle semble valide (pas dans la liste interdite)
            if current_font not in INVALID_FONTS:
                return  # <--- ON SORT ICI, on ne touche pas au style existant valide.

            # Si on est ici, c'est que le bloc a du contenu MAIS un style "pourri" (ex: Helvetica par défaut)
            # On répare en prenant le style du premier span réel
            first_span = spans[0]
            repaired_style = {
                "police": first_span.get('font_name', 'Arial'),
                "taille": first_span.get('font_size', 12),
                "couleur": first_span.get('color_rgb', [0, 0, 0])
            }
            # On applique une COPIE propre
            block['default_style'] = copy.deepcopy(repaired_style)

        # --- CAS 2 : Le bloc est VIDE ---
        else:
            # Si le bloc est vide, on ne veut pas laisser "Unknown" ou "Helvetica"
            # On remplace par la majorité uniquement si le style actuel est invalide
            if current_font in INVALID_FONTS:
                
                # Calcul (lazy) du style majoritaire seulement si nécessaire
                style_counts = {}
                taille_acc = {}
                color_map = {}

                for page_blocks in self.data_manager.enriched_data:
                    for b in page_blocks:
                        for span in b.get('matching_spans', []):
                            font = span.get('font_name')
                            if not font or font in INVALID_FONTS:
                                continue
                            style_counts[font] = style_counts.get(font, 0) + 1
                            taille_acc[font] = taille_acc.get(font, 0) + span.get('font_size', 0)
                            color_map[font] = span.get('color_rgb', [0, 0, 0])

                if style_counts:
                    majority_font = max(style_counts, key=style_counts.get)
                    count = style_counts[majority_font]
                    avg_taille = taille_acc[majority_font] / count
                    
                    majority_style = {
                        "police": majority_font,
                        "taille": avg_taille,
                        "couleur": color_map.get(majority_font, [0, 0, 0])
                    }
                    # On applique une COPIE propre
                    block['default_style'] = copy.deepcopy(majority_style)

        # Synchronisation session (copie aussi)
        if 'enriched_data' in self.session_data:
            for page_blocks in self.session_data['enriched_data']:
                for b in page_blocks:
                    if isinstance(b, dict) and b.get('id') == block.get('id'):
                        # On met à jour seulement si on a modifié block['default_style'] ci-dessus
                        # Par sécurité on force la synchro avec deepcopy
                        b['default_style'] = copy.deepcopy(block['default_style'])



 
    def update_isolated_block_bbox(self, block_data, new_rect, pos):
        """
        Mettre à jour la bbox d'un isolated_span après redimensionnement
        
        Args:
            block_data: Données du bloc isolated_span
            new_rect: Nouveau QRectF
            pos: Position (pas utilisée pour isolated_span car pas de déplacement)
        """
        scale = 2.0 * self.pdf_renderer.zoom_level
        
        # Convertir les coordonnées du rectangle en bbox_pixels
        new_bbox = [
            new_rect.left() / scale,
            new_rect.top() / scale,
            new_rect.right() / scale,
            new_rect.bottom() / scale
        ]
        
        # Mettre à jour le span dans le bloc
        if block_data.get('matching_spans'):
            block_data['matching_spans'][0]['bbox_pixels'] = new_bbox
        
        # Mettre à jour position_xy et max_allowable_width
        block_data['position_xy'] = [new_bbox[0], new_bbox[1]]
        block_data['max_allowable_width'] = new_bbox[2] - new_bbox[0]
        
        print(f"[INFO] Isolated span {block_data.get('id')} redimensionné: {new_bbox}")

 
    def stop_all_blinks(self):
        """Arrêter tous les timers de clignotement en cours"""
        if hasattr(self, '_blink_timers'):
            for timer in self._blink_timers[:]:  # Copie pour itération sûre
                try:
                    timer.stop()
                except RuntimeError:
                    pass  # Timer déjà détruit
                try:
                    timer.deleteLater()
                except RuntimeError:
                    pass  # Timer déjà détruit
            self._blink_timers.clear()



    def blink_items(self, items, duration_ms=2000):
        """
        Fait clignoter des items graphiques pendant une durée donnée.
        
        Args:
            items: Liste de QGraphicsRectItem
            duration_ms: Durée du clignotement en millisecondes
        """
        if not items:
            return
        
        from PyQt5.QtGui import QPen, QColor
        from PyQt5.QtCore import QTimer
        
        # ✅ Arrêter les anciens clignotements d'abord
        self.stop_all_blinks()
        
        # Sauvegarder les pens originaux
        original_pens = {}
        for item in items:
            try:
                original_pens[item] = item.pen()
            except RuntimeError:
                continue
        
        if not original_pens:
            return
        
        # États de clignotement
        blink_state = [0]
        blink_count = [0]
        max_blinks = 20
        timer_ref = [None]  # ✅ Référence partagée
        
        def toggle_blink():
            try:
                if blink_count[0] >= max_blinks:
                    # Restaurer les pens originaux
                    for item, pen in original_pens.items():
                        try:
                            item.setPen(pen)
                        except RuntimeError:
                            pass
                    # Nettoyer le timer
                    if timer_ref[0] and timer_ref[0] in self._blink_timers:
                        self._blink_timers.remove(timer_ref[0])
                    return
                
                for item in items:
                    try:
                        if blink_state[0] == 0:
                            pen = QPen(QColor(255, 0, 0), 8)
                            item.setPen(pen)
                        else:
                            item.setPen(original_pens.get(item))
                    except RuntimeError:
                        pass
                
                blink_state[0] = 1 - blink_state[0]
                blink_count[0] += 1
                
            except Exception as e:
                print(f"Erreur dans toggle_blink: {e}")
        
        # Timer pour le clignotement
        timer = QTimer(self)
        timer.timeout.connect(toggle_blink)
        timer.start(200)
        timer_ref[0] = timer  # ✅ Stocker la référence
        
        # Stocker le timer
        if not hasattr(self, '_blink_timers'):
            self._blink_timers = []
        self._blink_timers.append(timer)
        
        # Nettoyer après duration_ms
        def cleanup():
            try:
                # ✅ Vérifier que le timer existe encore
                if timer_ref[0] is not None:
                    if timer_ref[0] in self._blink_timers:
                        self._blink_timers.remove(timer_ref[0])
                    try:
                        timer_ref[0].stop()
                    except RuntimeError:
                        pass  # Timer déjà détruit
                    try:
                        timer_ref[0].deleteLater()
                    except RuntimeError:
                        pass  # Timer déjà détruit
            except Exception as e:
                print(f"Erreur dans cleanup: {e}")
        
        QTimer.singleShot(duration_ms, cleanup)


    
    # ========================================================================
    # NAVIGATION
    # ========================================================================
    
    def next_page(self):
        """Aller à la page suivante"""
        next_page = self.data_manager.current_page + 1
        if next_page < len(self.data_manager.enriched_data):
            self.load_page(next_page)
    
    def prev_page(self):
        """Aller à la page précédente"""
        prev_page = self.data_manager.current_page - 1
        if prev_page >= 0:
            self.load_page(prev_page)
    
    def zoom_in(self):
        """Augmenter le zoom"""
        self.pdf_renderer.set_zoom(self.pdf_renderer.zoom_level * 1.1)
        self.draw_page()
    
    def zoom_out(self):
        """Diminuer le zoom"""
        self.pdf_renderer.set_zoom(self.pdf_renderer.zoom_level / 1.1)
        self.draw_page()
    
    def zoom_reset(self):
        """Réinitialiser le zoom"""
        self.pdf_renderer.set_zoom(1.0)
        self.draw_page()
    
    # ========================================================================
    # RAFRAÎCHISSEMENT
    # ========================================================================
    
    def refresh_display(self):
        """Rafraîchir l'affichage complet"""
        self.draw_page()
        self.populate_blocks_list()
        self.update_page_stats()
        if self.current_block:
            self.highlight_current_block()
    
    # ✓ CORRECT
    def update_status(self):
        """Mettre à jour la barre de statut"""
        if self.current_block:
            block_type = self.current_block.get("block_type", "MinerU")
            if hasattr(self, 'statusbar') and self.statusbar is not None:
                self.statusbar.showMessage(
                    f"Bloc sélectionné - Page {self.data_manager.current_page + 1} "
                    f"- Type: {block_type}", 
                    3000
                )
        else:
            self.statusbar.showMessage(
                f"Page {self.data_manager.current_page + 1} / "
                f"{len(self.data_manager.enriched_data)}"
            )
        
    def closeEvent(self, event):
        """Événement de fermeture de la fenêtre"""
        try:
            # Sauvegarder l'état actuel
            self.save_current_session()
            
            # Sauvegarder l'état de la fenêtre
            if self.isMaximized():
                self.prefs.set("window.maximized", True)
            else:
                self.prefs.set("window.maximized", False)
                self.prefs.set("window.x", self.x())
                self.prefs.set("window.y", self.y())
                self.prefs.set("window.width", self.width())
                self.prefs.set("window.height", self.height())
            
            # Sauvegarder les tailles du splitter
            if self.main_splitter:
                self.prefs.set("splitters.main_horizontal", self.main_splitter.sizes())
            
        except Exception as e:
            print(f"Erreur lors de la fermeture: {e}")
        
        event.accept()

    def show_font_mapping_dialog(self):
        session_path = os.path.dirname(self.pdf_path)
        dialog = QDialog(self)
        dialog.setWindowTitle("Mapping des polices")
        dialog.resize(920, 520)
        layout = QVBoxLayout(dialog)
        panel = FontMappingPanel(session_path, self.pdf_path)
        layout.addWidget(panel)
        dialog.setLayout(layout)
        dialog.setModal(True)
        dialog.exec_()

    def show_translation_editor(self):
        """Ouvre l'éditeur de traduction/correction."""
        from .translation_editor import TranslationEditorDialog
        
        if not self.session_data: 
            QMessageBox.warning(self, "Erreur", "Aucune session chargée.")
            return
        
        # Calculer le dossier racine de la session
        # On utilise le dossier contenant le PDF comme racine de travail
        session_root = os.path.dirname(self.pdf_path) if self.pdf_path else "."
        
        # On passe les données de session qui contiennent 'translation_overrides'
        # et 'enriched_data' mis à jour
        editor = TranslationEditorDialog(self.session_data, session_root, self)
        editor.exec_()

    def show_svg_mapping_dialog(self):
        """Ouvre le panneau de gestion des SVG."""
        # Le root est le dossier contenant le PDF (comme pour font mapping)
        session_root = os.path.dirname(self.pdf_path)
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Gestion Images/SVG - {self.basename}")
        dialog.resize(800, 500)
        
        layout = QVBoxLayout(dialog)
        # On passe le session_root et le basename au panneau
        panel = SvgMappingPanel(session_root, self.basename, parent=dialog)
        
        layout.addWidget(panel)
        dialog.setLayout(layout)
        dialog.exec_()

    def generate_final_pdf(self):
        """Lance la génération du PDF final traduit."""
        # 1. Demander la langue
        lang, ok = QInputDialog.getText(
            self, "Générer PDF", 
            "Code langue cible (ex: FR) :", 
            text="FR"
        )
        if not ok or not lang.strip():
            return
            
        lang = lang.strip().upper()
        
        # 2. Sauvegarder tout avant de lancer
        self.save_current_session()
        
        # 3. Déterminer les chemins
        # Le dossier projet est celui contenant le PDF source
        project_dir = os.path.dirname(self.pdf_path)
        basename = self.basename
        
        # Vérifier si les fichiers nécessaires existent (notamment la traduction)
        trans_file = os.path.join(project_dir, f"{basename}_pour_traduction_{lang}.json")
        if not os.path.exists(trans_file):
            # Si le fichier spécifique langue n'existe pas, on cherche le générique
            trans_file_generic = os.path.join(project_dir, f"{basename}_pour_traduction.json")
            if os.path.exists(trans_file_generic):
                # On propose de l'utiliser ou de le copier ?
                # Pour simplifier, le builder s'attend à "_{lang}.json".
                # Copions le générique vers le spécifique pour le build si besoin
                import shutil
                shutil.copy2(trans_file_generic, trans_file)
                print(f"[Info] Copie de {trans_file_generic} vers {trans_file}")
            else:
                QMessageBox.warning(self, "Erreur", f"Fichier de traduction introuvable :\n{trans_file}")
                return

        # 4. Lancer le build
        try:
            self.statusbar.showMessage("Génération du PDF en cours...", 0)
            
            # Instanciation du builder avec le dossier projet correct
            builder = PDFBuilder(basename, lang, project_dir)
            output_path = builder.build()
            
            self.statusbar.showMessage(f"PDF généré : {output_path}", 5000)
            QMessageBox.information(self, "Succès", f"PDF généré avec succès :\n{output_path}")
            
            # Ouvrir le dossier ou le fichier ?
            # os.startfile(output_path) # Optionnel sous Windows
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.statusbar.showMessage("Erreur de génération", 5000)
            QMessageBox.critical(self, "Erreur de Build", f"Une erreur est survenue :\n{str(e)}")
