#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire d'état pour undo/redo et gestion de session complète
"""

import copy
import json
import os
from typing import List, Any, Optional


class StateManager:
    """Gestion de l'historique pour undo/redo et persistance de session"""
    
    MAX_HISTORY = 20  # Limite d'états en mémoire
    
    def __init__(self, session_file: Optional[str] = None):
        """
        Initialiser le gestionnaire d'état.
        
        Args:
            session_file (str, optional): Chemin du fichier de session JSON.
        """
        self.history: List[Any] = []
        self.history_index = -1
        self.session_file = session_file
        self.session_data = {
            "basename": "unknown",
            "enriched_data": [],
            "global_styles": {
                "styles": {},
                "block_style_refs": {}
            },
            "ui_state": {}
        }
    
    # --- Gestion historique ---

    def save_state(self, state: Any) -> None:
        """
        Sauvegarder l'état actuel (copie profonde).
        
        Args:
            state: État à sauvegarder
        """
        if len(self.history) >= self.MAX_HISTORY:
            self.history.pop(0)
            self.history_index -= 1
        
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]
        
        self.history.append(copy.deepcopy(state))
        self.history_index += 1
    
    def can_undo(self) -> bool:
        return self.history_index > 0
    
    def can_redo(self) -> bool:
        return self.history_index < len(self.history) - 1
    
    def undo(self) -> Optional[Any]:
        if not self.can_undo():
            return None
        self.history_index -= 1
        return copy.deepcopy(self.history[self.history_index])
    
    def redo(self) -> Optional[Any]:
        if not self.can_redo():
            return None
        self.history_index += 1
        return copy.deepcopy(self.history[self.history_index])
    
    def clear(self) -> None:
        self.history.clear()
        self.history_index = -1
        
    def get_history_size(self) -> int:
        return len(self.history)
    
    # --- Gestion de session (chargement/sauvegarde) ---
    
    def load_session(self, session_file: Optional[str] = None) -> dict:
        """
        Charger la session depuis un fichier JSON.
        
        Args:
            session_file (str, optional): Fichier à charger (par défaut self.session_file)
        
        Returns:
            dict: Données de la session chargée
        """
        path = session_file or self.session_file
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"Fichier de session introuvable : {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Injection rétrocompatible de global_styles si manquant
        if "global_styles" not in data:
            data["global_styles"] = {"styles": {}, "block_style_refs": {}}
        
        self.session_file = path
        self.session_data = data
        
        return data
    
    def save_current_session(self, session_file: Optional[str] = None) -> None:
        """
        Sauvegarder la session actuelle dans un fichier JSON.
        
        Args:
            session_file (str, optional): Fichier de sauvegarde (par défaut self.session_file)
        """
        path = session_file or self.session_file
        if not path:
            raise ValueError("Aucun fichier de session défini pour la sauvegarde")
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.session_data, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Session sauvegardée : {path}")
    
    def update_session_data(self, key: str, value: Any) -> None:
        """
        Mettre à jour une clé spécifique dans la session.
        
        Args:
            key (str): Clé à mettre à jour
            value (Any): Nouvelle valeur
        """
        self.session_data[key] = value

