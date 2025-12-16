#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rectangle cliquable et redimensionnable pour les isolated_spans avec clignotement cyan
"""

from PyQt5.QtWidgets import QGraphicsRectItem
from PyQt5.QtGui import QPen, QBrush, QColor
from PyQt5.QtCore import Qt, QTimer, QRectF


class ClickableIsolatedRect(QGraphicsRectItem):
    """Rectangle isolated_span redimensionnable avec clignotement CYAN"""
    
    def __init__(self, rect, block_data, parent_interface):
        super().__init__(rect)
        self.block_data = block_data
        self.parent_interface = parent_interface
        
        # État du clignotement
        self.is_highlighted = False
        self.blink_state = False
        
        # ✅ NOUVEAU : Redimensionnement
        self.resize_handle_size = 8
        self.resize_mode = None
        self.initial_rect = None
        self.initial_pos = None
        
        # Timer pour clignotement
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.toggle_blink)
        
        # ✅ NOUVEAU : Flags pour permettre le redimensionnement
        self.setFlag(QGraphicsRectItem.ItemIsMovable, False)  # Pas de déplacement
        self.setFlag(QGraphicsRectItem.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        
        self.update_style()
    
    def toggle_blink(self):
        """Basculer l'état du clignotement"""
        self.blink_state = not self.blink_state
        self.apply_style()
    
    def update_style(self, highlighted=False):
        """Mettre à jour le style du rectangle"""
        self.is_highlighted = highlighted
        if highlighted:
            self.blink_timer.start(500)
        else:
            self.blink_timer.stop()
            self.blink_state = False
        self.apply_style()
    
    def apply_style(self):
        """Appliquer le style"""
        include = self.block_data.get('include_in_output', True)
        
        if self.is_highlighted:
            # Bloc sélectionné - clignotement
            if self.blink_state:
                border_color = QColor(0, 255, 255)      # Cyan bright
                border_width = 7
                fill_color = QColor(0, 255, 255, 120)   # Cyan semi-transparent
            else:
                border_color = QColor(0, 180, 180)      # Cyan dark
                border_width = 7
                fill_color = QColor(0, 180, 180, 80)    # Cyan dark semi-transparent
            line_style = Qt.SolidLine
        elif include:
            # Bloc inclus - vert
            border_color = QColor(0, 200, 0)        # Vert
            border_width = 2
            fill_color = QColor(0, 200, 0, 80)      # Vert semi-transparent
            line_style = Qt.SolidLine
        else:
            # Bloc exclus - gris
            border_color = QColor(200, 200, 200)    # Gris
            border_width = 2
            fill_color = QColor(200, 200, 200, 60)  # Gris semi-transparent
            line_style = Qt.DashLine
        
        self.setPen(QPen(border_color, border_width, line_style))
        self.setBrush(QBrush(fill_color))
    
    # ✅ NOUVEAU : Méthodes de redimensionnement
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
            self.setCursor(Qt.PointingHandCursor)
        super().hoverMoveEvent(event)
    
    def mousePressEvent(self, event):
        """Gérer le clic (sélection ou début redimensionnement)"""
        if event.button() == Qt.LeftButton:
            self.resize_mode = self.get_resize_handle_at(event.pos())
            self.initial_rect = self.rect()
            self.initial_pos = event.pos()
            
            if not self.resize_mode:
                # Clic normal - sélection
                self.parent_interface.select_isolated_block(self.block_data)
        
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
                # ✅ Appeler la méthode pour sauvegarder la nouvelle bbox
                self.parent_interface.update_isolated_block_bbox(
                    self.block_data, self.rect(), self.pos()
                )
            self.resize_mode = None
            self.initial_rect = None
            self.initial_pos = None
        
        super().mouseReleaseEvent(event)
    
    def hoverEnterEvent(self, event):
        """Garder le curseur pointeur si pas sur une poignée"""
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Restaurer le curseur"""
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)
    
    def paint(self, painter, option, widget=None):
        """Dessiner le rectangle avec poignées si sélectionné et clignotement CYAN"""
        super().paint(painter, option, widget)
        
        # Dessiner les poignées si sélectionné ou highlighted
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
