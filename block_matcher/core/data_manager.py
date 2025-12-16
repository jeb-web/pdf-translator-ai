#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire de données pour les blocs et spans
"""

from typing import List, Dict, Any, Optional


class DataManager:
    """Gestion centralisée des données de blocs et spans"""
    
    def __init__(self, enriched_data: List[List[Dict[str, Any]]]):
        """
        Initialiser le gestionnaire de données
        
        Args:
            enriched_data: Données enrichies par page
        """
        # self.enriched_data = enriched_data
        # self.current_page = 0
        self.enriched_data = enriched_data if enriched_data is not None else []
        self.page_dimensions = {}
        self.current_page = 0
       

        
    def get_page_blocks(self, page_num: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Récupérer les blocs d'une page
        
        Args:
            page_num: Numéro de page (None = page actuelle)
            
        Returns:
            Liste des blocs de la page
        """
        if page_num is None:
            page_num = self.current_page
        
        if 0 <= page_num < len(self.enriched_data):
            return self.enriched_data[page_num]
        return []
    
    def get_mineru_blocks(self, page_num: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Récupérer uniquement les blocs MinerU (pas les isolated_span)
        
        Args:
            page_num: Numéro de page
            
        Returns:
            Liste des blocs MinerU
        """
        page_blocks = self.get_page_blocks(page_num)
        return [
            b for b in page_blocks 
            if b.get('block_type') and b.get('block_type') != 'isolated_span'
        ]
    
    def get_all_spans(self, page_num: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Récupérer tous les spans d'une page
        
        Args:
            page_num: Numéro de page
            
        Returns:
            Liste de tous les spans (triés par position)
        """
        page_blocks = self.get_page_blocks(page_num)
        all_spans = []
        
        for block in page_blocks:
            all_spans.extend(block.get('matching_spans', []))
        
        # Trier par position (haut en bas, gauche à droite)
        all_spans.sort(key=lambda s: (s['bbox_pixels'][1], s['bbox_pixels'][0]))
        
        return all_spans
    
    def get_unmatched_spans(self, page_num: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Récupérer les spans non matchés
        
        Args:
            page_num: Numéro de page
            
        Returns:
            Liste des spans sans correspondance
        """
        all_spans = self.get_all_spans(page_num)
        return [s for s in all_spans if s.get('matched_to_block') is None]
    
    def link_spans_to_block(self, block: Dict[str, Any], spans: List[Dict[str, Any]]) -> None:
        """
        Lier des spans à un bloc
        
        Args:
            block: Bloc cible
            spans: Liste des spans à lier
        """
        # Créer copie des spans pour éviter références
        new_spans = [span.copy() for span in spans]
        
        # Mettre à jour le bloc
        block['matching_spans'] = new_spans
        block['match_source'] = 'manual'
        
        # Marquer les spans comme matchés
        for span in new_spans:
            span['matched_to_block'] = block['id']
    
    def unlink_block(self, block: Dict[str, Any]) -> None:
        """
        Délier un bloc de ses spans
        
        Args:
            block: Bloc à délier
        """
        # Démarquer les spans
        for span in block.get('matching_spans', []):
            span['matched_to_block'] = None
        
        # Vider le bloc
        block['matching_spans'] = []
        block['match_source'] = 'unmatched'
    
    def get_statistics(self, page_num: Optional[int] = None) -> Dict[str, int]:
        """
        Calculer les statistiques de matching
        
        Args:
            page_num: Numéro de page (None = toutes les pages)
            
        Returns:
            Dict avec total, matched, manual
        """
        if page_num is not None:
            blocks = self.get_mineru_blocks(page_num)
        else:
            blocks = []
            for i in range(len(self.enriched_data)):
                blocks.extend(self.get_mineru_blocks(i))
        
        total = len(blocks)
        matched = len([b for b in blocks if b.get('matching_spans')])
        manual = len([b for b in blocks if b.get('match_source') == 'manual'])
        
        return {
            'total': total,
            'matched': matched,
            'manual': manual,
            'unmatched': total - matched
        }
    
    def find_block_by_id(self, block_id: str, page_num: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Trouver un bloc par son ID
        
        Args:
            block_id: ID du bloc recherché
            page_num: Numéro de page (None = page actuelle)
            
        Returns:
            Bloc trouvé ou None
        """
        page_blocks = self.get_page_blocks(page_num)
        for block in page_blocks:
            if block.get('id') == block_id:
                return block
        return None
        
    def merge_blocks(self, block_ids: List[str]) -> str:
        """Fusionner plusieurs blocs en un groupe"""
        if len(block_ids) < 2:
            raise ValueError("Au moins 2 blocs requis pour fusionner")
        
        import time
        merge_group_id = f"MERGE_{int(time.time() * 1000) % 1000000}"
        
        print(f"\n=== MERGE_BLOCKS DEBUG ===")
        print(f"Block IDs to merge: {block_ids}")
        print(f"Merge group ID: {merge_group_id}")
        print(f"enriched_data type: {type(self.enriched_data)}")
        print(f"enriched_data length: {len(self.enriched_data)}")
        
        matched_count = 0
        for page_idx, page_blocks in enumerate(self.enriched_data):
            print(f"\nPage {page_idx}: type={type(page_blocks)}, len={len(page_blocks) if isinstance(page_blocks, list) else 'N/A'}")
            
            if isinstance(page_blocks, list):
                for block_idx, block in enumerate(page_blocks):
                    if isinstance(block, dict):
                        block_id = block.get("id")
                        if block_id in block_ids:
                            print(f"  ✓ Found block {block_id} at index {block_idx}")
                            block["merge_group_id"] = merge_group_id
                            block["merge_order"] = block_ids.index(block_id)
                            matched_count += 1
                            print(f"    → merge_group_id set to {merge_group_id}")
                            print(f"    → merge_order set to {block_ids.index(block_id)}")
        
        print(f"\nTotal matched: {matched_count}/{len(block_ids)}")
        print(f"=== END MERGE_BLOCKS DEBUG ===\n")
        
        return merge_group_id



    def unmerge_blocks(self, block_ids: List[str]) -> None:
        """
        Défusionner un groupe de blocs
        
        Args:
            block_ids: Liste des IDs de blocs à défusionner
        """
        # ✅ CORRECTION : enriched_data est une liste de LISTES
        for page_blocks in self.enriched_data:  # ← page_blocks est une LISTE
            if isinstance(page_blocks, list):
                for block in page_blocks:
                    if isinstance(block, dict) and block.get("id") in block_ids:
                        block.pop("merge_group_id", None)
                        block.pop("merge_order", None)


    def get_merged_blocks_groups(self) -> Dict[str, List[dict]]:
        """
        Retourner tous les groupes de blocs fusionnés
        
        Returns:
            Dict: {merge_group_id: [block1, block2, ...]}
        """
        groups = {}
        # ✅ CORRECTION : enriched_data est une liste de LISTES
        for page_blocks in self.enriched_data:  # ← page_blocks est une LISTE
            if isinstance(page_blocks, list):
                for block in page_blocks:
                    if isinstance(block, dict) and "merge_group_id" in block:
                        gid = block["merge_group_id"]
                        if gid not in groups:
                            groups[gid] = []
                        groups[gid].append(block)
        
        # Trier chaque groupe par merge_order
        for gid in groups:
            groups[gid].sort(key=lambda b: b.get("merge_order", 0))
        
        return groups

    def export_merged_groups_for_translation(self):
        """
        Exporter les groupes fusionnés pour traduction
        
        Returns:
            Dict avec structure: {merge_group_id: {"text": "...", "block_ids": [...]}}
        """
        export_data = {}
        
        for page_blocks in self.enriched_data:
            for block in page_blocks:
                if "merge_group_id" in block:
                    group_id = block["merge_group_id"]
                    
                    # Créer l'entrée si elle n'existe pas
                    if group_id not in export_data:
                        export_data[group_id] = {
                            "text": "",
                            "block_ids": [],
                            "texts_by_order": {}
                        }
                    
                    # Ajouter le bloc à la liste
                    export_data[group_id]["block_ids"].append(block.get("id"))
                    
                    # Récupérer le texte avec l'ordre de fusion
                    merge_order = block.get("merge_order", 0)
                    text = block.get("text", "")
                    export_data[group_id]["texts_by_order"][merge_order] = text
        
        # Combiner les textes dans l'ordre merge_order
        for group_id, data in export_data.items():
            texts_ordered = [
                data["texts_by_order"][i] 
                for i in sorted(data["texts_by_order"].keys())
            ]
            data["text"] = "\n".join(texts_ordered)  # Joindre avec newline
        
        return export_data

