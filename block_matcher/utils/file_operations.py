#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Opérations de lecture/écriture de fichiers
"""

import json
import os
import fitz  # PyMuPDF
from typing import List, Dict, Any, Tuple


def save_corrected_files(
    enriched_data: List[List[Dict[str, Any]]], 
    pdf_path: str, 
    base_name: str
) -> Tuple[str, str, str]:  # ← Changé: 3 valeurs au lieu de 2
    """
    Sauvegarder les fichiers JSON corrigés ET le template PDF sans texte
    
    Args:
        enriched_data: Données enrichies corrigées
        pdf_path: Chemin vers le PDF
        base_name: Nom de base des fichiers
        
    Returns:
        (translation_file, formatting_file, template_file)
        
    Raises:
        Exception: Si erreur lors de la sauvegarde
    """
    try:
        from ..core.extract import DualOutputGenerator
    except ImportError:
        raise ImportError(
            "Module 'extract' introuvable. "
            "Assurez-vous que extract.py est dans le même répertoire."
        )
    
    # Créer le générateur
    generator = DualOutputGenerator()
    generator.page_dimensions = {}
    
    # Recalculer les dimensions de page
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        generator.page_dimensions[page_num] = [page.rect.width, page.rect.height]
    doc.close()
    
    # Régénérer les outputs
    translation_data = generator._generate_translation_format(enriched_data)
    formatting_data = generator._generate_formatting_format(enriched_data)
    
    # Définir les noms de fichiers
    translation_file = f'{base_name}_pour_traduction_corrected.json'
    formatting_file = f'{base_name}_formatage_corrected.json'
    template_file = f'{base_name}_template_corrected.pdf'  # ← NOUVEAU
    
    # Sauvegarder les fichiers JSON
    with open(translation_file, 'w', encoding='utf-8') as f:
        json.dump(translation_data, f, indent=2, ensure_ascii=False)
    
    with open(formatting_file, 'w', encoding='utf-8') as f:
        json.dump(formatting_data, f, indent=2, ensure_ascii=False)
    
    # ← NOUVEAU: Créer le template PDF sans texte
    generator.create_clean_template(pdf_path, template_file)
    
    return translation_file, formatting_file, template_file  # ← MODIFIÉ




def load_enriched_data(pdf_path: str, mineru_json_path: str) -> List[List[Dict[str, Any]]]:
    """
    Charger et enrichir les données depuis les fichiers sources
    
    Args:
        pdf_path: Chemin vers le PDF
        mineru_json_path: Chemin vers le JSON MinerU
        
    Returns:
        Données enrichies par page
        
    Raises:
        FileNotFoundError: Si un fichier est introuvable
        Exception: Si erreur lors du chargement
    """
    # Vérifier l'existence des fichiers
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF introuvable: {pdf_path}")
    
    if not os.path.exists(mineru_json_path):
        raise FileNotFoundError(f"JSON MinerU introuvable: {mineru_json_path}")
    
    # Importer le générateur
    try:
        from ..core.extract import DualOutputGenerator
    except ImportError:
        raise ImportError(
            "Module 'extract' introuvable. "
            "Assurez-vous que extract.py est dans le même répertoire."
        )
    
    # Charger et traiter les données
    generator = DualOutputGenerator()
    mineru_data = generator._load_mineru_data(mineru_json_path)
    enriched_data = generator._process_with_visual_matching(pdf_path, mineru_data)
    
    return enriched_data


def export_statistics(enriched_data: List[List[Dict[str, Any]]], output_path: str) -> None:
    """
    Exporter des statistiques détaillées en JSON
    
    Args:
        enriched_data: Données enrichies
        output_path: Chemin du fichier de sortie
    """
    stats = {
        'total_pages': len(enriched_data),
        'pages': []
    }
    
    for page_num, page_blocks in enumerate(enriched_data):
        mineru_blocks = [
            b for b in page_blocks 
            if b.get('block_type') and b.get('block_type') != 'isolated_span'
        ]
        
        page_stats = {
            'page': page_num + 1,
            'total_blocks': len(mineru_blocks),
            'matched_blocks': len([b for b in mineru_blocks if b.get('matching_spans')]),
            'manual_blocks': len([b for b in mineru_blocks if b.get('match_source') == 'manual']),
            'auto_blocks': len([
                b for b in mineru_blocks 
                if b.get('matching_spans') and b.get('match_source') != 'manual'
            ]),
            'unmatched_blocks': len([b for b in mineru_blocks if not b.get('matching_spans')]),
        }
        
        stats['pages'].append(page_stats)
    
    # Calculer totaux
    stats['totals'] = {
        'total_blocks': sum(p['total_blocks'] for p in stats['pages']),
        'matched_blocks': sum(p['matched_blocks'] for p in stats['pages']),
        'manual_blocks': sum(p['manual_blocks'] for p in stats['pages']),
        'auto_blocks': sum(p['auto_blocks'] for p in stats['pages']),
        'unmatched_blocks': sum(p['unmatched_blocks'] for p in stats['pages']),
    }
    
    # Sauvegarder
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def backup_file(file_path: str) -> str:
    """
    Créer une copie de sauvegarde d'un fichier
    
    Args:
        file_path: Chemin du fichier à sauvegarder
        
    Returns:
        Chemin du fichier de backup
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Fichier introuvable: {file_path}")
    
    # Trouver un nom de backup disponible
    backup_path = f"{file_path}.backup"
    counter = 1
    
    while os.path.exists(backup_path):
        backup_path = f"{file_path}.backup{counter}"
        counter += 1
    
    # Copier le fichier
    with open(file_path, 'r', encoding='utf-8') as source:
        content = source.read()
    
    with open(backup_path, 'w', encoding='utf-8') as dest:
        dest.write(content)
    
    return backup_path
