#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration des raccourcis clavier pour Block Validator
"""

from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QKeySequence


def setup_shortcuts(main_window):
    """
    Configurer tous les raccourcis clavier
    
    Args:
        main_window: Instance de BlockValidationInterface
    """
    
    # === NAVIGATION ===
    QShortcut(QKeySequence("Right"), main_window, main_window.next_page)
    QShortcut(QKeySequence("Left"), main_window, main_window.prev_page)
    QShortcut(QKeySequence("N"), main_window, main_window.next_page)
    QShortcut(QKeySequence("P"), main_window, main_window.prev_page)
    
    # === ZOOM ===
    QShortcut(QKeySequence("Plus"), main_window, main_window.zoom_in)
    QShortcut(QKeySequence("+"), main_window, main_window.zoom_in)
    QShortcut(QKeySequence("Minus"), main_window, main_window.zoom_out)
    QShortcut(QKeySequence("-"), main_window, main_window.zoom_out)
    QShortcut(QKeySequence("0"), main_window, main_window.zoom_reset)
    
    # === GESTION DES SPANS ===
    QShortcut(QKeySequence("Up"), main_window, main_window.move_span_up)
    QShortcut(QKeySequence("Down"), main_window, main_window.move_span_down)
    QShortcut(QKeySequence("Delete"), main_window, main_window.remove_span)
    QShortcut(QKeySequence("Backspace"), main_window, main_window.remove_span)
    
    # === ACTIONS SUR LES BLOCS ===
    QShortcut(QKeySequence("L"), main_window, main_window.toggle_preserve_empty)
    QShortcut(QKeySequence("I"), main_window, main_window.toggle_include_isolated)
    QShortcut(QKeySequence("A"), main_window, main_window.add_spans_to_block)
    QShortcut(QKeySequence("C"), main_window, main_window.create_block_from_selection)
    
    # === UNDO/REDO ===
    QShortcut(QKeySequence("Ctrl+Z"), main_window, main_window.undo)
    QShortcut(QKeySequence("Ctrl+Y"), main_window, main_window.redo)
    QShortcut(QKeySequence("Ctrl+Shift+Z"), main_window, main_window.redo)
    
    # === SAUVEGARDE ===
    QShortcut(QKeySequence("Ctrl+E"), main_window, main_window.generate_translation_format_and_metadata_files)


def get_shortcuts_help() -> str:
    """
    Obtenir l'aide des raccourcis clavier
    
    Returns:
        Texte d'aide formaté
    """
    help_text = """
    ╔════════════════════════════════════════╗
    ║     RACCOURCIS CLAVIER DISPONIBLES     ║
    ╠════════════════════════════════════════╣
    ║ NAVIGATION                             ║
    ║  → / N         Page suivante           ║
    ║  ← / P         Page précédente         ║
    ║                                        ║
    ║ ZOOM                                   ║
    ║  + / Plus      Zoomer                  ║
    ║  - / Minus     Dézoomer                ║
    ║  0             Réinitialiser zoom      ║
    ║                                        ║
    ║ GESTION DES SPANS                      ║
    ║  ↑             Déplacer span vers haut ║
    ║  ↓             Déplacer span vers bas  ║
    ║  Del / ⌫       Retirer span du bloc    ║
    ║  A             Ajouter spans           ║
    ║                                        ║
    ║ ACTIONS SUR BLOCS                      ║
    ║  L             Lock/Unlock bloc vide   ║
    ║  I             Include/Exclude isolé   ║
    ║  C             Créer bloc depuis ISO   ║
    ║                                        ║
    ║ HISTORIQUE                             ║
    ║  Ctrl+Z        Annuler                 ║
    ║  Ctrl+Y        Refaire                 ║
    ║                                        ║
    ║ FICHIER                                ║
    ║  Ctrl+S        Sauvegarder             ║
    ╚════════════════════════════════════════╝
    """
    return help_text
