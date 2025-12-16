#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestion des métadonnées de validation
"""

import json
import os
from collections import Counter
from typing import List, Dict, Any


def save_validation_metadata(base_name: str, enriched_data: List[List[Dict[str, Any]]]) -> str:
    """
    Sauvegarder les métadonnées de validation
    
    Args:
        base_name: Nom de base du projet
        enriched_data: Données enrichies
        
    Returns:
        Chemin du fichier de métadonnées créé
    """
    metadata_file = f'{base_name}_validation_metadata.json'
    metadata = {'pages': []}
    
    total_blocks = 0
    manual_blocks = 0
    preserved_blocks = 0
    isolated_included = 0
    
    for page_num, page_blocks in enumerate(enriched_data):
        page_metadata = {
            'page_number': page_num + 1,
            'blocks': []
        }
        
        for block in page_blocks:
            # Blocs MinerU normaux
            if block.get('block_type') and block.get('block_type') != 'isolated_span':
                total_blocks += 1
                match_source = block.get('match_source', 'auto')
                preserve_empty = block.get('preserve_empty', False)
                
                if match_source == 'manual':
                    manual_blocks += 1
                if preserve_empty:
                    preserved_blocks += 1
                
                block_metadata = {
                    'id': block['id'],
                    'match_source': match_source,
                    'preserve_empty': preserve_empty,
                    'spans_count': len(block.get('matching_spans', [])),
                    'span_ids': [s['id'] for s in block.get('matching_spans', [])]
                }
                page_metadata['blocks'].append(block_metadata)
            
            # Isolated spans
            elif block.get('block_type') == 'isolated_span':
                include = block.get('include_in_output', True)
                if include:
                    isolated_included += 1
                
                block_metadata = {
                    'id': block['id'],
                    'block_type': 'isolated_span',
                    'include_in_output': include,
                    'span_ids': [s['id'] for s in block.get('matching_spans', [])]
                }
                page_metadata['blocks'].append(block_metadata)
        
        metadata['pages'].append(page_metadata)
    
    # Sauvegarder
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Métadonnées sauvegardées: {metadata_file}")
    print(f"   - {total_blocks} blocs MinerU")
    print(f"   - {manual_blocks} blocs manuels")
    print(f"   - {preserved_blocks} blocs vides conservés")
    print(f"   - {isolated_included} isolated spans inclus")
    
    return metadata_file


def load_validation_metadata(base_name: str, enriched_data: List[List[Dict[str, Any]]]) -> List[List[Dict[str, Any]]]:
    """
    Charger les métadonnées de validation
    
    Args:
        base_name: Nom de base du projet
        enriched_data: Données enrichies
        
    Returns:
        Données enrichies avec métadonnées appliquées
    """
    metadata_file = f'{base_name}_validation_metadata.json'
    
    if not os.path.exists(metadata_file):
        return enriched_data
    
    print(f"\n📂 Métadonnées trouvées: {metadata_file}")
    
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Collecter les spans PAR PAGE
        spans_by_page = {}
        for page_num, page_blocks in enumerate(enriched_data):
            spans_by_page[page_num] = {}
            for block in page_blocks:
                for span in block.get('matching_spans', []):
                    if span['id'] not in spans_by_page[page_num]:
                        spans_by_page[page_num][span['id']] = span
        
        # Réinitialiser les matching_spans
        for page_num, page_blocks in enumerate(enriched_data):
            for block in page_blocks:
                if block.get('block_type') != 'isolated_span':
                    block['matching_spans'] = []
        
        # Reconstruire selon métadonnées
        total_manual = 0
        total_preserved = 0
        total_isolated_included = 0
        spans_assigned_by_page = {p: set() for p in spans_by_page.keys()}
        
        for page_num, page_blocks in enumerate(enriched_data):
            if page_num >= len(metadata['pages']):
                break
            
            page_metadata = metadata['pages'][page_num]
            metadata_by_id = {b['id']: b for b in page_metadata['blocks']}
            page_spans = spans_by_page.get(page_num, {})
            
            for block in page_blocks:
                block_id = block.get('id')
                if block_id in metadata_by_id:
                    block_meta = metadata_by_id[block_id]
                    
                    # Isolated span
                    if block_meta.get('block_type') == 'isolated_span':
                        block['include_in_output'] = block_meta.get('include_in_output', True)
                        if block['include_in_output']:
                            total_isolated_included += 1
                        continue
                    
                    # Bloc normal
                    block['match_source'] = block_meta.get('match_source', 'auto')
                    if block['match_source'] == 'manual':
                        total_manual += 1
                    
                    block['preserve_empty'] = block_meta.get('preserve_empty', False)
                    if block['preserve_empty']:
                        total_preserved += 1
                    
                    # Reconstruire spans
                    if 'span_ids' in block_meta:
                        for span_id in block_meta['span_ids']:
                            if span_id in page_spans:
                                span = page_spans[span_id]
                                span['matched_to_block'] = block_id
                                block['matching_spans'].append(span)
                                spans_assigned_by_page[page_num].add(span_id)
        
        # Créer isolated_spans pour spans non assignés
        total_unassigned = 0
        for page_num, page_spans in spans_by_page.items():
            assigned = spans_assigned_by_page.get(page_num, set())
            unassigned = set(page_spans.keys()) - assigned
            
            if unassigned:
                total_unassigned += len(unassigned)
                existing_ids = {
                    b['id'] for b in enriched_data[page_num] 
                    if b.get('block_type') == 'isolated_span'
                }
                
                for span_id in unassigned:
                    span = page_spans[span_id]
                    span['matched_to_block'] = None
                    
                    iso_id = f"page{page_num+1}_isolated_pymupdf_{span_id}"
                    if iso_id in existing_ids:
                        print(f"   ⚠️ Skip doublon: {iso_id}")
                        continue
                    
                    isolated_block = {
                        'id': iso_id,
                        'content': span['text'],
                        'styled_content': span['text'],
                        'block_type': 'isolated_span',
                        'position_xy': [span['bbox_pixels'][0], span['bbox_pixels'][1]],
                        'max_allowable_width': span['bbox_pixels'][2] - span['bbox_pixels'][0],
                        'default_style': {
                            "police": span['font_name'],
                            "taille": span['font_size'],
                            "couleur": span.get('color_rgb', [0, 0, 0])
                        },
                        'additional_styles': {},
                        'matching_spans': [span],
                        'source': 'metadata_unassigned',
                        'include_in_output': True
                    }
                    enriched_data[page_num].append(isolated_block)
                    existing_ids.add(iso_id)
        
        print(f"✅ Métadonnées appliquées:")
        print(f"   - {total_manual} blocs manuels")
        print(f"   - {total_preserved} blocs vides conservés")
        print(f"   - {total_isolated_included} isolated spans inclus")
        print(f"   - {total_unassigned} spans non assignés")
        
        # Diagnostic isolated_spans
        print(f"\n📊 Diagnostic isolated_spans:")
        for page_num, page_blocks in enumerate(enriched_data):
            isolated = [b for b in page_blocks if b.get('block_type') == 'isolated_span']
            isolated_ids = [b['id'] for b in isolated]
            
            if len(isolated_ids) != len(set(isolated_ids)):
                print(f"   ⚠️ Page {page_num+1}: DOUBLONS détectés!")
                counts = Counter(isolated_ids)
                for block_id, count in counts.items():
                    if count > 1:
                        print(f"      - {block_id}: {count} fois")
            else:
                print(f"   ✅ Page {page_num+1}: {len(isolated)} isolated_spans")
        
        return enriched_data
    
    except Exception as e:
        print(f"❌ Erreur métadonnées: {e}")
        import traceback
        traceback.print_exc()
        return enriched_data
