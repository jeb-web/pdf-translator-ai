# core/sessionmanager.py

import json
import os
from typing import Dict, Any, Optional

def create_new_session(basename: str, pdf_path: str, enriched_data: list, page_dimensions: Dict) -> Dict[str, Any]:
    """
    Crée une nouvelle structure de session.
    
    Args:
        basename: Nom de base du projet
        pdf_path: Chemin du fichier PDF
        enriched_data: Données enrichies des blocs
        page_dimensions: Dimensions des pages
    
    Returns:
        Structure de session complète
    """
    session_data = {
        "version": "1.0",
        "basename": basename,
        "pdf_path": pdf_path,
        "enriched_data": enriched_data,
        "page_dimensions": page_dimensions,
        # ✅ NOUVEAU : Initialiser global_styles vide
        "global_styles": {
            "styles": {},
            "block_style_refs": {}
        },
        "ui_state": {
            "current_page": 0,
            "zoom_level": 1.0
        }
    }
    return session_data


def load_session(session_file: str) -> Optional[Dict[str, Any]]:
    """
    Charge une session depuis un fichier JSON.
    
    Args:
        session_file: Chemin du fichier de session
    
    Returns:
        Données de session ou None si échec
    """
    if not os.path.exists(session_file):
        print(f"[ERREUR] Fichier de session introuvable : {session_file}")
        return None
    
    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # ✅ NOUVEAU : Vérifier et initialiser global_styles si absent (rétrocompatibilité)
        if "global_styles" not in session_data:
            print("[INFO] Ancienne session détectée, ajout de global_styles")
            session_data["global_styles"] = {
                "styles": {},
                "block_style_refs": {}
            }
        
        print(f"[OK] Session chargée : {session_file}")
        return session_data
    
    except json.JSONDecodeError as e:
        print(f"[ERREUR] Impossible de lire le fichier de session : {e}")
        return None
    except Exception as e:
        print(f"[ERREUR] Erreur lors du chargement de la session : {e}")
        return None


def save_session(session_data: Dict[str, Any], session_file: str) -> bool:
    """
    Sauvegarde une session dans un fichier JSON.
    
    Args:
        session_data: Données de session à sauvegarder
        session_file: Chemin du fichier de session
    
    Returns:
        True si succès, False sinon
    """
    try:
        # ✅ NOUVEAU : Vérifier que global_styles est présent avant sauvegarde
        if "global_styles" not in session_data:
            print("[AVERTISSEMENT] global_styles manquant, initialisation par défaut")
            session_data["global_styles"] = {
                "styles": {},
                "block_style_refs": {}
            }
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        # ✅ NOUVEAU : Afficher le nombre de styles sauvegardés
        num_styles = len(session_data["global_styles"]["styles"])
        print(f"[OK] Session sauvegardée : {session_file} ({num_styles} styles globaux)")
        return True
    
    except Exception as e:
        print(f"[ERREUR] Impossible de sauvegarder la session : {e}")
        return False


def load_or_create_session(basename: str, pdf_path: str = None, enriched_data: list = None, page_dimensions: Dict = None) -> Dict[str, Any]:
    """
    Charge une session existante ou en crée une nouvelle.
    
    Args:
        basename: Nom de base du projet
        pdf_path: Chemin du PDF (requis si création)
        enriched_data: Données enrichies (requis si création)
        page_dimensions: Dimensions des pages (requis si création)
    
    Returns:
        Données de session
    """
    session_file = f"{basename}_session.json"
    
    # Tenter de charger une session existante
    session_data = load_session(session_file)
    
    if session_data is None:
        # Créer une nouvelle session
        if pdf_path is None or enriched_data is None or page_dimensions is None:
            raise ValueError("pdf_path, enriched_data et page_dimensions sont requis pour créer une nouvelle session")
        
        print(f"[INFO] Création d'une nouvelle session : {session_file}")
        session_data = create_new_session(basename, pdf_path, enriched_data, page_dimensions)
        save_session(session_data, session_file)
    
    return session_data
