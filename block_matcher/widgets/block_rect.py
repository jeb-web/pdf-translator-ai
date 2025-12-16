#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rectangle redimensionnable pour les blocs MinerU avec clignotement
"""

from PyQt5.QtWidgets import QGraphicsRectItem
from PyQt5.QtGui import QPen, QBrush, QColor, QPainter
from PyQt5.QtCore import Qt, QRectF, QTimer


class ResizableBlockRect(QGraphicsRectItem):
    """Rectangle MinerU redimensionnable avec poignées et clignotement"""
    
    def __init__(self, rect, block_data, parent_interface):
        super().__init__(rect)
        self.block_data = block_data
        self.parent_interface = parent_interface
        
        # État du clignotement
        self.is_highlighted = False
        self.blink_state = False
        
        # Redimensionnement
        self.resize_handle_size = 8
        self.resize_mode = None
        self.initial_rect = None
        self.initial_pos = None
        
        # Timer pour clignotement
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self._toggle_blink)
        
        self._setup_flags()
        self.update_style()
    
    def _setup_flags(self):
        """Configurer les flags du widget"""
        self.setFlag(QGraphicsRectItem.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
    
    def _toggle_blink(self):
        """Basculer l'état du clignotement"""
        self.blink_state = not self.blink_state
        self._apply_style()
    
    def update_style(self, highlighted=False):
        """
        Mettre à jour le style du rectangle
        
        Args:
            highlighted: Si True, active le clignotement magenta
        """
        self.is_highlighted = highlighted
        if highlighted:
            self.blink_timer.start(500)  # Clignotement toutes les 500ms
        else:
            self.blink_timer.stop()
            self.blink_state = False
        self._apply_style()
    
    def _apply_style(self):
        """Appliquer le style basé sur l'état du bloc"""
        spans = self.block_data.get('matching_spans', [])
        manual = self.block_data.get('match_source') == 'manual'
        empty = len(spans) == 0
        preserved = self.block_data.get('preserve_empty', False)
        
        if self.is_highlighted:
            # Clignotement MAGENTA pour highlight
            if self.blink_state:
                color = QColor(255, 0, 255)  # Magenta vif
                width = 6
                alpha = 150
            else:
                color = QColor(180, 0, 180)  # Magenta foncé
                width = 6
                alpha = 100
        elif empty and not preserved:
            # Rouge pour blocs vides non préservés
            color = QColor(255, 0, 0)
            width = 2
            alpha = 100
        elif empty and preserved:
            # Magenta pour blocs vides préservés
            color = QColor(200, 0, 200)
            width = 2
            alpha = 100
        elif manual:
            # Vert pour matches manuels
            color = QColor(0, 200, 0)
            width = 2
            alpha = 120
        elif spans:
            # Bleu pour matches automatiques
            color = QColor(0, 150, 255)
            width = 2
            alpha = 100
        else:
            # Orange par défaut
            color = QColor(255, 100, 0)
            width = 2
            alpha = 100
        
        color.setAlpha(alpha)
        self.setPen(QPen(color, width))
        self.setBrush(QBrush(color))
    
    def get_resize_handle_at(self, pos):
        """
        Déterminer si la position correspond à une poignée de redimensionnement
        
        Args:
            pos: Position de la souris
            
        Returns:
            Code de la poignée ('se', 'nw', etc.) ou None
        """
        rect = self.rect()
        hs = self.resize_handle_size
        
        # Coins
        if QRectF(rect.right() - hs, rect.bottom() - hs, hs*2, hs*2).contains(pos):
            return 'se'
        if QRectF(rect.left() - hs, rect.bottom() - hs, hs*2, hs*2).contains(pos):
            return 'sw'
        if QRectF(rect.right() - hs, rect.top() - hs, hs*2, hs*2).contains(pos):
            return 'ne'
        if QRectF(rect.left() - hs, rect.top() - hs, hs*2, hs*2).contains(pos):
            return 'nw'
        
        # Côtés
        if QRectF(rect.left() - hs, rect.center().y() - hs, hs*2, hs*2).contains(pos):
            return 'w'
        if QRectF(rect.right() - hs, rect.center().y() - hs, hs*2, hs*2).contains(pos):
            return 'e'
        if QRectF(rect.center().x() - hs, rect.top() - hs, hs*2, hs*2).contains(pos):
            return 'n'
        if QRectF(rect.center().x() - hs, rect.bottom() - hs, hs*2, hs*2).contains(pos):
            return 's'
        
        return None
    
    def hoverMoveEvent(self, event):
        """Changer le curseur selon la poignée survolée"""
        handle = self.get_resize_handle_at(event.pos())
        if handle in ['se', 'nw']:
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in ['sw', 'ne']:
            self.setCursor(Qt.SizeBDiagCursor)
        elif handle in ['e', 'w']:
            self.setCursor(Qt.SizeHorCursor)
        elif handle in ['n', 's']:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)
    
    def mousePressEvent(self, event):
        """Gérer le clic (sélection ou début redimensionnement)"""
        if event.button() == Qt.LeftButton:
            self.resize_mode = self.get_resize_handle_at(event.pos())
            self.initial_rect = self.rect()
            self.initial_pos = event.pos()
            
            if not self.resize_mode:
                self.parent_interface.select_mineru_block(self.block_data)
        
        event.accept()
    
    def mouseMoveEvent(self, event):
        """Gérer le redimensionnement"""
        if self.resize_mode and self.initial_rect:
            delta = event.pos() - self.initial_pos
            new_rect = QRectF(self.initial_rect)
            
            # Ajuster selon la poignée
            if 'e' in self.resize_mode:
                new_rect.setRight(self.initial_rect.right() + delta.x())
            if 'w' in self.resize_mode:
                new_rect.setLeft(self.initial_rect.left() + delta.x())
            if 's' in self.resize_mode:
                new_rect.setBottom(self.initial_rect.bottom() + delta.y())
            if 'n' in self.resize_mode:
                new_rect.setTop(self.initial_rect.top() + delta.y())
            
            # Taille minimale
            if new_rect.width() > 20 and new_rect.height() > 20:
                self.setRect(new_rect)
            
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Terminer le redimensionnement"""
        if event.button() == Qt.LeftButton:
            if self.resize_mode:
                self.parent_interface.update_block_bbox(
                    self.block_data, self.rect(), self.pos()
                )
            self.resize_mode = None
            self.initial_rect = None
            self.initial_pos = None
        
        super().mouseReleaseEvent(event)
    
    def paint(self, painter, option, widget=None):
        """Dessiner le rectangle avec poignées si sélectionné"""
        super().paint(painter, option, widget)
        
        if self.isSelected() or self.is_highlighted:
            rect = self.rect()
            hs = self.resize_handle_size
            
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            
            # Positions des 8 poignées
            handles = [
                (rect.right(), rect.bottom()),      # SE
                (rect.left(), rect.bottom()),       # SW
                (rect.right(), rect.top()),         # NE
                (rect.left(), rect.top()),          # NW
                (rect.left(), rect.center().y()),   # W
                (rect.right(), rect.center().y()),  # E
                (rect.center().x(), rect.top()),    # N
                (rect.center().x(), rect.bottom())  # S
            ]
            
            for x, y in handles:
                painter.drawRect(int(x - hs/2), int(y - hs/2), hs, hs)
