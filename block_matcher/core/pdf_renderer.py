#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rendu PDF avec overlays de blocs et spans (incluant isolated_spans)
"""

import fitz  # PyMuPDF
from PyQt5.QtWidgets import QGraphicsScene
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont
from PyQt5.QtCore import QRectF
from typing import Dict, List, Any, Tuple

from ..widgets.block_rect import ResizableBlockRect
from ..widgets.span_rect import ClickableSpanRect
from ..widgets.isolated_rect import ClickableIsolatedRect


class PDFRenderer:
    """Gestionnaire de rendu PDF avec overlays graphiques"""
    
    def __init__(self, pdf_path: str):
        """
        Initialiser le renderer
        
        Args:
            pdf_path: Chemin vers le fichier PDF
        """
        self.pdf_path = pdf_path
        self.zoom_level = 1.0
        self.doc = None
    
    def open_document(self) -> None:
        """Ouvrir le document PDF"""
        if self.doc is None:
            self.doc = fitz.open(self.pdf_path)
    
    def close_document(self) -> None:
        """Fermer le document PDF"""
        if self.doc is not None:
            self.doc.close()
            self.doc = None
    
    def render_page_to_pixmap(self, page_num: int) -> QPixmap:
        """
        Rendre une page en QPixmap
        
        Args:
            page_num: Numéro de la page
            
        Returns:
            QPixmap de la page rendue
        """
        self.open_document()
        page = self.doc.load_page(page_num)
        
        # Render avec zoom
        mat = fitz.Matrix(2.0 * self.zoom_level, 2.0 * self.zoom_level)
        pix = page.get_pixmap(matrix=mat)
        
        # Convertir en QPixmap
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, 
                     QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        
        return pixmap
    
    def get_page_dimensions(self, page_num: int) -> Tuple[float, float]:
        """
        Obtenir les dimensions d'une page
        
        Args:
            page_num: Numéro de la page
            
        Returns:
            (width, height) en points
        """
        self.open_document()
        page = self.doc.load_page(page_num)
        return (page.rect.width, page.rect.height)
    
    def render_page_with_overlays(
            self, 
            scene: QGraphicsScene,
            page_num: int, 
            page_blocks: List[Dict[str, Any]],
            parent_interface,
            show_all_spans: bool = False
        ) -> Tuple[Dict, Dict]:
            """
            Rendre une page avec overlays de blocs, spans et isolated_spans
            """
            scene.clear()
            
            # Rendre le PDF
            pixmap = self.render_page_to_pixmap(page_num)
            scene.addPixmap(pixmap)
            
            # Obtenir dimensions de la page
            page_width, page_height = self.get_page_dimensions(page_num)
            scale = 2.0 * self.zoom_level
            
            mineru_rects = {}
            span_rects = {}
            
            # 1. Dessiner les blocs MinerU normaux (ResizableBlockRect)
            block_index = 0
            for block in page_blocks:
                if 'mineru_original' in block and block.get('block_type') and \
                   block.get('block_type') != 'isolated_span':
                    
                    bbox = block['mineru_original']['bbox']
                    
                    # Convertir bbox normalisé en coordonnées pixels
                    rect = QRectF(
                        bbox[0] * page_width * scale,
                        bbox[1] * page_height * scale,
                        (bbox[2] - bbox[0]) * page_width * scale,
                        (bbox[3] - bbox[1]) * page_height * scale
                    )
                    
                    block_rect = ResizableBlockRect(rect, block, parent_interface)
                    scene.addItem(block_rect)
                    mineru_rects[block['id']] = block_rect
                    
                    # Ajouter label
                    label_text = f"B{block_index}"
                    text_item = scene.addText(label_text)
                    text_item.setDefaultTextColor(QColor(255, 0, 0))
                    text_item.setFont(QFont("Arial", 10, QFont.Bold))
                    text_item.setPos(rect.topLeft())
                    
                    block_index += 1
            
            # 2. Dessiner les spans PyMuPDF normaux (ClickableSpanRect)
            for block in page_blocks:
                if block.get('block_type') != 'isolated_span':
                    for span in block.get('matching_spans', []):
                        if span['id'] not in span_rects:
                            span_rect = self._create_span_rect(
                                span, scale, scene, parent_interface
                            )
                            span_rects[span['id']] = span_rect
            
            # 3. Dessiner les isolated_spans (ClickableIsolatedRect)
            for block in page_blocks:
                if block.get('block_type') == 'isolated_span':
                    spans = block.get('matching_spans') or []
                    if spans and isinstance(spans, list) and len(spans) > 0:
                        span = spans[0]
                        if isinstance(span, dict) and 'bbox_pixels' in span:
                            bbox = span['bbox_pixels']
                            rect = QRectF(
                                bbox[0] * scale,
                                bbox[1] * scale,
                                (bbox[2] - bbox[0]) * scale,
                                (bbox[3] - bbox[1]) * scale
                            )
                            
                            # Utiliser ClickableIsolatedRect
                            iso_rect = ClickableIsolatedRect(rect, block, parent_interface)
                            scene.addItem(iso_rect)
                            
                            # ✅ CORRECTION : Ajouter AUSSI à span_rects avec l'ID du span
                            mineru_rects[block['id']] = iso_rect
                            span_rects[span['id']] = iso_rect  # ← LIGNE AJOUTÉE
            
            return mineru_rects, span_rects


    
    def _create_span_rect(
        self, 
        span: Dict[str, Any], 
        scale: float, 
        scene: QGraphicsScene, 
        parent_interface
    ) -> ClickableSpanRect:
        """
        Créer un rectangle pour un span
        
        Args:
            span: Données du span
            scale: Facteur d'échelle
            scene: Scène graphique
            parent_interface: Interface parente
            
        Returns:
            ClickableSpanRect créé
        """
        bbox_px = span['bbox_pixels']
        rect = QRectF(
            bbox_px[0] * scale,
            bbox_px[1] * scale,
            (bbox_px[2] - bbox_px[0]) * scale,
            (bbox_px[3] - bbox_px[1]) * scale
        )
        
        span_rect = ClickableSpanRect(rect, span, parent_interface)
        scene.addItem(span_rect)
        return span_rect
    
    def set_zoom(self, zoom_level: float) -> None:
        """
        Définir le niveau de zoom
        
        Args:
            zoom_level: Niveau de zoom (0.5 à 3.0)
        """
        self.zoom_level = max(0.5, min(3.0, zoom_level))
    
    def zoom_in(self, step: float = 0.2) -> float:
        """
        Zoomer
        
        Args:
            step: Incrément de zoom
            
        Returns:
            Nouveau niveau de zoom
        """
        self.zoom_level = min(3.0, self.zoom_level + step)
        return self.zoom_level
    
    def zoom_out(self, step: float = 0.2) -> float:
        """
        Dézoomer
        
        Args:
            step: Décrément de zoom
            
        Returns:
            Nouveau niveau de zoom
        """
        self.zoom_level = max(0.5, self.zoom_level - step)
        return self.zoom_level
    
    def zoom_reset(self) -> float:
        """
        Réinitialiser le zoom
        
        Returns:
            Niveau de zoom (1.0)
        """
        self.zoom_level = 1.0
        return self.zoom_level
    
    def __del__(self):
        """Destructeur - fermer le document"""
        self.close_document()
