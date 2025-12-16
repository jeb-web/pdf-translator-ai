#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur final pour produire les deux fichiers de sortie exacts:
- Fichier pour traduction (simple avec balises de style)
- Fichier de formatage (complet avec métadonnées de mise en page)
Usage: python generate_dual_output.py <PDF_FILE> <MINERU_JSON> [base_name]
"""

import fitz  # PyMuPDF
import json
import os
import sys
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import re

class DualOutputGenerator:
    """Générateur pour les deux formats de sortie"""
    
    def __init__(self, enriched_data: List[List[Dict]] = None, page_dimensions: Dict = None, global_styles_data: Dict = None, translation_overrides: Dict = None):
        """
        Initialise le générateur.
        :param translation_overrides: Dict {block_id: "xml_content"} contenant les corrections manuelles.
        """
        self.bbox_tolerance = 0.02
        self.page_dimensions = page_dimensions or {}
        self.style_counters = {}
        self.enriched_data = enriched_data
        
        # --- NOUVEAU : Stockage des overrides ---
        self.translation_overrides = translation_overrides or {}
        
        # ✅ MODIFICATION : Initialiser seulement si global_styles_data a du contenu
        if global_styles_data is not None and isinstance(global_styles_data, dict):
            loaded_styles = global_styles_data.get('styles', {})
            loaded_refs = global_styles_data.get('block_style_refs', {})
            
            # Charger seulement si les données ne sont pas vides
            if loaded_styles or loaded_refs:
                self.global_styles = loaded_styles
                self.block_additional_style_refs = loaded_refs
                
                # Reconstruire style_mapping
                self.style_mapping = {}
                for gs_key, style_dict in self.global_styles.items():
                    style_signature = (
                        style_dict.get('police', ''),
                        style_dict.get('taille', 0),
                        style_dict.get('couleur', 0)
                    )
                    self.style_mapping[style_signature] = gs_key
                
                print(f"[INFO] DualOutputGenerator initialisé avec {len(self.global_styles)} styles globaux existants")
            else:
                self.global_styles = {}
                self.style_mapping = {}
                self.block_additional_style_refs = {}
                print("[INFO] DualOutputGenerator initialisé avec styles globaux vides")
        else:
            self.global_styles = {}
            self.style_mapping = {}
            self.block_additional_style_refs = {}
            print("[INFO] DualOutputGenerator initialisé avec styles globaux vides")
        
        self.diagnostic_colors = {
            'mineru_block': (0, 0.8, 0),
            'pymupdf_matched': (0, 0, 1),
            'pymupdf_isolated': (1, 0, 0),
            'mineru_empty': (1, 0.5, 0),
            'text_info': (0, 0, 0),
            'background': (1, 1, 0.9),
        }



    def update_empty_block_style_from_first_span(self, block):
        """MET À JOUR default_style UNIQUEMENT si BLOC ÉTAIT VIDE et qu'on ajoute PREMIER span."""
        matching_spans = block.get('matching_spans', [])
        
        # UNIQUEMENT si le bloc était vide (0 span avant) et maintenant 1+ span
        if matching_spans and block.get('default_style', {}).get('police') == 'Unknown':
            first_span = next((s for s in matching_spans if s.get('font_name') and s.get('font_name') != 'Unknown'), matching_spans[0])
            block['default_style'] = {
                'police': first_span.get('font_name'),
                'taille': first_span.get('font_size', 12.0),
                'couleur': first_span.get('color_rgb', 0)
            }


    def get_document_default_style(self):
        """Style global fixe pour blocs sans spans."""
        return {'police': 'Helvetica', 'taille': 12.0, 'couleur': 0}



    def _calculate_average_line_spacing(self, matching_spans: List, default_style: Dict) -> float:
        """
        Calcule l'interligne moyen pour un bloc en se basant sur la position verticale des spans.
        """
        # Si pas assez d'informations, retourner une valeur par défaut basée sur la taille de la police.
        if not matching_spans or len(matching_spans) < 2:
            return round(default_style.get('taille', 12.0) * 1.2, 2)

        # Étape 1: Regrouper les spans en lignes en se basant sur leur coordonnée Y supérieure (y0)
        y_tolerance = 2.0  # Tolérance en pixels pour considérer que les spans sont sur la même ligne
        lines = defaultdict(list)
        for span in matching_spans:
            y0 = span['bbox_pixels'][1]
            found_line = False
            # Chercher une ligne existante dans la tolérance
            for line_y in lines.keys():
                if abs(y0 - line_y) < y_tolerance:
                    lines[line_y].append(span)
                    found_line = True
                    break
            if not found_line:
                lines[y0].append(span)

        # S'il n'y a qu'une seule ligne détectée, on ne peut pas calculer d'interligne.
        if len(lines) < 2:
            return round(default_style.get('taille', 12.0) * 1.2, 2)

        # Étape 2: Trier les coordonnées Y des lignes
        sorted_line_y_coords = sorted(lines.keys())

        # Étape 3: Calculer les distances entre les débuts de lignes consécutives
        distances = []
        font_size = default_style.get('taille', 12.0)
        for i in range(len(sorted_line_y_coords) - 1):
            distance = sorted_line_y_coords[i+1] - sorted_line_y_coords[i]
            # Filtre pour éviter les grands écarts (ex: entre deux paragraphes)
            if distance > 0 and distance < (font_size * 3):
                distances.append(distance)

        # Étape 4: Calculer la moyenne
        if not distances:
            return round(font_size * 1.2, 2) # Fallback si aucun écart valide n'est trouvé

        average_spacing = sum(distances) / len(distances)
        return round(average_spacing, 2)

    def generate_dual_outputs(self, pdf_path: str, mineru_json_path: str = None, base_name: str = None):
        """Générer les deux fichiers de sortie"""

        if base_name is None:
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]

        translation_file = f"{base_name}_pour_traduction.json"
        formatting_file = f"{base_name}_formatage.json"

        print("🎯 GÉNÉRATION DES DEUX FORMATS DE SORTIE")
        print("=" * 60)
        print(f"PDF source: {pdf_path}")
        print(f"MinerU JSON: {mineru_json_path}")
        print(f"Sortie traduction: {translation_file}")
        print(f"Sortie formatage: {formatting_file}")

        # 1. Charger et analyser les données
        if self.enriched_data is None:
            mineru_data = self._load_mineru_data(mineru_json_path)
            self.enriched_data = self._process_with_visual_matching(pdf_path, mineru_data)

        # 2. Générer les deux formats
        # ✅ MODIFICATION : Inverser l'ordre - formatage EN PREMIER
        formatting_data = self._generate_formatting_format(self.enriched_data)
        translation_data = self._generate_translation_format(self.enriched_data)

        # 3. Sauvegarder
        with open(translation_file, 'w', encoding='utf-8') as f:
            json.dump(translation_data, f, indent=2, ensure_ascii=False)

        with open(formatting_file, 'w', encoding='utf-8') as f:
            json.dump(formatting_data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Fichiers JSON générés:")
        print(f"📝 {translation_file}")
        print(f"🎨 {formatting_file}")

        # Créer le template PDF sans texte
        template_file = f"{base_name}_template.pdf"
        self.create_clean_template(pdf_path, template_file, self.enriched_data)

        print(f"\n✅ Tous les fichiers générés:")
        print(f"📝 {translation_file}")
        print(f"🎨 {formatting_file}")
        print(f"🖼️  {template_file}")

        return translation_file, formatting_file, template_file


    def _load_mineru_data(self, json_path: str):
        """Charger MinerU"""
        print("\n📖 Chargement MinerU...")

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"✅ {len(data)} pages chargées")
            return data
        except Exception as e:
            print(f"❌ Erreur: {e}")
            raise

    def _process_with_visual_matching(self, pdf_path: str, mineru_data: List):
        """Traiter avec matching visuel robuste"""
        print("\n🔗 Matching visuel et enrichissement...")

        doc = fitz.open(pdf_path)
        enriched_data = []

        for page_num in range(len(doc)):
            if page_num >= len(mineru_data):
                break
            print(f"  Page {page_num}...")

            page = doc.load_page(page_num)
            page_rect = page.rect

            # Stocker les dimensions de page
            self.page_dimensions[page_num] = [page_rect.width, page_rect.height]

            # Extraire spans PyMuPDF
            pymupdf_spans = self._extract_pymupdf_spans_detailed(page, page_rect)

            # Traiter les blocs MinerU de cette page
            page_data = mineru_data[page_num]
            enriched_page = self._enrich_page_blocks(page_data, pymupdf_spans, page_num)

            enriched_data.append(enriched_page)

        doc.close()
        return enriched_data

    def _extract_pymupdf_spans_detailed(self, page, page_rect):
        """Extraire spans PyMuPDF avec détails complets"""

        text_dict = page.get_text("dict")
        spans = []
        span_id = 0

        for block_idx, block in enumerate(text_dict["blocks"]):
            if "lines" in block:
                for line_idx, line in enumerate(block["lines"]):
                    for span_idx, span in enumerate(line["spans"]):
                        if span["text"].strip():
                            # Coordonnées normalisées ET pixels
                            bbox_norm = [
                                span["bbox"][0] / page_rect.width,
                                span["bbox"][1] / page_rect.height,
                                span["bbox"][2] / page_rect.width,
                                span["bbox"][3] / page_rect.height
                            ]

                            span_info = {
                                'id': span_id,
                                'text': span["text"],
                                'bbox_pixels': span["bbox"],
                                'bbox_normalized': bbox_norm,
                                'font_name': span["font"],
                                'font_size': round(span["size"], 2),
                                'color_rgb': span["color"],
                                'color_hex': f"#{span['color']:06x}",
                                'flags': span["flags"],
                                'is_bold': bool(span["flags"] & 2**4),
                                'is_italic': bool(span["flags"] & 2**1),
                                'is_superscript': bool(span["flags"] & 2**0),
                                'matched_to_block': None,
                                'match_quality': 'unmatched'
                            }
                            spans.append(span_info)
                            span_id += 1

        return spans

    # --- DÉBUT DE LA CORRECTION ---
    def _convert_poly_to_bbox(self, poly: List[float]) -> List[float]:
        """Convertit un polygone [x1, y1, x2, y2, ...] en bbox [x0, y0, x1, y1]."""
        x_coords = poly[0::2]
        y_coords = poly[1::2]
        return [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]

    def _enrich_page_blocks(self, page_data, pymupdf_spans: List, page_num: int):
        """
        Enrichir les blocs d'une page avec matching PyMuPDF
        Adapté pour le nouveau format MinerU où page_data est directement une liste
        """
        
        # Le nouveau format: page_data est directement une liste de blocs
        standardized_blocks = []
        
        # Convertir les blocs MinerU au format attendu
        for block in page_data:
            if isinstance(block, dict):
                block_type = block.get('type')
                
                # Ne traiter que les blocs de texte (title, text)
                if block_type in ['title', 'text']:
                    bbox = block.get('bbox')
                    content = block.get('content', '')
                    
                    if bbox and len(bbox) == 4:
                        standardized_blocks.append({
                            'type': block_type,
                            'content': content,
                            'bbox': bbox,  # Déjà normalisé (0-1)
                            'original_block': block
                        })
        
        # Trier par position (haut vers bas, gauche vers droite)
        standardized_blocks.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))
        
        # Enrichir avec matching PyMuPDF
        enriched_blocks = []
        group_counter = 0
        bloc_counter = 0
        self.style_counters[page_num] = {}
        
        # Traiter chaque bloc MinerU
        for block_idx, block in enumerate(standardized_blocks):
            if block.get('type') in ['text', 'title']:
                matching_spans = self._find_matching_spans_for_block(
                    block, pymupdf_spans, page_num
                )
                
                enriched_block = self._create_enriched_block(
                    block, matching_spans, page_num, group_counter, bloc_counter
                )
                self.update_empty_block_style_from_first_span(enriched_block)
                enriched_blocks.append(enriched_block)
                bloc_counter += 1
                
                # Marquer les spans comme utilisés
                for span in matching_spans:
                    span['matched_to_block'] = block_idx
        
        # Ajouter les spans isolés
        isolated_spans = [s for s in pymupdf_spans if s['matched_to_block'] is None]
        
        for span in isolated_spans:
            isolated_block = self._create_isolated_span_block(
                span, page_num, group_counter, bloc_counter
            )
            enriched_blocks.append(isolated_block)
            bloc_counter += 1
        
        return enriched_blocks



    def _find_matching_spans_for_block(self, block: Dict, pymupdf_spans: List, page_num: int):
        """Trouver les spans PyMuPDF correspondant à un bloc MinerU."""

        block_bbox = block['bbox']
        block_content = block.get('content', '').lower()
        matching_spans = []

        # 1. Sélection initiale par chevauchement de bbox + score texte
        for span in pymupdf_spans:
            if span['matched_to_block'] is not None:
                continue

            if self._spans_overlap(span['bbox_normalized'], block_bbox):
                if not block_content.strip():
                    text_match_score = 1.0
                else:
                    text_match_score = self._evaluate_text_match(span['text'], block_content)

                if text_match_score > 0:
                    span['text_match_score'] = text_match_score
                    span['match_quality'] = self._get_match_quality_label(text_match_score)
                    matching_spans.append(span)

        if not matching_spans:
            return []

        # 2. Regrouper les spans par lignes (tolérance verticale) puis trier par X

        y_tolerance = 1.0  # en pixels
        lines = defaultdict(list)

        for span in matching_spans:
            y_span = span['bbox_pixels'][1]
            line_y = None
            for existing_y in lines.keys():
                if abs(y_span - existing_y) <= y_tolerance:
                    line_y = existing_y
                    break
            if line_y is None:
                line_y = y_span
            lines[line_y].append(span)

        sorted_spans = []
        for y in sorted(lines.keys()):
            line_spans = sorted(lines[y], key=lambda s: s['bbox_pixels'][0])
            sorted_spans.extend(line_spans)

        return sorted_spans


    def _spans_overlap(self, span_bbox: List, block_bbox: List) -> bool:
        """Test de chevauchement avec tolérance"""

        tolerance = self.bbox_tolerance

        return (span_bbox[0] >= block_bbox[0] - tolerance and
                span_bbox[1] >= block_bbox[1] - tolerance and
                span_bbox[2] <= block_bbox[2] + tolerance and
                span_bbox[3] <= block_bbox[3] + tolerance)

    def _evaluate_text_match(self, span_text: str, block_content: str) -> float:
        """Évaluer la correspondance textuelle"""

        span_text = span_text.strip().lower()

        if not block_content.strip(): # Si pas de contenu à matcher, overlap suffit
            return 1.0

        if span_text in block_content:
            return 1.0

        # Correspondance par mots
        span_words = set(word for word in span_text.split() if len(word) >= 2)
        block_words = set(word for word in block_content.split() if len(word) >= 2)

        if span_words and block_words:
            common_words = span_words & block_words
            return len(common_words) / len(span_words)

        return 0.0

    def _get_match_quality_label(self, quality: float) -> str:
        """Convertir score en label"""
        if quality >= 0.9: return 'excellent'
        elif quality >= 0.7: return 'good'
        elif quality >= 0.4: return 'fair'
        else: return 'poor'

    def _create_enriched_block(self, mineru_block: Dict, matching_spans: List, page_num: int, group_num: int, bloc_num: int):
        block_id = f"page{page_num+1}_group{group_num}_bloc{bloc_num:02d}"
        mineru_content = mineru_block.get('content', '')
        
        if matching_spans:
            content = " ".join([s['text'] for s in matching_spans if s.get('text')])
        else:
            content = mineru_content
        
        block_type = self._determine_block_type(content, mineru_block)
        
        page_dims = self.page_dimensions[page_num]
        position_xy = [
            mineru_block['bbox'][0] * page_dims[0],
            mineru_block['bbox'][1] * page_dims[1]
        ]
        max_width = (mineru_block['bbox'][2] - mineru_block['bbox'][0]) * page_dims[0]
        
        styled_content, additional_styles = self._create_styled_content(content, matching_spans, page_num)
        
        # DEFAULT_STYLE = PREMIER SPAN ou Unknown (sera corrigé après)
        if matching_spans and matching_spans[0].get('font_name'):
            first_span = matching_spans[0]
            default_style = {
                'police': first_span.get('font_name'),
                'taille': first_span.get('font_size', 12.0),
                'couleur': first_span.get('color_rgb', 0)
            }
        else:
            default_style = {'police': 'Unknown', 'taille': 12.0, 'couleur': 0}
        
        enriched_block = {
            'id': block_id,
            'content': content,
            'styled_content': styled_content,
            'block_type': block_type,
            'position_xy': [round(position_xy[0], 2), round(position_xy[1], 2)],
            'max_allowable_width': round(max_width, 2),
            'default_style': default_style,
            'additional_styles': additional_styles,
            'matching_spans': matching_spans,
            'mineru_original': mineru_block
        }
        
        if block_type == 'list_item':
            enriched_block['list_marker'] = self._create_list_marker(matching_spans)
        
        svg_info = self._detect_svgs_in_content(content)
        if svg_info:
            enriched_block['svgs_in_block'] = svg_info
        
        return enriched_block



    def _determine_block_type(self, content: str, mineru_block: Dict) -> str:
        """Déterminer le type de bloc"""

        if mineru_block['type'] == 'title':
            return 'title'

        if (content.strip().startswith('•') or 
            re.match(r'^\s*[\-\*]\s', content) or
            re.match(r'^\s*\d+\.\s', content)):
            return 'list_item'

        if content.isupper() and len(content.split()) < 10:
            return 'title'

        return 'paragraph'

    def _create_styled_content(self, content: str, matching_spans: List, page_num: int):
        """Crée styled_content et additional_styles uniquement."""
        if not matching_spans:
            return content, {}
        
        span_styles = []
        for s in matching_spans:
            if s.get('text'):
                span_styles.append({
                    'font': s.get('font_name'),
                    'size': s.get('font_size'),
                    'color': s.get('color_rgb'),
                    'is_bold': s.get('is_bold'),
                    'is_italic': s.get('is_italic'),
                    'text': s.get('text')
                })
        
        if not span_styles:
            return content, {}
        
        # Style dominant
        from collections import defaultdict
        style_freq = defaultdict(int)
        for s in span_styles:
            style_key = (s['font'], s['size'], s['color'], s['is_bold'], s['is_italic'])
            style_freq[style_key] += len(s['text'])
        
        dominant_style_key = max(style_freq, key=style_freq.get)
        
        # Créer styled_content
        styled_parts = []
        additional_styles = {}
        style_counter = 1
        
        for span in span_styles:
            current_style_key = (span['font'], span['size'], span['color'], span['is_bold'], span['is_italic'])
            if current_style_key == dominant_style_key:
                styled_parts.append(span['text'])
            else:
                style_tag = f"s{style_counter}"
                additional_styles[style_tag] = {
                    'police': span['font'],
                    'taille': span['size'],
                    'couleur': span['color']
                }
                styled_parts.append(f"{style_tag}{span['text']}{style_tag}")
                style_counter += 1
        
        styled_content = "".join(styled_parts)
        import re
        styled_content = re.sub(r'\s+', ' ', styled_content.replace('\n', ' ').replace('\t', ' '))
        
        return styled_content, additional_styles




    def _create_list_marker(self, matching_spans: List):
        """Créer les informations de marqueur de liste"""

        if not matching_spans:
            return {"text": "•", "style": {"police": "Unknown", "taille": 12.0, "couleur": 0}, "text_indent": 15.0}

        first_span = matching_spans[0]
        return {
            "text": "•",
            "style": {"police": first_span['font_name'], "taille": first_span['font_size'], "couleur": first_span['color_rgb']},
            "text_indent": 15.0
        }

    def _detect_svgs_in_content(self, content: str):
        """Détecter les références SVG dans le contenu"""
        svg_pattern = r'<svg\s+id="([^"]+)"/>'
        svgs = re.findall(svg_pattern, content)
        if not svgs: return None

        svg_info = {}
        for i, svg_id in enumerate(svgs):
            svg_info[f"SVG_{i}"] = {
                "file": f"{svg_id}.svg", "taille_texte_reference": 10.5,
                "ratio_largeur_hauteur": 0.5426, "ajustement_vertical": -12
            }
        return svg_info

    def _create_isolated_span_block(self, span: Dict, page_num: int, group_num: int, bloc_num: int):
        """Créer un bloc pour un span isolé"""

        block_id = f"page{page_num+1}_isolated_pymupdf_{span['id']}"
        page_dims = self.page_dimensions[page_num]
        position_xy = [span['bbox_normalized'][0] * page_dims[0], span['bbox_normalized'][1] * page_dims[1]]
        width = (span['bbox_normalized'][2] - span['bbox_normalized'][0]) * page_dims[0]

        default_style = {"police": span['font_name'], "taille": span['font_size'], "couleur": span['color_rgb']}

        return {
            'id': block_id, 'content': span['text'], 'styled_content': span['text'],
            'block_type': 'isolated_span',
            'position_xy': [round(position_xy[0], 2), round(position_xy[1], 2)],
            'max_allowable_width': round(width, 2),
            'default_style': default_style, 'additional_styles': {},
            'matching_spans': [span], 'source': 'pymupdf_isolated',
            'include_in_output': True  # ← AJOUTER CETTE LIGNE
        }


    def _calculate_real_line_count(self, matching_spans: List, max_width: float, page_num: int) -> int:
        """
        Calcule le nombre réel de lignes basé sur les spans PyMuPDF et la largeur maximale.
        Les spans sont déjà triés par position de lecture (y, puis x).
        """
        if not matching_spans:
            return 1

        # Regrouper les spans en lignes basées sur leur position Y
        lines = []
        current_line = []
        current_y = None
        y_tolerance = 2.0  # Tolérance en pixels pour considérer que deux spans sont sur la même ligne

        page_dims = self.page_dimensions.get(page_num, {})

        for span in matching_spans:
            # Position Y en pixels
            span_y = span['bbox_pixels'][1]  # top Y

            # Si c'est le premier span ou si le Y est différent (nouvelle ligne)
            if current_y is None or abs(span_y - current_y) > y_tolerance:
                if current_line:
                    lines.append(current_line)
                current_line = [span]
                current_y = span_y
            else:
                # Même ligne
                current_line.append(span)

        # Ajouter la dernière ligne
        if current_line:
            lines.append(current_line)

        return max(1, len(lines))


    def create_clean_template(self, pdf_path: str, output_template: str, enriched_data: List[List[Dict[str, Any]]] = None):
        """
        Crée un template PDF sans texte
        
        Args:
            pdf_path: Chemin vers le PDF source
            output_template: Chemin vers le template de sortie
            enriched_data: Données enrichies pour identifier les spans à exclure
                          Si None, tous les spans sont supprimés (comportement par défaut)
        """
        print(f"\n🧹 Création du template: {output_template}")
        
        # Collecter les bounding boxes des spans à CONSERVER
        excluded_bboxes = set()
        
        if enriched_data:
            for page_num, page_blocks in enumerate(enriched_data):
                for block in page_blocks:
                    # ✅ Garder les spans exclus des blocs normaux
                    if not block.get('include_in_output', True) and block.get('block_type') != 'isolated_span':
                        matching_spans = block.get('matching_spans', [])
                        for span in matching_spans:
                            bbox_px = span.get('bbox_pixels')
                            if bbox_px:
                                bbox_key = (page_num, tuple(bbox_px))
                                excluded_bboxes.add(bbox_key)
                    
                    # ✅ NOUVEAU : Garder les isolated_span exclus (mais pas consumed)
                    if block.get('block_type') == 'isolated_span':
                        if not block.get('include_in_output', True) and not block.get('is_consumed', False):
                            matching_spans = block.get('matching_spans', [])
                            for span in matching_spans:
                                bbox_px = span.get('bbox_pixels')
                                if bbox_px:
                                    bbox_key = (page_num, tuple(bbox_px))
                                    excluded_bboxes.add(bbox_key)
            
            print(f"   📌 {len(excluded_bboxes)} spans exclus seront conservés dans le template")
        
        doc = fitz.open(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            print(f"   Page {page_num + 1}: Suppression du texte...")
            
            try:
                text_dict = page.get_text("dict")
                text_instances = []
                kept_count = 0
                removed_count = 0
                
                for block in text_dict["blocks"]:
                    if block.get("type") == 0:
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                if span.get("text", "").strip():
                                    span_bbox = span["bbox"]
                                    bbox_key = (page_num, tuple(span_bbox))
                                    
                                    # Vérifier si ce span doit être conservé
                                    if bbox_key in excluded_bboxes:
                                        kept_count += 1
                                        # Ne pas ajouter à text_instances = ne pas supprimer
                                    else:
                                        removed_count += 1
                                        text_instances.append({'bbox': fitz.Rect(span_bbox)})
                
                # Appliquer les suppressions
                for instance in text_instances:
                    page.add_redact_annot(instance['bbox'])
                
                if text_instances:
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
                
                if kept_count > 0:
                    print(f"      ✅ {removed_count} spans supprimés, {kept_count} spans conservés")
                else:
                    print(f"      ✅ {removed_count} spans supprimés")
                    
            except Exception as e:
                print(f"      ❌ Erreur: {e}")
        
        doc.save(output_template, garbage=4, deflate=True, clean=True)
        doc.close()
        print(f"   ✅ Template créé")




    def create_visual_diagnostic(self, pdf_path: str, enriched_data: List, base_name: str = None):
        """Créer un PDF de diagnostic visuel basé sur l'enrichissement existant"""
        if base_name is None:
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]

        diagnostic_file = f"{base_name}_diagnostic.pdf"

        # Ouvrir le PDF original
        doc = fitz.open(pdf_path)

        # Statistiques globales
        global_stats = {
            'total_mineru_blocks': 0,
            'total_pymupdf_spans': 0,
            'matched_spans': 0,
            'empty_mineru_blocks': 0,
            'partial_matches': 0
        }

        # Traiter chaque page
        for page_num in range(len(doc)):
            if page_num >= len(enriched_data):
                break

            page = doc.load_page(page_num)
            page_blocks = enriched_data[page_num]

            # Dessiner le diagnostic sur cette page
            self._draw_diagnostic_on_page(page, page_blocks, global_stats, page_num)

        # Ajouter une page de résumé
        self._add_diagnostic_summary_page(doc, global_stats)

        # Sauvegarder
        doc.save(diagnostic_file)
        doc.close()

        print(f"   ✅ Diagnostic créé: {diagnostic_file}")
        self._print_diagnostic_stats(global_stats)

        return diagnostic_file

    def _draw_diagnostic_on_page(self, page, page_blocks: List, global_stats: Dict, page_num: int):
        """Dessiner les éléments de diagnostic sur une page"""
        page_rect = page.rect

        for block_idx, block in enumerate(page_blocks):
            if not block.get('block_type'):
                continue

            matching_spans = block.get('matching_spans', [])

            # Calculer la bbox en pixels
            if 'mineru_original' in block:
                mineru_bbox = block['mineru_original']['bbox']
                bbox_pixels = [
                    mineru_bbox[0] * page_rect.width,
                    mineru_bbox[1] * page_rect.height,
                    mineru_bbox[2] * page_rect.width,
                    mineru_bbox[3] * page_rect.height
                ]
            else:
                if matching_spans:
                    span = matching_spans[0]
                    bbox_pixels = span['bbox_pixels']
                else:
                    continue

            bbox_rect = fitz.Rect(bbox_pixels)

            # Déterminer le type de match
            if not matching_spans:
                color, width = (1, 0.5, 0), 1.5
                global_stats['empty_mineru_blocks'] += 1
            else:
                spans_text_len = sum(len(s['text']) for s in matching_spans)
                block_content_len = len(block.get('content', ''))

                if block_content_len > 0:
                    coverage = spans_text_len / block_content_len
                else:
                    coverage = 1.0

                if coverage >= 0.8:
                    color, width = (0, 0.8, 0), 2.0
                elif coverage >= 0.5:
                    color, width = (1, 0.65, 0), 2.0
                    global_stats['partial_matches'] += 1
                else:
                    color, width = (1, 0.4, 0), 2.0
                    global_stats['partial_matches'] += 1

            # Dessiner le rectangle du bloc
            page.draw_rect(bbox_rect, color=color, width=width)

            # Numéroter le bloc
            center_x = (bbox_rect.x0 + bbox_rect.x1) / 2
            center_y = (bbox_rect.y0 + bbox_rect.y1) / 2
            num_text = f"B{block_idx}"

            text_rect = fitz.Rect(center_x - 15, center_y - 8, center_x + 15, center_y + 8)
            page.draw_rect(text_rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=0.8)
            page.insert_text(fitz.Point(center_x - 10, center_y + 3), num_text, 
                            fontsize=10, color=(0, 0, 0))

            # Dessiner les spans matchés
            for span in matching_spans:
                span_bbox = fitz.Rect(span['bbox_pixels'])

                quality = span.get('match_quality', 'unmatched')
                if quality == 'excellent':
                    span_color = (0, 0, 1)
                elif quality == 'good':
                    span_color = (0, 0.5, 1)
                elif quality == 'fair':
                    span_color = (0.5, 0.5, 1)
                else:
                    span_color = (0.8, 0.8, 1)

                page.draw_rect(span_bbox, color=span_color, width=1.0)

                global_stats['matched_spans'] += 1

            global_stats['total_mineru_blocks'] += 1
            global_stats['total_pymupdf_spans'] += len(matching_spans)

    def _add_diagnostic_summary_page(self, doc, stats: Dict):
        """Ajouter une page de résumé avec statistiques"""
        summary_page = doc.new_page(width=595, height=842)
        y = 50

        title = "RAPPORT DE DIAGNOSTIC DE MATCHING"
        summary_page.insert_text(fitz.Point(50, y), title, fontsize=16, color=(0, 0, 0))
        y += 40

        match_rate = (stats['matched_spans'] / stats['total_pymupdf_spans'] * 100) if stats['total_pymupdf_spans'] > 0 else 0
        empty_rate = (stats['empty_mineru_blocks'] / stats['total_mineru_blocks'] * 100) if stats['total_mineru_blocks'] > 0 else 0

        summary_lines = [
            f"Blocs traites totaux: {stats['total_mineru_blocks']}",
            f"Spans PyMuPDF totaux: {stats['total_pymupdf_spans']}",
            f"",
            f"Spans matches: {stats['matched_spans']} ({match_rate:.1f}%)",
            f"Blocs vides: {stats['empty_mineru_blocks']} ({empty_rate:.1f}%)",
            f"Blocs avec matches partiels: {stats['partial_matches']}",
            f"",
            f"LEGENDE DES COULEURS:",
            f"Vert fonce: Bloc avec match complet (>=80%)",
            f"Orange: Bloc avec match partiel (50-80%)",
            f"Orange clair: Bloc avec match faible (<50%)",
            f"Rouge: Bloc vide (aucun span)",
            f"Bleu: Spans matches (intensite = qualite)",
        ]

        for line in summary_lines:
            summary_page.insert_text(fitz.Point(50, y), line, fontsize=11, color=(0, 0, 0))
            y += 15

    def _print_diagnostic_stats(self, stats: Dict):
        """Afficher les statistiques du diagnostic"""
        match_rate = (stats['matched_spans']/stats['total_pymupdf_spans']*100) if stats['total_pymupdf_spans'] > 0 else 0

        print(f"\n   📊 Statistiques:")
        print(f"      Blocs: {stats['total_mineru_blocks']}")
        print(f"      Spans: {stats['total_pymupdf_spans']}")
        print(f"      Taux de matching: {match_rate:.1f}%")


    def _generate_translation_format(self, enriched_data: list):
        """Génère le format pour traduction avec styles globaux."""
        translation_data = []
        merged_groups = {}
        processed_block_ids = set()

        # Étape 1: Identification des groupes fusionnés
        for page_blocks in enriched_data:
            for block in page_blocks:
                if block.get('merge_group_id'):
                    merge_group_id = block.get('merge_group_id')
                    if merge_group_id not in merged_groups:
                        merged_groups[merge_group_id] = []
                    merged_groups[merge_group_id].append(block)

        # Utiliser le mapping déjà construit
        style_mapping = self.block_additional_style_refs

        # Étape 2: Traitement des groupes fusionnés
        for group_id, blocks in merged_groups.items():
            blocks_sorted = sorted(blocks, key=lambda b: b.get('merge_order', 0))
            
            # ... (logique de style de référence inchangée) ...
            reference_default_style = blocks_sorted[0].get('default_style', {})
            first_block_id = blocks_sorted[0].get('id')
            
            unified_style_mapping = {}
            
            # 1. Collecter additional_styles
            for blk in blocks_sorted:
                blk_id = blk.get('id')
                if blk_id in style_mapping:
                    for local_tag, global_tag in style_mapping[blk_id].items():
                        style_info = blk.get('additional_styles', {}).get(local_tag)
                        if style_info:
                            style_key = (
                                style_info.get('police'),
                                style_info.get('taille'),
                                style_info.get('couleur')
                            )
                            if style_key not in unified_style_mapping:
                                unified_style_mapping[style_key] = global_tag
            
            # 2. Ajouter default_styles
            reference_style_key = (
                reference_default_style.get('police'),
                reference_default_style.get('taille'),
                reference_default_style.get('couleur')
            )
            
            for blk in blocks_sorted:
                blk_id = blk.get('id')
                blk_default = blk.get('default_style', {})
                blk_style_key = (
                    blk_default.get('police'),
                    blk_default.get('taille'),
                    blk_default.get('couleur')
                )
                
                if blk_style_key != reference_style_key and blk_style_key not in unified_style_mapping:
                    for gs_tag, gs_style in self.global_styles.items():
                        gs_key = (
                            gs_style.get('police'),
                            gs_style.get('taille'),
                            gs_style.get('couleur')
                        )
                        if blk_style_key == gs_key:
                            unified_style_mapping[blk_style_key] = gs_tag
                            break
            
            # 3. Reconstruire le contenu stylé
            merged_parts = []
            for blk in blocks_sorted:
                matching_spans = blk.get('matching_spans', [])
                if matching_spans:
                    styled_text = self._rebuild_styled_content_for_merged_group(
                        matching_spans,
                        reference_default_style,
                        unified_style_mapping
                    )
                else:
                    styled_text = blk.get('styled_content', blk.get('content', ''))
                    blk_id = blk.get('id')
                    if blk_id in style_mapping:
                        for local_tag, global_tag in style_mapping[blk_id].items():
                            styled_text = styled_text.replace(f"<{local_tag}>", f"<{global_tag}>")
                            styled_text = styled_text.replace(f"</{local_tag}>", f"</{global_tag}>")
                
                merged_parts.append(styled_text)
            
            merged_text = " ".join(merged_parts)
            
            # --- INTERVENTION OVERRIDE (GROUPES) ---
            if group_id in self.translation_overrides:
                # print(f"[OVERRIDE] Application de la correction pour le groupe {group_id}")
                merged_text = self.translation_overrides[group_id]
            # ---------------------------------------
            
            if merged_text.strip():
                translation_data.append({"id": group_id, "source": merged_text.strip(), "target": ""})
            processed_block_ids.update(b.get('id') for b in blocks_sorted)

        # Étape 3: Traitement des blocs restants
        for page_blocks in enriched_data:
            for block in page_blocks:
                if block.get('id') in processed_block_ids:
                    continue

                block_type = block.get('block_type')

                if block_type == 'isolated_span':
                    block_id = block.get('id')
                    is_consumed = block.get('is_consumed', False)
                    include_output = block.get('include_in_output', False)
                    
                    if is_consumed or not include_output:
                        continue
                    
                    has_consumed_spans = False
                    for span in block.get('matching_spans', []):
                        span_matched_block = span.get('matched_to_block')
                        if span_matched_block and span_matched_block != block_id:
                            has_consumed_spans = True
                            break
                    
                    if has_consumed_spans:
                        continue
                    
                    matching_spans = block.get('matching_spans', [])
                    if matching_spans:
                        content = self._rebuild_styled_content_from_spans(
                            matching_spans,
                            block.get('default_style', {}),
                            block.get('additional_styles', {})
                        )
                    else:
                        content = block.get('styled_content', block.get('content', ''))
                    
                    content = self._replace_local_styles_with_global(content, block_id, style_mapping)
                    
                    # --- INTERVENTION OVERRIDE (ISOLATED) ---
                    if block_id in self.translation_overrides:
                        content = self.translation_overrides[block_id]
                    # ----------------------------------------

                    if content.strip():
                        translation_data.append({"id": block_id, "source": content.strip(), "target": ""})
                
                elif block_type != 'isolated_span':
                    matching_spans = block.get('matching_spans', [])
                    block_id = block.get('id')
                    
                    if matching_spans:
                        source_text = self._rebuild_styled_content_from_spans(
                            matching_spans,
                            block.get('default_style', {}),
                            block.get('additional_styles', {})
                        )
                    else:
                        source_text = block.get('styled_content', block.get('content', ''))
                    
                    source_text = self._replace_local_styles_with_global(source_text, block_id, style_mapping)
                    
                    # --- INTERVENTION OVERRIDE (STANDARD) ---
                    if block_id in self.translation_overrides:
                        source_text = self.translation_overrides[block_id]
                    # ----------------------------------------
                    
                    if source_text.strip() and block.get('include_in_output', True):
                        translation_data.append({"id": block_id, "source": source_text.strip(), "target": ""})

        return translation_data


    def _rebuild_styled_content_for_merged_group(
        self,
        matching_spans: List,
        reference_default_style: Dict,
        unified_style_mapping: Dict
    ) -> str:
        """
        Reconstruit le styled_content pour un bloc membre d'un groupe mergé.
        Utilise un mapping unifié avec des tags GLOBAUX (gsX).
        
        Args:
            matching_spans: Liste des spans du bloc actuel
            reference_default_style: Style de référence pour tout le groupe
            unified_style_mapping: Mapping {(police, taille, couleur): global_tag (gsX)}
        
        Returns:
            Contenu stylé avec balises GLOBALES <gs1>, <gs2>, etc.
        """
        if not matching_spans:
            return ""
        
        reference_style_key = (
            reference_default_style.get('police'),
            reference_default_style.get('taille'),
            reference_default_style.get('couleur')
        )
        
        styled_parts = []
        
        for span in matching_spans:
            # ✅ CORRECTION : Gérer les spans avec text=None
            span_text = span.get('text')
            if not span_text:
                continue
            
            span_style_key = (
                span.get('font_name'),
                span.get('font_size'),
                span.get('color_rgb')
            )
            
            # Comparer avec le style de référence du groupe
            if span_style_key == reference_style_key:
                # Style correspond à la référence : pas de balise
                styled_parts.append(span_text)
            else:
                # Style différent : chercher le tag GLOBAL dans le mapping
                global_tag = unified_style_mapping.get(span_style_key)
                
                if global_tag:
                    # Utilise directement le tag global (gsX)
                    styled_parts.append(f"<{global_tag}>{span_text}</{global_tag}>")
                else:
                    # Style non trouvé : fallback sans balise
                    styled_parts.append(span_text)
        
        styled_content = "".join(styled_parts)
        
        # Nettoyer les espaces
        styled_content = re.sub(r'\s+', ' ', styled_content).replace(' </', '</').replace('> <', '><')
        
        return styled_content




    def _get_or_create_global_style(self, style_info: Dict) -> str:
        """
        Cherche ou crée un style global correspondant à style_info.
        
        Args:
            style_info: Dictionnaire avec 'police', 'taille', 'couleur'
        
        Returns:
            Tag du style global (ex: 'gs1', 'gs2', etc.)
        """
        style_key = (
            style_info.get('police'),
            style_info.get('taille'),
            style_info.get('couleur')
        )
        
        # Chercher si ce style existe déjà
        for gs_tag, gs_style in self.global_styles.items():
            gs_key = (
                gs_style.get('police'),
                gs_style.get('taille'),
                gs_style.get('couleur')
            )
            if style_key == gs_key:
                return gs_tag
        
        # Créer un nouveau style global
        existing_nums = []
        for tag in self.global_styles.keys():
            if tag.startswith('gs') and tag[2:].isdigit():
                existing_nums.append(int(tag[2:]))
        
        next_num = max(existing_nums) + 1 if existing_nums else 1
        new_tag = f"gs{next_num}"
        
        # Ajouter aux styles globaux
        self.global_styles[new_tag] = {
            'police': style_info.get('police'),
            'taille': style_info.get('taille'),
            'couleur': style_info.get('couleur')
        }
        
        return new_tag




    def _rebuild_styled_content_from_spans(self, matching_spans: List, default_style: Dict, additional_styles: Dict) -> str:
        """
        Reconstruit le styled_content à partir des matching_spans actuels.
        Utilise la même logique que _create_styled_content().
        
        Args:
            matching_spans: Liste des spans actuellement associés au bloc
            default_style: Style par défaut du bloc
            additional_styles: Styles additionnels du bloc
        
        Returns:
            Contenu stylé avec balises <s1>, <s2>, etc.
        """
        if not matching_spans:
            return ""
        
        # Créer une liste de styles pour chaque span
        span_styles = []
        for s in matching_spans:
            # ✅ CORRECTION : Ignorer les spans sans texte
            if not s.get('text'):
                continue
            span_styles.append({
                'font': s.get('font_name'),
                'size': s.get('font_size'),
                'color': s.get('color_rgb'),
                'is_bold': s.get('is_bold'),
                'is_italic': s.get('is_italic'),
                'text': s.get('text')
            })
        
        if not span_styles:
            return ""
        
        # Déterminer le style dominant (celui avec le plus de caractères)
        style_freq = {}
        for s in span_styles:
            style_key = (s['font'], s['size'], s['color'], s['is_bold'], s['is_italic'])
            style_freq[style_key] = style_freq.get(style_key, 0) + len(s['text'])
        
        dominant_style_key = max(style_freq, key=style_freq.get)
        
        # Définir le style dominant attendu depuis default_style
        default_style_key = (
            default_style.get('police'),
            default_style.get('taille'),
            default_style.get('couleur'),
            False,  # is_bold
            False   # is_italic
        )
        
        # Reconstruire le texte avec balises de style
        styled_parts = []
        
        for span in span_styles:
            current_style_key = (span['font'], span['size'], span['color'], span['is_bold'], span['is_italic'])
            
            # Comparer avec le style par défaut
            if (span['font'] == default_style.get('police') and 
                span['size'] == default_style.get('taille') and 
                span['color'] == default_style.get('couleur')):
                # Style dominant : pas de balise
                styled_parts.append(span['text'])
            else:
                # Style additionnel : chercher la balise correspondante dans additional_styles
                style_tag = None
                for tag, style_info in additional_styles.items():
                    if (style_info.get('police') == span['font'] and 
                        style_info.get('taille') == span['size'] and 
                        style_info.get('couleur') == span['color']):
                        style_tag = tag
                        break
                
                if style_tag:
                    styled_parts.append(f"<{style_tag}>{span['text']}</{style_tag}>")
                else:
                    # Si pas de style additionnel trouvé, ajouter sans balise
                    styled_parts.append(span['text'])
        
        styled_content = "".join(styled_parts)
        
        # Nettoyer les espaces multiples et formater proprement
        styled_content = re.sub(r'\s+', ' ', styled_content).replace(' </', '</').replace('> <', '><')
        
        return styled_content



    def _replace_local_styles_with_global(self, styled_text: str, block_id: str, style_mapping: dict):
        """
        Remplace les balises <s1> par <gs1> selon le mapping du bloc.
        
        Args:
            styled_text: Texte avec balises de style locales (<s1>, <s2>, etc.)
            block_id: Identifiant du bloc
            style_mapping: Dictionnaire de mapping {block_id: {local_style: global_style}}
        
        Returns:
            Texte avec balises de style globales (<gs1>, <gs2>, etc.)
        """
        if block_id not in style_mapping:
            return styled_text
        
        block_mapping = style_mapping[block_id]
        
        for local_style, global_style in block_mapping.items():
            # Remplacer <s1> par <gs1> et </s1> par </gs1>
            styled_text = styled_text.replace(f"<{local_style}>", f"<{global_style}>")
            styled_text = styled_text.replace(f"</{local_style}>", f"</{global_style}>")
        
        return styled_text

    def _rebuild_styled_content_from_spans_with_reference(
        self, 
        matching_spans: List, 
        reference_default_style: Dict, 
        group_additional_styles: Dict,
        block_default_style: Dict
    ) -> str:
        """
        Reconstruit le styled_content pour un bloc membre d'un groupe mergé.
        Utilise un style de référence commun pour tout le groupe.
        
        Args:
            matching_spans: Liste des spans du bloc actuel
            reference_default_style: Style de référence pour tout le groupe (généralement du premier bloc)
            group_additional_styles: Tous les styles additionnels du groupe mergé
            block_default_style: Style par défaut du bloc actuel (pour détecter si différent de la référence)
        
        Returns:
            Contenu stylé avec balises <s1>, <s2>, etc.
        """
        if not matching_spans:
            return ""
        
        styled_parts = []
        
        # Créer un mapping inverse : style_info -> tag
        style_to_tag = {}
        for tag, style_info in group_additional_styles.items():
            style_key = (
                style_info.get('police'),
                style_info.get('taille'),
                style_info.get('couleur')
            )
            style_to_tag[style_key] = tag
        
        for span in matching_spans:
            span_style_key = (span.get('font_name'), span.get('font_size'), span.get('color_rgb'))
            reference_style_key = (
                reference_default_style.get('police'),
                reference_default_style.get('taille'),
                reference_default_style.get('couleur')
            )
            
            # Comparer avec le style de référence du groupe
            if span_style_key == reference_style_key:
                # Style correspond à la référence : pas de balise
                styled_parts.append(span.get('text'))
            else:
                # Style différent : chercher la balise correspondante
                style_tag = style_to_tag.get(span_style_key)
                
                if style_tag:
                    # Style additionnel trouvé dans le groupe
                    styled_parts.append(f"<{style_tag}>{span.get('text')}</{style_tag}>")
                else:
                    # Style non répertorié : créer une nouvelle balise
                    # (cela arrive quand le default_style du bloc diffère de la référence)
                    block_style_key = (
                        block_default_style.get('police'),
                        block_default_style.get('taille'),
                        block_default_style.get('couleur')
                    )
                    
                    if span_style_key == block_style_key:
                        # Le span correspond au default_style du bloc actuel
                        # qui diffère de la référence du groupe
                        # Il faut créer une balise pour ce style
                        
                        # Générer un nouveau tag
                        existing_tags = [tag for tag in group_additional_styles.keys() if tag.startswith('s')]
                        if existing_tags:
                            max_num = max([int(tag[1:]) for tag in existing_tags if tag[1:].isdigit()] + [0])
                            new_tag = f"s{max_num + 1}"
                        else:
                            new_tag = "s1"
                        
                        # Ajouter au mapping
                        group_additional_styles[new_tag] = {
                            'police': span.get('font_name'),
                            'taille': span.get('font_size'),
                            'couleur': span.get('color_rgb')
                        }
                        style_to_tag[span_style_key] = new_tag
                        
                        styled_parts.append(f"<{new_tag}>{span.get('text')}</{new_tag}>")
                    else:
                        # Style inconnu : ajouter sans balise (fallback)
                        styled_parts.append(span.get('text'))
        
        styled_content = "".join(styled_parts)
        
        # Nettoyer les espaces
        styled_content = re.sub(r'\s+', ' ', styled_content).replace(' </', '</').replace('> <', '><')
        
        return styled_content

    def _calculate_line_count_from_bbox(self, bbox: List, matching_spans: List, page_idx: int) -> int:
        """
        ✅ NOUVELLE FONCTION : Calcule le nombre de lignes depuis la hauteur de la bbox.
        
        Args:
            bbox: Bbox normalisée [x0, y0, x1, y1]
            matching_spans: Spans (pour taille de police)
            page_idx: Index de page
        
        Returns:
            Nombre de lignes estimé
        """
        if not bbox or len(bbox) < 4:
            return 1
        
        # Hauteur de la bbox normalisée
        bbox_height = bbox[3] - bbox[1]
        
        # Taille de police moyenne
        font_sizes = [s.get('font_size', 10) for s in matching_spans if s.get('font_size')]
        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 10
        
        # Hauteur d'une ligne normalisée (avec interligne)
        page_height = self.page_dimensions[page_idx][1]
        line_height_normalized = (avg_font_size * 1.2) / page_height
        
        # Nombre de lignes
        line_count = max(1, round(bbox_height / line_height_normalized))
        
        return line_count


    def _generate_formatting_format(self, enriched_data: List):
        """Générer le format de mise en page avec styles globaux unifiés."""
        
        def get_or_create_global_style(style_dict):
            """
            Ajoute un style au dictionnaire global ou retourne sa clé s'il existe déjà.
            On normalise la taille de police pour éviter les doublons dus aux flottants.
            """
            raw_size = style_dict.get('taille', 0)

            # Normalisation de la taille :
            # - Si pas de taille valide, on met 0
            # - Sinon, on arrondit à 0.1 pt (tu peux passer à 0.5 si tu veux regrouper plus agressivement)
            try:
                size = float(raw_size)
            except (TypeError, ValueError):
                size = 0.0

            # Arrondi à 0.1 pt
            normalized_size = 0.2 * round(size / 0.2)

            # Construire la signature à partir de la taille normalisée
            style_signature = (
                style_dict.get('police', ''),
                normalized_size,
                style_dict.get('couleur', 0)
            )

            # Vérifier si ce style existe déjà
            if style_signature in self.style_mapping:
                return self.style_mapping[style_signature]

            # Sinon, créer un nouveau style global
            existing_numbers = [int(k[2:]) for k in self.global_styles.keys() if k.startswith('gs')]
            next_number = max(existing_numbers, default=0) + 1

            key = f"gs{next_number}"
            self.global_styles[key] = {
                "police": style_dict.get('police', ''),
                "taille": normalized_size,
                "couleur": style_dict.get('couleur', 0)
            }
            self.style_mapping[style_signature] = key

            return key

        
        # ✅ Premier passage - collecter TOUS les styles (default + additional)
        block_default_style_refs = {}
        
        for page_blocks in enriched_data:
            for block in page_blocks:
                block_id = block.get('id')
                
                # Traiter le default_style
                default_style = block.get('default_style', {})
                if default_style:
                    gs_key = get_or_create_global_style(default_style)
                    block_default_style_refs[block_id] = gs_key
                
                # Traiter les additional_styles
                additional_styles = block.get('additional_styles', {})
                if additional_styles:
                    if block_id not in self.block_additional_style_refs:
                        self.block_additional_style_refs[block_id] = {}
                    
                    for local_key, style in additional_styles.items():
                        gs_key = get_or_create_global_style(style)
                        self.block_additional_style_refs[block_id][local_key] = gs_key
        
        print(f"[INFO] {len(self.global_styles)} styles globaux collectés")
        
        # Créer la structure du fichier de formatage
        formatting_data = {
            "global_styles": self.global_styles,
            "pages": []
        }
        
        # Création du formatage : blocs avec styles locaux conservés (pour rétrocompatibilité)
        for page_idx, page_blocks in enumerate(enriched_data):
            page_info = {
                "page_number": page_idx + 1,
                "dimensions": self.page_dimensions[page_idx],
                "blocks": []
            }
            
            for block in page_blocks:
                if block.get('block_type') and block.get('include_in_output', True):
                    
                    # Recalculer position_xy depuis mineru_original.bbox
                    if 'mineru_original' in block and 'bbox' in block['mineru_original']:
                        bbox = block['mineru_original']['bbox']
                        page_dims = self.page_dimensions[page_idx]
                        position_xy = (bbox[0] * page_dims[0], bbox[1] * page_dims[1])
                        max_allowable_width = (bbox[2] - bbox[0]) * page_dims[0]
                    else:
                        position_xy = block['position_xy']
                        max_allowable_width = block['max_allowable_width']
                    
                    calculated_line_spacing = self._calculate_average_line_spacing(
                        block.get('matching_spans', []),
                        block['default_style']
                    )
                    
                    formatting_block = {
                        "id": block['id'],
                        "block_type": block['block_type'],
                        "position_xy": position_xy,
                        "lignes_originales": self._calculate_line_count_from_bbox(
                            block.get('mineru_original', {}).get('bbox', []),
                            block.get('matching_spans', []),
                            page_idx
                        ),
                        "max_allowable_width": max_allowable_width,
                        "interligne_normal": calculated_line_spacing,
                        "alignment": "left",  # ancien champ, laissé pour compat éventuelle
                        "align": block.get('align', 'left'),
                        "default_style": block['default_style'],
                        "styles": block['additional_styles']
                    }
                    
                    # Référence au style global par défaut
                    block_id = block.get('id')
                    if block_id in block_default_style_refs:
                        formatting_block['default_style_ref'] = block_default_style_refs[block_id]
                    
                    # Gestion des listes "anciennes" (list_marker) – conservée pour compat
                    if block['block_type'] == 'list_item' and 'list_marker' in block:
                        formatting_block['list_marker'] = block['list_marker']
                    
                    # ✅ NOUVEAU : Copie des propriétés de liste manuelles
                    if 'is_list' in block:
                        formatting_block['is_list'] = block['is_list']
                    if 'list_bullet' in block:
                        formatting_block['list_bullet'] = block['list_bullet']
                    if 'list_indent' in block:
                        formatting_block['list_indent'] = block['list_indent']
                    if 'list_hang' in block:
                        formatting_block['list_hang'] = block['list_hang']
                    
                    # Gestion des SVGs
                    if 'svgs_in_block' in block:
                        formatting_block['svgs_in_block'] = block['svgs_in_block']
                    
                    # Gestion des groupes fusionnés
                    if block.get('merge_group_id'):
                        formatting_block['merge_group_id'] = block['merge_group_id']
                        formatting_block['merge_order'] = block.get('merge_order', 0)
                        formatting_block['is_merged_member'] = True
                    
                    page_info["blocks"].append(formatting_block)
            
            formatting_data["pages"].append(page_info)
        
        return formatting_data



def main():
    if len(sys.argv) < 2:
        print("Usage: python extract.py <basename> [--diagnostic]")
        print("📝 Exemple: python extract.py Yokai")
        print("📝 Avec diagnostic: python extract.py Yokai --diagnostic")
        sys.exit(1)

    base_name = sys.argv[1]
    create_diagnostic = '--diagnostic' in sys.argv

    pdf_path = f"{base_name}.pdf"
    mineru_json_path = f"{base_name}_model.json"

    print(f"🚀 Traitement de: {base_name}")
    print(f"   PDF: {pdf_path}")
    print(f"   JSON: {mineru_json_path}")
    if create_diagnostic:
        print(f"   Mode: avec diagnostic visuel")

    if not os.path.exists(pdf_path):
        print(f"❌ PDF non trouvé: {pdf_path}")
        sys.exit(1)

    if not os.path.exists(mineru_json_path):
        print(f"❌ JSON MinerU non trouvé: {mineru_json_path}")
        sys.exit(1)

    try:
        generator = DualOutputGenerator(
            enriched_data=self.data_manager.enriched_data,
            page_dimensions=self.data_manager.page_dimensions
            )

        # Génération normale
        translation_file, formatting_file, template_file = generator.generate_dual_outputs(
            pdf_path, base_name=base_name
        )

        # Diagnostic si demandé
        diagnostic_file = None
        if create_diagnostic:
            print("\n🔍 Création du diagnostic visuel...")
            # ✅ NOUVEAU CODE
        session_file = f"{base_name}_session.json"

        if os.path.exists(session_file):
            print(f"📂 Chargement session : {session_file}")
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
                enriched_data = session_data.get('pages', [])
        else:
            print(f"📖 Génération depuis MinerU...")
            mineru_data = generator._load_mineru_data(mineru_json_path)
            enriched_data = generator._process_with_visual_matching(pdf_path, mineru_data)

            diagnostic_file = generator.create_visual_diagnostic(pdf_path, enriched_data, base_name)

        print(f"\n🎉 SUCCÈS!\n")
        print(f"📝 FICHIER POUR TRADUCTION:")
        print(f"   {translation_file}")
        print(f"\n🎨 FICHIER DE FORMATAGE:")
        print(f"   {formatting_file}")
        print(f"\n🖼️  FICHIER TEMPLATE:")
        print(f"   {template_file}")

        if diagnostic_file:
            print(f"\n🔍 FICHIER DE DIAGNOSTIC:")
            print(f"   {diagnostic_file}")

    except Exception as e:
        print(f"💥 Erreur: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
