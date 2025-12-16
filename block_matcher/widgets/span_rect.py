#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rectangle cliquable pour les spans PyMuPDF (version validation)
"""

from PyQt5.QtWidgets import QGraphicsRectItem
from PyQt5.QtGui import QPen, QBrush, QColor
from PyQt5.QtCore import Qt


class ClickableSpanRect(QGraphicsRectItem):
    """Rectangle cliquable représentant un span PyMuPDF"""
    
    # Couleurs pour les différents états
    COLORS = {
        'matched': QColor(0, 0, 255, 80),       # Bleu transparent
        'unmatched': QColor(255, 0, 0, 100),    # Rouge transparent
    }
    
    PEN_WIDTHS = {
        'matched': 1,
        'unmatched': 1,
    }
    
    def __init__(self, rect, span_data, parent_interface):
        """
        Initialiser le rectangle de span
        
        Args:
            rect: QRectF définissant la position et taille
            span_data: Dict contenant les données du span
            parent_interface: Référence à l'interface principale
        """
        super().__init__(rect)
        self.span_data = span_data
        self.parent_interface = parent_interface
        
        self.setAcceptHoverEvents(True)
        self.update_style()
    
    def update_style(self):
        """Mettre à jour le style basé sur le statut"""
        is_matched = self.span_data.get('matched_to_block') is not None
        
        if is_matched:
            # Déjà matché - bleu transparent
            color = self.COLORS['matched']
            pen_width = self.PEN_WIDTHS['matched']
        else:
            # Non matché - rouge transparent
            color = self.COLORS['unmatched']
            pen_width = self.PEN_WIDTHS['unmatched']
        
        self.setPen(QPen(color, pen_width))
        self.setBrush(QBrush(color))
    
    def mousePressEvent(self, event):
        """
        Gérer le clic sur le span
        
        Args:
            event: Événement de clic souris
        """
        if event.button() == Qt.LeftButton:
            # Vérifier que la méthode existe avant de l'appeler
            if hasattr(self.parent_interface, 'on_span_clicked'):
                self.parent_interface.on_span_clicked(self.span_data)
        event.accept()
    
    def hoverEnterEvent(self, event):
        """
        Effet hover - réduire l'opacité
        
        Args:
            event: Événement hover
        """
        self.setOpacity(0.7)
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """
        Retirer l'effet hover
        
        Args:
            event: Événement hover
        """
        self.setOpacity(1.0)
        super().hoverLeaveEvent(event)
