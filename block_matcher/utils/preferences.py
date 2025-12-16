#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestion des préférences utilisateur
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class PreferencesManager:
    """Gestionnaire des préférences UI"""
    
    def __init__(self, project_name: str):
        """
        Initialiser le gestionnaire
        
        Args:
            project_name: Nom du projet (pour préférences spécifiques)
        """
        self.project_name = project_name
        self.prefs_file = Path.home() / ".block_validator_prefs.json"
        self.preferences = self._load_preferences()
    
    def _load_preferences(self) -> Dict[str, Any]:
        """Charger les préférences depuis le fichier"""
        if not self.prefs_file.exists():
            return self._get_default_preferences()
        
        try:
            with open(self.prefs_file, 'r', encoding='utf-8') as f:
                all_prefs = json.load(f)
            
            # Retourner les préférences du projet ou défaut
            return all_prefs.get(self.project_name, self._get_default_preferences())
        
        except Exception as e:
            print(f"⚠️ Erreur chargement préférences: {e}")
            return self._get_default_preferences()
    
    def _get_default_preferences(self) -> Dict[str, Any]:
        """Obtenir les préférences par défaut"""
        return {
            'window': {
                'width': 1800,
                'height': 1000,
                'x': 50,
                'y': 50
            },
            'splitters': {
                'main_horizontal': [400, 800, 600],  # Panneau gauche, PDF, (non utilisé)
                'control_vertical': [300, 300, 200]   # Liste blocs, Détails, Disponibles
            },
            'sections': {
                'stats_collapsed': False,
                'details_collapsed': False
            },
            'viewer': {
                'zoom_level': 1.0,
                'show_all_spans': False
            },
            'last_page': 0
        }
    
    def save_preferences(self):
        """Sauvegarder les préférences dans le fichier"""
        try:
            # Charger toutes les préférences existantes
            all_prefs = {}
            if self.prefs_file.exists():
                with open(self.prefs_file, 'r', encoding='utf-8') as f:
                    all_prefs = json.load(f)
            
            # Mettre à jour les préférences du projet
            all_prefs[self.project_name] = self.preferences
            
            # Sauvegarder
            with open(self.prefs_file, 'w', encoding='utf-8') as f:
                json.dump(all_prefs, f, indent=2)
            
            print(f"✓ Préférences sauvegardées: {self.prefs_file}")
        
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde préférences: {e}")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Obtenir une préférence par son chemin
        
        Args:
            key_path: Chemin de la clé (ex: 'window.width')
            default: Valeur par défaut si non trouvée
            
        Returns:
            Valeur de la préférence
        """
        keys = key_path.split('.')
        value = self.preferences
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path: str, value: Any):
        """
        Définir une préférence par son chemin
        
        Args:
            key_path: Chemin de la clé (ex: 'window.width')
            value: Valeur à définir
        """
        keys = key_path.split('.')
        current = self.preferences
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
