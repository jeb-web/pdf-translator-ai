# build.py

import json
import os
import sys
import fitz  # PyMuPDF pour la fusion de PDFs
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import re
import argparse
import copy

# --- REPORTLAB pour SVG ---
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Group

# --- CONFIGURATION ---
FONT_DIR = 'fonts'
FONT_MAPPING_FILE = 'font_mapping.json'
SVG_DIR = 'svgs'
SVG_MAPPING_FILENAME_SUFFIX = '_svg_mapping.json'

# --- FONCTIONS UTILITAIRES ---

# Ajouter cette nouvelle fonction après les imports
def resolve_style_ref(style_ref, global_styles, fallback_style):
    """
    Résout une référence de style (ex: 'gs1') vers l'objet de style complet.
    
    Args:
        style_ref: Référence au style ('gs1') ou objet de style direct
        global_styles: Dictionnaire des styles globaux
        fallback_style: Style par défaut si résolution échoue
    
    Returns:
        Dict avec {police, taille, couleur}
    """
    if isinstance(style_ref, str):
        # C'est une référence, la résoudre
        return global_styles.get(style_ref, fallback_style)
    elif isinstance(style_ref, dict):
        # C'est déjà un objet de style (ancien système)
        return style_ref
    else:
        return fallback_style



def _tokenize_preserve_spaces(s):
    """Regex pour diviser la chaîne en mots et en groupes d'espaces, en les préservant"""
    return re.findall(r'\s+|\S+', s)
    
    
        
def _is_likely_definition_list(translated_text: str, tag_threshold: int = 3) -> bool:
    """
    Détecte de manière heuristique si un bloc de texte est une "liste de définitions"
    (comme une section de crédits) plutôt qu'un paragraphe fluide.

    Critères :
    1. Doit avoir plus qu'un certain nombre de balises de style.
    2. Une majorité du contenu de ces balises doit se terminer par un deux-points.
    """
    # Expression régulière pour trouver toutes les balises de style et leur contenu
    matches = re.findall(r'<(s\d+)>(.*?)</\1>', translated_text)

    # Critère 1: Vérifier s'il y a suffisamment de balises pour justifier l'analyse.
    if len(matches) < tag_threshold:
        return False

    # Critère 2: Compter combien de ces balises se terminent par ":"
    colon_count = 0
    for _, content in matches:
        if content.strip().endswith(':'):
            colon_count += 1

    # Si plus de la moitié des balises correspondent au critère, c'est probablement notre liste.
    if colon_count > 0 and (colon_count / len(matches)) >= 0.5:
        return True

    return False

    def redistribute_merged_text(merged_text, format_blocks, default_style):
        """
        Redistribue le texte traduit d'un groupe fusionné 
        dans les blocs membres selon merge_order
        
        Args:
            merged_text: Texte traduit complet du groupe fusionné
            format_blocks: Liste des blocs membres du groupe (format_data)
            default_style: Style par défaut du premier bloc
        
        Returns:
            Dict {block_id: text_portion}
        """
        result = {}
        blocks_sorted = sorted(format_blocks, key=lambda b: b.get('merge_order', 0))
        
        # Diviser le texte en portions égales par bloc
        lines = merged_text.split('\n')
        line_per_block = max(1, len(lines) // len(blocks_sorted)) if blocks_sorted else 0
        
        line_idx = 0
        for block in blocks_sorted:
            block_lines = lines[line_idx:line_idx + block.get('lignes_originales', 1)]
            result[block['id']] = ' '.join(block_lines)
            line_idx += len(block_lines)
        
        return result  

def format_list_items_for_reflow(text, block_type):
    """
    Pour un bloc de type 'list_item', cette fonction identifie les puces
    et insère un retour à la ligne avant chacune (sauf la première)
    pour garantir que chaque item de la liste commence sur une nouvelle ligne.
    """
    if block_type != 'list_item':
        return text

    all_markers = ['•', '◦', '▪', '▫', '‣', '⁃', '⁌', '⁍', '*', '○', '●']
    
    processed_text = text.strip()

    for marker in all_markers:
        escaped_marker = re.escape(marker)
        pattern = rf'(?<=\S)\s*({escaped_marker})\s*'
        processed_text = re.sub(pattern, r'\n\1 ', processed_text)

    return processed_text


def discover_fonts(format_data):
    """Découvre toutes les polices utilisées dans le document (globales ET locales)"""
    fonts = set()
    
    # 1. Scanner les styles globaux (prioritaire)
    global_styles = format_data.get('global_styles', {})
    for style_key, style_data in global_styles.items():
        if isinstance(style_data, dict) and 'police' in style_data:
            fonts.add(style_data['police'])
    
    # 2. Scanner les styles locaux dans les blocs (rétrocompatibilité)
    for page in format_data.get('pages', []):
        for block in page.get('blocks', []):
            # Style par défaut du bloc
            if 'default_style' in block:
                if isinstance(block['default_style'], dict):
                    fonts.add(block['default_style']['police'])
            
            # Styles additionnels du bloc
            if 'styles' in block:
                for style in block['styles'].values():
                    if isinstance(style, dict) and 'police' in style:
                        fonts.add(style['police'])
            
            # Style de la puce de liste
            if 'list_marker' in block and block.get('list_marker', {}).get('style'):
                marker_style = block['list_marker']['style']
                if isinstance(marker_style, dict) and 'police' in marker_style:
                    fonts.add(marker_style['police'])
    
    return fonts



def setup_fonts(font_mapping_file, font_dir, required_fonts):
    """Configure et enregistre les polices nécessaires"""
    print("\n--- PHASE DE CONFIGURATION DES POLICES ---")

    if not os.path.exists(font_dir):
        os.makedirs(font_dir)
        print(f"[INFO] Dossier '{font_dir}' créé.")

    if not os.path.exists(font_mapping_file):
        print(f"[ACTION REQUISE] Fichier '{font_mapping_file}' introuvable.")
        mapping_template = {font: "NOM_DE_FICHIER.ttf" for font in sorted(list(required_fonts))}
        with open(font_mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mapping_template, f, indent=2)
        print(f"[OK] Modèle créé. Veuillez le remplir et placer les polices dans '{font_dir}/'.")
        return False

    try:
        with open(font_mapping_file, 'r', encoding='utf-8') as f:
            if os.path.getsize(font_mapping_file) == 0:
                print(f"[ERREUR] '{font_mapping_file}' est vide.")
                return False
            font_mapping = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERREUR] Impossible de lire '{font_mapping_file}': {e}")
        return False

    all_fonts_found = True
    for font_name, font_file in font_mapping.items():
        if font_name in required_fonts and font_name not in ["SVG_Placeholder_Font", "default"]:
            if not isinstance(font_file, str) or not font_file.endswith(('.ttf', '.otf')):
                print(f"[AVERTISSEMENT] Format de fichier incorrect ou manquant pour la police '{font_name}' dans '{font_mapping_file}'.")
                all_fonts_found = False
                continue

            font_path = os.path.join(font_dir, font_file)
            if not os.path.exists(font_path):
                print(f"[ERREUR] Fichier de police introuvable : '{font_path}' pour la police '{font_name}'.")
                all_fonts_found = False
            else:
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    print(f" [OK] Police '{font_name}' enregistrée depuis '{font_file}'.")
                except Exception as e:
                    print(f"[ERREUR] Impossible de charger '{font_path}' pour '{font_name}': {e}")
                    all_fonts_found = False

    if not all_fonts_found:
        print("[ACTION REQUISE] Veuillez corriger les erreurs dans la configuration des polices.")
        return False

    print("--- CONFIGURATION DES POLICES TERMINÉE ---")
    return True


def parse_tagged_text(text, default_style, styles_dict, svg_mapping_data):
    """
    Parse le texte XML balisé (incluant <gsN>...</gsN> et <svg id="..."/>)
    et le convertit en une liste de segments texte/SVG.
    
    Args:
        text: Texte balisé avec <gsX> ou <svg>
        default_style: Style par défaut (dict)
        styles_dict: Dictionnaire des styles (global_styles)
        svg_mapping_data: Mapping des SVG
    
    Returns:
        Liste de segments avec style résolu
    """
    segments = []
    tag_pattern = re.compile(r'<(gs\d+)>(.*?)</\1>|<svg id="([^"]*)"\s*/>|([^<]+)', re.DOTALL)
    text_processed = text

    for match in tag_pattern.finditer(text_processed):
        if match.group(1):
            # Balise de style <gsX>
            style_id = match.group(1)
            content = match.group(2)
            style = styles_dict.get(style_id, default_style)
            
            # Sécurité : vérifier que le style est bien un dict
            if not isinstance(style, dict):
                print(f"[ERREUR] Style '{style_id}' n'est pas un dict: {type(style)} = {style}")
                style = default_style
            
            # print(f"[TAG] {style_id}: est dans styles_dict ? {'oui' if style_id in styles_dict else 'non'} | Valeur: {style}")

            if content:
                segments.append({'type': 'text', 'text': content, 'style': style})
                
        elif match.group(3):
            # Balise SVG
            svg_id = match.group(3)
            svg_props = svg_mapping_data.get(svg_id)
            if svg_props:
                segments.append({'type': 'svg', 'id': svg_id, 'props': svg_props, 'style': default_style})
            else:
                print(f"[AVERTISSEMENT] SVG ID '{svg_id}' trouvé dans le texte mais non configuré. Rendu comme texte.")
                segments.append({'type': 'text', 'text': f"[[SVG_{svg_id}]]", 'style': default_style})
                
        elif match.group(4):
            # Texte sans balise
            content = match.group(4)
            if content:
                segments.append({'type': 'text', 'text': content, 'style': default_style})

    # Correction des espaces entre segments
    corrected_segments = []
    for i, seg in enumerate(segments):
        if corrected_segments:
            prev_seg = corrected_segments[-1]
            need_space = False
            if prev_seg['type'] == 'text' and seg['type'] == 'text':
                if not prev_seg['text'].endswith((' ', '\n')) and not seg['text'].startswith((' ', '\n')):
                    need_space = True
            elif prev_seg['type'] == 'text' and seg['type'] == 'svg':
                if not prev_seg['text'].endswith((' ', '\n')):
                    need_space = True
            elif prev_seg['type'] == 'svg' and seg['type'] == 'text':
                if not seg['text'].startswith((' ', '\n')):
                    need_space = True
            if need_space:
                corrected_segments.append({'type': 'text', 'text': ' ', 'style': prev_seg['style']})
        corrected_segments.append(seg)

    # Normalisation des espaces multiples
    for seg in corrected_segments:
        if seg['type'] == 'text':
            seg['text'] = re.sub(r' +', ' ', seg['text'])

    return corrected_segments



def int_to_rgb(color_int):
    """Convertit une couleur entière en tuple RGB normalisé"""
    red = (color_int >> 16) & 255
    green = (color_int >> 8) & 255
    blue = color_int & 255
    return (red/255.0, green/255.0, blue/255.0)


def calculate_reflow(segments, blockdata, svgmappingdata, font_scale=1.0, char_space=0, **kwargs):
    """
    Calcule le wrapping des lignes pour un bloc.
    
    Intègre :
    - font_scale / char_space
    - is_list, list_indent, list_hang (nouvelle logique)
    
    segments : liste de segments {'type': 'text'|'svg', ...}
    blockdata : dict avec au minimum:
        - 'max_allowable_width'
        - éventuellement:
            - 'is_list' (bool)
            - 'list_indent' (float)
            - 'list_hang' (bool)
    """
    # Compatibilité éventuelle avec anciens kwargs
    if 'fontscale' in kwargs:
        font_scale = kwargs['fontscale']
    if 'charspace' in kwargs:
        char_space = kwargs['charspace']

    lines = []
    current_line = []
    current_width = 0.0

    base_maxwidth = float(blockdata.get('max_allowable_width', 0) or 0.0)

    # Nouveaux paramètres de liste
    is_list = blockdata.get('is_list', False)
    list_indent = float(blockdata.get('list_indent', 0) or 0.0)
    list_hang = blockdata.get('list_hang', True)

    # Compteur de lignes pour appliquer la logique liste
    line_index = 0

    # Fonction interne pour obtenir la largeur max effective pour la ligne en cours
    def get_effective_maxwidth(line_idx: int) -> float:
        """
        Pour les listes, on réduit la largeur disponible si le texte est censé commencer après le retrait.
        - Ligne 0 (première) : on applique le retrait (texte commence après la puce).
        - Lignes suivantes :
            - si list_hang == True : même retrait (texte sous le début de la première ligne).
            - sinon : pas de retrait (texte sous la puce).
        Pour les blocs normaux, on renvoie base_maxwidth.
        """
        if not is_list:
            return base_maxwidth

        if line_idx == 0:
            # 1ère ligne : puce + texte décalé
            return max(0.0, base_maxwidth - list_indent)
        else:
            if list_hang:
                # Lignes suivantes alignées sous le texte (même retrait)
                return max(0.0, base_maxwidth - list_indent)
            else:
                # Lignes suivantes sous la puce : pas de retrait dans le wrapping
                return base_maxwidth

    # Largeur max effective pour la première ligne
    effective_maxwidth = get_effective_maxwidth(line_index)

    for segment in segments:
        if segment['type'] == 'text':
            style = segment['style']
            font = style.get("police", "Helvetica") or "Helvetica"
            size = style.get("taille", 10.5) * font_scale

            # Gestion des sauts de ligne internes
            parts = segment['text'].split('\n')
            for i, part in enumerate(parts):
                if i > 0:
                    # On pousse la ligne courante et démarre une nouvelle
                    if current_line:
                        lines.append(current_line)
                    current_line = []
                    current_width = 0.0
                    line_index += 1
                    effective_maxwidth = get_effective_maxwidth(line_index)

                if not part:
                    # Ligne vide : on laisse la ligne telle quelle (sera traitée comme ligne vide)
                    continue

                # On découpe en tokens (espaces + mots)
                tokens = re.findall(r'\s+|\S+', part)

                for token in tokens:
                    # Largeur du token + char_space éventuel
                    base_w = pdfmetrics.stringWidth(token, font, size)
                    extra_cs = (len(token) * char_space) if token.strip() else 0.0
                    w = base_w + extra_cs

                    # Si on dépasse la largeur max et qu'il y a déjà du contenu sur la ligne, on coupe
                    if token.strip() and current_width + w > effective_maxwidth and current_line:
                        lines.append(current_line)
                        current_line = []
                        current_width = 0.0
                        line_index += 1
                        effective_maxwidth = get_effective_maxwidth(line_index)

                    current_line.append({
                        'type': 'text',
                        'text': token,
                        'width': w,
                        'style': style,
                        'font_scale': font_scale,
                        'char_space': char_space
                    })
                    current_width += w

        elif segment['type'] == 'svg':
            props = segment['props']
            # Hauteur basée sur la taille de référence * font_scale
            h = props['taille_texte_reference'] * font_scale
            w = h * props['ratio_largeur_hauteur']

            # Si le SVG dépasse la largeur restante de la ligne, on coupe la ligne
            if current_width + w > effective_maxwidth and current_line:
                lines.append(current_line)
                current_line = []
                current_width = 0.0
                line_index += 1
                effective_maxwidth = get_effective_maxwidth(line_index)

            current_line.append({
                'type': 'svg',
                'id': segment['id'],
                'props': props,
                'width': w,
                'height': h,
                'font_scale': font_scale
            })
            current_width += w

    if current_line:
        lines.append(current_line)

    return lines

def estimate_original_line_spacing(block):
    """
    Estime l'interligne (distance baseline-baseline) d'origine pour un bloc,
    basée sur default_style['taille'] et interligne_normal.
    """
    default_style = block.get('default_style') or {}
    base_font_size = default_style.get('taille', 10.5)
    interligne_normal = block.get('interligne_normal', 1.2)
    return base_font_size * interligne_normal


def estimate_box_height_from_original(block):
    """
    Estime la hauteur physique de la box d'un bloc en utilisant :
    - lignes_originales
    - line_spacing_original (dérivé de la police et de interligne_normal)
    """
    lignes_originales = block.get('lignes_originales', 1) or 1
    line_spacing_original = estimate_original_line_spacing(block)
    return lignes_originales * line_spacing_original


def estimate_line_spacing_for_scale(block, font_scale):
    """
    Estime l'interligne à utiliser pour un font_scale donné
    (interligne proportionnel à la taille de police réduite).
    """
    default_style = block.get('default_style') or {}
    base_font_size = default_style.get('taille', 10.5)
    interligne_normal = block.get('interligne_normal', 1.2)
    return (base_font_size * font_scale) * interligne_normal


def compress_block_lines(segments, block_for_reflow, svg_mapping_data, max_lines_original):
    """
    Essaie de faire tenir le texte dans le bloc en jouant sur:
    - font_scale (de 1.0 à 0.65)
    - char_space (de 0.0 à -0.20 par pas de -0.05)

    Logique:
    - On fixe la hauteur de box d'après la situation d'origine (font_scale=1).
    - Pour chaque (fs, cs) en boucle imbriquée:
        1) On calcule les lignes.
        2) Si len(lines) <= max_lines_original -> OK avec interligne original.
        3) Sinon, on calcule la capacité physique max_lines_fs avec interligne "scaled":
           - si len(lines) <= max_lines_fs -> OK (plus de lignes, même hauteur de box).
    - Si rien ne tient, on revient à fs=1.0, cs=0.0.
    """
    # Sécurité : si on n'a pas d'info sur max_lines_original, on considère "pas de limite"
    if max_lines_original is None:
        max_lines_original = block_for_reflow.get('lignes_originales')

    if max_lines_original is None:
        max_lines_original = 9999  # gros nombre, mais en pratique tes blocs auront la clé

    # Hauteur de box d'après la situation originale
    box_height = estimate_box_height_from_original(block_for_reflow)

    # 1) Tentative initiale sans compression
    base_fs = 1.0
    base_cs = 0.0
    lines = calculate_reflow(
        segments,
        block_for_reflow,
        svg_mapping_data,
        font_scale=base_fs,
        char_space=base_cs
    )

    # Si ça tient déjà dans max_lines_original, on ne fait rien
    if len(lines) <= max_lines_original:
        return lines, base_fs, base_cs, "original_spacing"

    font_scale_candidates = [1.0, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65]
    char_space_candidates = [0.0, -0.05, -0.10, -0.15, -0.20]

    best_fs = base_fs
    best_cs = base_cs
    best_mode = "original_spacing"
    is_fitted = False

    for fs in font_scale_candidates:
        for cs in char_space_candidates:
            lines_test = calculate_reflow(
                segments,
                block_for_reflow,
                svg_mapping_data,
                font_scale=fs,
                char_space=cs
            )
            n_lines = len(lines_test)

            # Cas 1 : on arrive à tenir dans le nombre de lignes original
            if n_lines <= max_lines_original:
                lines = lines_test
                best_fs = fs
                best_cs = cs
                best_mode = "original_spacing"  # on gardera l'interligne original
                is_fitted = True
                if fs != 1.0 or cs != 0.0:
                    print(f" {block_for_reflow.get('id', '?')} -> Compression (n_lignes={n_lines} <= {max_lines_original}) : fs={fs:.2f}, cs={cs:.2f}, mode=original")
                break

            # Cas 2 : plus de lignes que l'original, mais peut-on tenir en hauteur ?
            line_spacing_scaled = estimate_line_spacing_for_scale(block_for_reflow, fs)
            if line_spacing_scaled <= 0:
                continue

            max_lines_fs = int(box_height // line_spacing_scaled)

            if n_lines <= max_lines_fs:
                # On accepte plus de lignes tant que la hauteur physique reste dans la box
                lines = lines_test
                best_fs = fs
                best_cs = cs
                best_mode = "scaled_spacing"
                is_fitted = True
                print(
                    f" {block_for_reflow.get('id', '?')} -> Compression (n_lignes={n_lines} > {max_lines_original}, "
                    f"mais n_lignes <= {max_lines_fs} possible) : fs={fs:.2f}, cs={cs:.2f}, mode=scaled"
                )
                break

        if is_fitted:
            break

    if not is_fitted:
        # Fallback : garder la version non compressée (plus lisible même si ça déborde)
        print(
            f" [AVERTISSEMENT] {block_for_reflow.get('id', '?')} : impossible de tenir en hauteur de box "
            f"même avec fs>=0.65 et cs>=-0.20. Retour à fs=1.0, cs=0.0."
        )
        lines = calculate_reflow(
            segments,
            block_for_reflow,
            svg_mapping_data,
            font_scale=base_fs,
            char_space=base_cs
        )
        best_fs = base_fs
        best_cs = base_cs
        best_mode = "original_spacing"

    return lines, best_fs, best_cs, best_mode



def draw_text_block(c, block, lines, svg_cache):
    """
    Dessine un bloc de texte (avec éventuellement liste) sur le canvas.
    Gère le rendu SVG inline.
    """
    page_height = c._pagesize[1]
    
    align = block.get('align', 'left')
    x_block_start = block['position_xy'][0]
    y_top = page_height - block['position_xy'][1]
    block_width = block['max_allowable_width']

    is_list = block.get('is_list', False)
    bullet_text = block.get('list_bullet', '')
    list_indent = float(block.get('list_indent', 0) or 0.0)
    list_hang = block.get('list_hang', True)

    compression_mode = block.get('compression_spacing_mode', None)

    y_curr = y_top
    # Ajustement baseline pour la première ligne
    if lines and lines[0]:
        first_seg = next((s for s in lines[0] if s['type'] == 'text'), None)
        if first_seg:
            fs = first_seg.get('font_scale', 1.0)
            size = first_seg['style'].get('taille', 10)
            y_curr -= (size * fs) * 0.8
        elif lines[0][0]['type'] == 'svg':
            y_curr -= lines[0][0]['height']

    total_lines = len(lines)

    for line_idx, line in enumerate(lines):
        max_h = 0
        line_content_width = 0
        nb_spaces = 0

        for s in line:
            if s['type'] == 'text':
                h = s['style'].get('taille', 10) * s.get('font_scale', 1.0)
                max_h = max(max_h, h)
                line_content_width += s['width']
                nb_spaces += s['text'].count(' ')
            else:
                max_h = max(max_h, s['height'])
                line_content_width += s['width']

        default_style = block.get('default_style', {"police": "Helvetica", "taille": 10, "couleur": 0})
        default_font_size = default_style.get('taille', 10)
        interligne_normal = block.get('interligne_normal', default_font_size * 1.2)

        if compression_mode == "original_spacing":
            spacing = default_font_size * (interligne_normal / default_font_size)
        else:
            spacing = max_h * (interligne_normal / default_font_size) if default_font_size else max_h * 1.2

        # Alignement horizontal
        x_base = x_block_start
        use_indent_this_line = False

        if is_list:
            if line_idx == 0:
                use_indent_this_line = True
            else:
                use_indent_this_line = list_hang
            
            if use_indent_this_line:
                x_base += list_indent

        usable_width = block_width - (list_indent if (is_list and use_indent_this_line) else 0)

        x_curr = x_base
        word_space = 0.0

        if align == 'center':
            x_curr += max(0, (usable_width - line_content_width) / 2.0)
        elif align == 'right':
            x_curr += max(0, usable_width - line_content_width)
        elif align == 'justify':
            is_last_line = (line_idx == total_lines - 1)
            if (not is_last_line) and nb_spaces > 0:
                space_missing = usable_width - line_content_width
                if space_missing > 0:
                    word_space = space_missing / nb_spaces

        # Dessin de la puce
        if is_list and line_idx == 0 and bullet_text:
            global_styles = block.get('global_styles', {})
            bullet_segments = parse_tagged_text(bullet_text, default_style, global_styles, {})
            x_bullet = x_block_start
            
            for seg in bullet_segments:
                if seg['type'] == 'text':
                    st = seg['style']
                    c.setFont(st.get('police', 'Helvetica'), st.get('taille', 10))
                    c.setFillColorRGB(*int_to_rgb(st.get('couleur', 0)))
                    c.drawString(x_bullet, y_curr, seg['text'])
                    x_bullet += pdfmetrics.stringWidth(seg['text'], st.get('police', 'Helvetica'), st.get('taille', 10))

        # Dessin du contenu de la ligne
        for seg in line:
            if seg['type'] == 'text':
                st = seg['style']
                fs = seg.get('font_scale', 1.0)
                font_name = st.get('police', 'Helvetica')
                font_size = st.get('taille', 10) * fs

                c.setFont(font_name, font_size)
                c.setFillColorRGB(*int_to_rgb(st.get('couleur', 0)))

                t_obj = c.beginText(x_curr, y_curr)
                t_obj.setCharSpace(seg.get('char_space', 0))
                if word_space > 0:
                    t_obj.setWordSpace(word_space)

                t_obj.textOut(seg['text'])
                c.drawText(t_obj)
                
                seg_spaces = seg['text'].count(' ')
                x_curr += seg['width'] + (seg_spaces * word_space)

            elif seg['type'] == 'svg':
                svg_id = seg['id']
                props = seg['props']
                w_target = seg['width']
                h_target = seg['height']
                
                # 1. Récupération du chemin fichier
                file_name = props.get('file', '')
                file_path = os.path.join(SVG_DIR, file_name) # Assurez-vous que SVG_DIR est accessible ici
                
                if not os.path.exists(file_path):
                    # Fichier introuvable -> Carré rouge
                    c.setFillColorRGB(1, 0, 0)
                    c.rect(x_curr, y_curr, w_target, h_target, fill=1)
                
                else:
                    # 2. Distinction selon l'extension
                    ext = os.path.splitext(file_name)[1].lower()
                    
                    if ext in ['.png', '.jpg', '.jpeg']:
                        # --- GESTION DES IMAGES RASTER (PNG/JPG) ---
                        # ReportLab dessine les images avec le coin bas-gauche en (x, y)
                        # ajustement_vertical : souvent positif pour remonter l'image par rapport à la baseline
                        v_adjust = props.get('ajustement_vertical', 0)
                        
                        try:
                            # drawImage(image, x, y, width, height, mask='auto')
                            # mask='auto' permet la transparence pour les PNG
                            c.drawImage(file_path, x_curr, y_curr + v_adjust, width=w_target, height=h_target, mask='auto')
                        except Exception as e:
                            print(f"[ERREUR IMG] {file_name} : {e}")
                            c.setFillColorRGB(1, 0, 0)
                            c.rect(x_curr, y_curr, w_target, h_target, fill=1)

                    elif ext == '.svg':
                        # --- GESTION DES SVG (Code existant amélioré) ---
                        if svg_id not in svg_cache:
                            try:
                                svg_cache[svg_id] = svg2rlg(file_path)
                            except Exception as e:
                                print(f"[ERREUR SVG] {file_name} : {e}")

                        drawing = svg_cache.get(svg_id)
                        
                        if drawing:
                            c.saveState()
                            c.translate(x_curr, y_curr)
                            
                            # Calcul de l'échelle
                            orig_w = getattr(drawing, 'width', 0) or w_target
                            orig_h = getattr(drawing, 'height', 0) or h_target
                            # Sécurité division par zéro
                            if orig_w <= 0: orig_w = 1
                            if orig_h <= 0: orig_h = 1
                                
                            sx = w_target / orig_w
                            sy = h_target / orig_h
                            c.scale(sx, sy)
                            
                            v_adjust = props.get('ajustement_vertical', 0)
                            # renderPDF dessine depuis 0,0
                            renderPDF.draw(drawing, c, 0, v_adjust/sy)
                            c.restoreState()
                        else:
                            # Echec SVG -> Carré rouge
                            c.setFillColorRGB(1, 0, 0)
                            c.rect(x_curr, y_curr, w_target, h_target, fill=1)
                    
                    else:
                        print(f"[ERREUR] Format non supporté : {ext}")
                        c.setFillColorRGB(1, 0, 0)
                        c.rect(x_curr, y_curr, w_target, h_target, fill=1)

                x_curr += w_target


        y_curr -= spacing


def redistribute_merged_text_simple(merged_text, group_blocks_sorted):
    """
    ✅ VERSION SIMPLE : Découpe le texte avec balises proportionnellement selon lignes_originales.
    Préserve TOUTES les balises de style car on découpe la chaîne brute.
    
    Args:
        merged_text: Texte complet avec balises <gsX>...</gsX>
        group_blocks_sorted: Blocs triés par merge_order
    
    Returns:
        Dict {block_id: text_portion}
    """
    result = {}
    
    # Calculer le total de lignes
    total_lines = sum(b.get('lignes_originales', 1) for b in group_blocks_sorted)
    
    if total_lines == 0:
        return result
    
    remaining_text = merged_text.strip()
    
    for i, block in enumerate(group_blocks_sorted):
        block_id = block['id']
        block_lines = block.get('lignes_originales', 1)
        
        if i == len(group_blocks_sorted) - 1:
            # Dernier bloc : tout ce qui reste
            result[block_id] = remaining_text
        else:
            # Calculer la proportion de texte pour ce bloc
            line_ratio = block_lines / total_lines
            target_length = int(len(remaining_text) * line_ratio)
            
            # Trouver une position de coupe propre (espace ou fin de balise)
            cut_position = target_length
            
            # Chercher un espace proche, en évitant de couper au milieu d'une balise
            search_range = min(50, len(remaining_text) - target_length)
            
            for offset in range(search_range):
                pos = target_length + offset
                if pos >= len(remaining_text):
                    break
                    
                char = remaining_text[pos]
                
                # Couper sur un espace, mais pas à l'intérieur d'une balise
                if char == ' ':
                    # Vérifier qu'on n'est pas entre < et >
                    left_part = remaining_text[:pos]
                    open_tags = left_part.count('<')
                    close_tags = left_part.count('>')
                    
                    if open_tags == close_tags:
                        # Balises équilibrées, position de coupe valide
                        cut_position = pos
                        break
            
            # Extraire la portion pour ce bloc
            result[block_id] = remaining_text[:cut_position].strip()
            remaining_text = remaining_text[cut_position:].strip()
            
            # Ajuster total_lines pour les blocs suivants
            total_lines -= block_lines
    
    return result


def redistribute_merged_text_fillstrategy(
    merged_text,
    group_blocks_sorted,
    svg_mapping_data,
    global_styles,
    font_scale=1.0,
    char_space=0.0
):
    """
    ✅ CORRECTION COMPLÈTE : Redistribue le texte fusionné en remplissant séquentiellement les blocs.
    Préserve TOUTES les balises de style.
    
    Algorithme :
    1. Parser le texte avec balises en segments
    2. Remplir le bloc 0 jusqu'à sa capacité (lignes_originales)
    3. Passer au bloc 1, etc.
    4. Reconstruire le texte avec balises pour chaque bloc
    
    Returns:
        Dict {block_id: text_portion} ou None si débordement total
    """
    result = {}
    first_block = group_blocks_sorted[0]
    block_type = first_block.get('block_type', 'paragraph')
    
    # ✅ Utiliser le default_style du PREMIER bloc comme référence
    default_style_ref = first_block.get('default_style_ref') or first_block.get('default_style')
    resolved_default_style = global_styles.get(default_style_ref, default_style_ref) if isinstance(default_style_ref, str) else default_style_ref
    
    processed_text = format_list_items_for_reflow(merged_text, block_type)
    
    # Parser le texte en segments (préserve les balises)
    segments = parse_tagged_text(processed_text, resolved_default_style, global_styles, svg_mapping_data)
    
    segment_idx = 0
    
    # Remplir séquentiellement chaque bloc
    for block in group_blocks_sorted:
        block_lines_available = block['lignes_originales']
        block_segments = []
        
        # Remplir ce bloc jusqu'à sa capacité
        while segment_idx < len(segments):
            current_seg = segments[segment_idx]
            
            # Tester si on peut ajouter le segment entier
            test_segments = block_segments + [current_seg]
            test_lines = calculate_reflow(test_segments, block, svg_mapping_data, font_scale=font_scale, char_space=char_space)
            
            if len(test_lines) <= block_lines_available:
                # Le segment entier tient, l'ajouter
                block_segments.append(current_seg)
                segment_idx += 1
            else:
                # Débordement : essayer de découper si c'est du texte
                if current_seg['type'] == 'text' and current_seg['text'].strip():
                    # Découper le texte mot par mot
                    words = current_seg['text'].split()
                    words_fitted = 0
                    
                    # Trouver combien de mots peuvent tenir
                    for word_count in range(1, len(words) + 1):
                        partial_text = ' '.join(words[:word_count])
                        partial_seg = {'type': 'text', 'text': partial_text, 'style': current_seg['style']}
                        
                        test_segments_partial = block_segments + [partial_seg]
                        test_lines_partial = calculate_reflow(test_segments_partial, block, svg_mapping_data, font_scale=font_scale, char_space=char_space)
                        
                        if len(test_lines_partial) <= block_lines_available:
                            words_fitted = word_count
                        else:
                            break
                    
                    if words_fitted > 0:
                        # Ajouter la partie qui tient
                        fitted_text = ' '.join(words[:words_fitted])
                        fitted_seg = {'type': 'text', 'text': fitted_text, 'style': current_seg['style']}
                        block_segments.append(fitted_seg)
                        
                        # Garder le reste pour le prochain bloc
                        remaining_text = ' '.join(words[words_fitted:])
                        if remaining_text.strip():
                            segments[segment_idx] = {'type': 'text', 'text': remaining_text, 'style': current_seg['style']}
                        else:
                            segment_idx += 1
                    
                    # Bloc plein, passer au suivant
                    break
                else:
                    # SVG ou texte vide : ne peut pas être découpé, passer au bloc suivant
                    break
        
        # ✅ Reconstruire le texte AVEC balises pour ce bloc
        result[block['id']] = _reconstruct_text_with_balises_preserved(block_segments, global_styles)
    
    # Si des segments restent non distribués, signaler débordement
    if segment_idx < len(segments):
        return None
    
    return result


def _reconstruct_text_with_balises_preserved(segments, global_styles):
    """
    ✅ NOUVELLE FONCTION : Reconstruit le texte en préservant EXACTEMENT les balises.
    
    Args:
        segments: Liste de segments avec style
        global_styles: Dict des styles globaux
    
    Returns:
        Texte avec balises <gsX>...</gsX>
    """
    # Créer un mapping inverse : (police, taille, couleur) -> gsX
    style_to_tag = {}
    for gs_tag, gs_style in global_styles.items():
        if isinstance(gs_style, dict):
            style_key = (
                gs_style.get('police'),
                gs_style.get('taille'),
                gs_style.get('couleur')
            )
            style_to_tag[style_key] = gs_tag
    
    parts = []
    
    for seg in segments:
        if seg['type'] == 'text':
            text = seg.get('text', '')
            if not text:
                continue
            
            style = seg['style']
            style_key = (
                style.get('police'),
                style.get('taille'),
                style.get('couleur')
            )
            
            # Trouver le tag global correspondant
            gs_tag = style_to_tag.get(style_key)
            
            if gs_tag:
                # Ajouter avec balise
                parts.append(f"<{gs_tag}>{text}</{gs_tag}>")
            else:
                # Pas de tag trouvé : texte sans balise
                parts.append(text)
        
        elif seg['type'] == 'svg':
            parts.append(f"<svg id=\"{seg['id']}\"/>")
    
    return ''.join(parts)


def _reconstruct_text_with_tags(segments, global_styles):
    """
    ✅ NOUVELLE FONCTION : Reconstruit le texte avec balises à partir des segments.
    Préserve les balises de style <gsX>.
    
    Args:
        segments: Liste de segments {'type': 'text', 'text': '...', 'style': {...}}
        global_styles: Dict des styles globaux
    
    Returns:
        Texte avec balises <gsX>...</gsX>
    """
    parts = []
    
    # Créer un mapping inverse : (police, taille, couleur) -> gsX
    style_to_tag = {}
    for gs_tag, gs_style in global_styles.items():
        if isinstance(gs_style, dict):
            style_key = (
                gs_style.get('police'),
                gs_style.get('taille'),
                gs_style.get('couleur')
            )
            style_to_tag[style_key] = gs_tag
    
    # Variable pour traquer le dernier tag utilisé (pour éviter les balises redondantes)
    last_tag = None
    
    for seg in segments:
        if seg['type'] == 'text':
            text = seg['text']
            if not text:
                continue
                
            style = seg['style']
            
            # Trouver le tag global correspondant
            style_key = (
                style.get('police'),
                style.get('taille'),
                style.get('couleur')
            )
            
            matching_tag = style_to_tag.get(style_key)
            
            if matching_tag and matching_tag != last_tag:
                # Style différent du texte précédent, ajouter les balises
                parts.append(f"<{matching_tag}>{text}</{matching_tag}>")
                last_tag = matching_tag
            elif matching_tag and matching_tag == last_tag:
                # Même style que le précédent, continuer la balise
                parts.append(f"<{matching_tag}>{text}</{matching_tag}>")
            else:
                # Pas de tag trouvé (style par défaut)
                parts.append(text)
                last_tag = None
                
        elif seg['type'] == 'svg':
            parts.append(f"<svg id=\"{seg['id']}\"/>")
            last_tag = None
    
    return ''.join(parts)


def create_text_overlay_pdf(format_data, translation_data, svg_mapping_data, temp_file, global_styles):
    """Crée un PDF transparent contenant SEULEMENT le texte traduit et les SVGs, compatible styles globaux."""
    print(f"\n--- CRÉATION DU PDF TEXTE TRANSPARENT: {temp_file} ---")
    first_page_dims = format_data['pages'][0]['dimensions']
    c = canvas.Canvas(temp_file, pagesize=(first_page_dims[0], first_page_dims[1]))
    svg_cache = {}

    # Fonction utilitaire interne pour résoudre le style par référence globale
    def resolve_style_ref(style_ref, global_styles, fallback_style):
        if isinstance(style_ref, str):
            return global_styles.get(style_ref, fallback_style)
        elif isinstance(style_ref, dict):
            return style_ref
        else:
            return fallback_style

    for page_data in format_data.get('pages', []):
        c.setPageSize(page_data['dimensions'])
        print(f" [PAGE {page_data['page_number']}] Création texte transparent...")

        merged_groups_redistribution = {}
        merged_groups_compression = {}

        # ✅ CORRECTION : Gestion des groupes fusionnés avec remplissage séquentiel
        for block in page_data.get('blocks', []):
            merge_group_id = block.get('merge_group_id')
            if merge_group_id and merge_group_id not in merged_groups_redistribution:
                translated_text = translation_data.get(merge_group_id)
                if translated_text:
                    group_blocks = [b for b in page_data.get('blocks', [])
                                   if b.get('merge_group_id') == merge_group_id]
                    group_blocks_sorted = sorted(group_blocks, key=lambda b: b.get('merge_order', 0))

                    redistributed = None
                    is_fitted = False

                    # ✅ Essayer différentes compressions jusqu'à ce que tout tienne
                    for fs_test in [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7]:
                        cs_test = -0.1 if fs_test > 0.85 else -0.2
                        redistributed_test = redistribute_merged_text_fillstrategy(
                            translated_text,
                            group_blocks_sorted,
                            svg_mapping_data,
                            global_styles,
                            font_scale=fs_test,
                            char_space=cs_test
                        )
                        if redistributed_test is not None:
                            redistributed = redistributed_test
                            merged_groups_compression[merge_group_id] = (fs_test, cs_test)
                            if fs_test < 1.0:
                                print(f" [COMPRESSION GROUPE] {merge_group_id} - fs={fs_test:.2f}, cs={cs_test:.2f}")
                            is_fitted = True
                            break

                    if not is_fitted:
                        # Compression maximale forcée
                        redistributed = redistribute_merged_text_fillstrategy(
                            translated_text,
                            group_blocks_sorted,
                            svg_mapping_data,
                            global_styles,
                            font_scale=0.65,
                            char_space=-0.3
                        )
                        merged_groups_compression[merge_group_id] = (0.65, -0.3)
                        print(f" -> [AVERTISSEMENT] Compression maximale forcée pour {merge_group_id}")

                    merged_groups_redistribution[merge_group_id] = redistributed

        block_count = 0
        for block in page_data.get('blocks', []):
            merge_group_id = block.get('merge_group_id')
            if merge_group_id:
                translated_text = merged_groups_redistribution.get(merge_group_id, {}).get(block['id'])
            else:
                translated_text = translation_data.get(block['id'])

            if not translated_text:
                print(f"[DEBUG] Bloc {block['id']} ignoré (pas de texte)")
                continue

            block_count += 1

            # ✅ CORRECTION : Pour les blocs fusionnés, utiliser le default_style du PREMIER bloc du groupe
            if merge_group_id:
                # Trouver le premier bloc du groupe (merge_order=0)
                group_blocks = [b for b in page_data.get('blocks', []) 
                               if b.get('merge_group_id') == merge_group_id]
                first_block = min(group_blocks, key=lambda b: b.get('merge_order', 0))
                default_style_ref = first_block.get('default_style_ref', first_block.get('default_style'))
            else:
                default_style_ref = block.get('default_style_ref', block.get('default_style'))
            
            # Résolution du style par défaut via la référence globale
            resolved_default_style = resolve_style_ref(
                default_style_ref,
                global_styles,
                {"police": "Helvetica", "taille": 10.5, "couleur": 0}
            )

            # IMPORTANT - IGNORER LES STYLES LOCAUX
            block_styles = {}  # On ne prend plus en compte 'styles' ou 'style_refs'

            block_type = block.get('block_type', 'paragraph')
            processed_text = format_list_items_for_reflow(translated_text, block_type)

            # print("Clés de global_styles :", list(global_styles.keys())[:6])
            # print("Exemple de texte transmis :", processed_text[:100])

            # Parsing du texte avec styles globaux uniquement
            segments = parse_tagged_text(processed_text, resolved_default_style, global_styles, svg_mapping_data)

            block_for_reflow = dict(block)
            block_for_reflow['default_style'] = resolved_default_style
            block_for_reflow['global_styles'] = global_styles  # pour la puce stylée
            
            if merge_group_id and merge_group_id in merged_groups_compression:
                font_scale, char_space = merged_groups_compression[merge_group_id]
                lines = calculate_reflow(segments, block_for_reflow, svg_mapping_data, font_scale=font_scale, char_space=char_space)
            else:
                # 1. Premier calcul standard (fs=1.0)
                lines = calculate_reflow(segments, block_for_reflow, svg_mapping_data)
                
                # 2. Si ça déborde, on lance la compression intelligente
                if len(lines) > block['lignes_originales']:
                    # Estimation mathématique brute pour cibler la zone probable
                    estimated_ratio = (block['lignes_originales'] / len(lines)) ** 0.75
                    
                    is_fitted = False
                    
                    # Liste de valeurs à tester, du plus grand (qualité max) au plus petit.
                    # On inclut des valeurs standards et l'estimation calculée pour affiner.
                    candidates = {0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6}
                    # On ajoute l'estimation (bornée) pour avoir une chance de tomber juste
                    safe_estimate = max(0.55, min(0.98, estimated_ratio))
                    candidates.add(safe_estimate)
                    
                    # Tri décroissant impératif : on veut la plus grande police qui rentre
                    test_range = sorted(list(candidates), reverse=True)

                    for fs_test in test_range:
                        # Ajustement léger de l'espacement lettres pour aider la compression
                        cs_test = -0.1 if fs_test > 0.85 else -0.2
                        
                        lines_test = calculate_reflow(segments, block_for_reflow, svg_mapping_data, font_scale=fs_test, char_space=cs_test)
                        
                        if len(lines_test) <= block['lignes_originales']:
                            lines = lines_test
                            # On n'affiche le message que si la compression est significative (< 0.98)
                            if fs_test < 0.98:
                                print(f" {block_for_reflow['id']} -> Compression dynamique appliquée : fs={fs_test:.2f}, cs={cs_test:.2f}")
                            is_fitted = True
                            break
                    
                    if not is_fitted:
                        print(f" -> [AVERTISSEMENT] {block_for_reflow['id']} : Impossible de faire tenir le texte (Best effort conservé).")
                        # En désespoir de cause, on garde la dernière tentative (la plus petite) 
                        # ou on pourrait forcer un crop, mais mieux vaut un texte petit qui déborde un peu qu'un texte invisible.


            draw_text_block(c, block_for_reflow, lines, svg_cache)

        print(f" [PAGE {page_data['page_number']}] {block_count} blocs traités")
        c.showPage()

    c.save()
    print(f"[OK] PDF texte transparent créé: {temp_file}")




def merge_template_and_text(template_pdf, text_pdf, output_pdf):
    """Fusionne le template graphique et le PDF texte transparent"""
    print(f"\n--- FUSION DU TEMPLATE ET DU TEXTE ---")
    try:
        doc_template = fitz.open(template_pdf)
        doc_text = fitz.open(text_pdf)
        doc_final = fitz.open()

        for page_num in range(min(len(doc_template), len(doc_text))):
            template_page = doc_template[page_num]
            final_page = doc_final.new_page(width=template_page.rect.width, height=template_page.rect.height)
            final_page.show_pdf_page(final_page.rect, doc_template, page_num)
            final_page.show_pdf_page(final_page.rect, doc_text, page_num)

        doc_final.save(output_pdf)
        doc_final.close(); doc_text.close(); doc_template.close()
        print(f"[OK] PDF final créé: {output_pdf}")
    except Exception as e:
        print(f"[ERREUR] Fusion échouée: {e}")
        raise


# --- SCRIPT PRINCIPAL ---
# def main():
    # parser = argparse.ArgumentParser(description="Étape 3: Reconstruit le PDF traduit en utilisant le template graphique.")
    # parser.add_argument("base_name", help="Nom de base des fichiers projet.")
    # parser.add_argument("lang_code", help="Code de la langue de traduction (ex: FR).")
    # args = parser.parse_args()

    # format_file = f"{args.base_name}_formatage.json"
    # translation_file = f"{args.base_name}_pour_traduction_{args.lang_code}.json"
    # template_file = f"{args.base_name}_template.pdf"
    # svg_mapping_file = f"{args.base_name}{SVG_MAPPING_FILENAME_SUFFIX}"
    # temp_text_file = f"{args.base_name}_temp_text.pdf"
    # output_pdf = f"{args.base_name}_traduit_{args.lang_code}.pdf"

    # print("--- DÉMARRAGE DU SCRIPT DE RECONSTRUCTION V3 (TEMPLATE) ---")
    # required_files = [
        # (format_file, "Fichier de formatage"),
        # (translation_file, "Fichier de traduction"),
        # (template_file, "Template PDF"),
        # (svg_mapping_file, "Mapping SVG")
    # ]

    # missing_files = [(name, path) for path, name in required_files if not os.path.exists(path)]

    # if missing_files:
        # print("[ERREUR] Fichiers requis manquants:")
        # for name, path in missing_files:
            # print(f"  - {name}: {path}")
        # return

    # try:
        # with open(format_file, 'r', encoding='utf-8') as f:
            # format_data = json.load(f)
            
        # # Extraire global_styles
        # global_styles = format_data.get('global_styles', {})
        # print(f"\n[INFO] {len(global_styles)} styles globaux chargés")
        
        # # Validation de la structure des styles
        # for style_key, style_val in global_styles.items():
            # if not isinstance(style_val, dict):
                # print(f"[ERREUR] global_styles[{style_key}] n'est pas un dict: {type(style_val)} = {style_val}")
            # elif 'police' not in style_val or 'taille' not in style_val or 'couleur' not in style_val:
                # print(f"[AVERTISSEMENT] Style {style_key} incomplet: {style_val}")
        
        # # Charger traduction
        # with open(translation_file, 'r', encoding='utf-8') as f:
            # translation_items = json.load(f)
            # translation_data = {}
            # merged_groups_data = {}
            
            # for item in translation_items:
                # item_id = item['id']
                # translated_text = item.get('target', '') or item['source']
                # translation_data[item_id] = translated_text
                
                # if item.get('is_merged_group'):
                    # merged_groups_data[item_id] = {
                        # 'target': translated_text,
                        # 'original_ids': item.get('original_ids', []),
                        # 'block_count': item.get('block_count', 0)
                    # }
        
        # # Charger SVG mapping
        # with open(svg_mapping_file, 'r', encoding='utf-8') as f:
            # svg_mapping_data = json.load(f)
        
        # # Configuration des polices (maintenant avec global_styles)
        # if not setup_fonts(FONT_MAPPING_FILE, FONT_DIR, discover_fonts(format_data)):
            # return

        # # Création du PDF
        # create_text_overlay_pdf(format_data, translation_data, svg_mapping_data, temp_text_file, global_styles)
        # merge_template_and_text(template_file, temp_text_file, output_pdf)

        # # Nettoyage
        # if os.path.exists(temp_text_file):
            # os.remove(temp_text_file)
            # print(f"[OK] Fichier temporaire supprimé.")

        # print(f"\n[SUCCESS] PDF traduit généré: {output_pdf}")

    # except Exception as e:
        # print(f"[ERREUR] Échec de la reconstruction: {e}")
        # import traceback
        # traceback.print_exc()


# if __name__ == '__main__':
    # main()



# --- WRAPPER CLASS POUR L'INTERFACE GRAPHIQUE ---

class PDFBuilder:
    def __init__(self, basename, lang_code, project_dir):
        self.basename = basename
        self.lang_code = lang_code
        self.project_dir = project_dir
        
    def build(self):
        # 1. Configuration des chemins absolus
        # On met à jour les variables globales du module pour que les fonctions existantes les utilisent
        global FONT_DIR, SVG_DIR, FONT_MAPPING_FILE
        
        FONT_DIR = os.path.join(self.project_dir, 'fonts')
        SVG_DIR = os.path.join(self.project_dir, 'svgs')
        FONT_MAPPING_FILE = os.path.join(self.project_dir, 'font_mapping.json')
        
        # 2. Chemins des fichiers
        format_file = os.path.join(self.project_dir, f"{self.basename}_formatage.json")
        translation_file = os.path.join(self.project_dir, f"{self.basename}_pour_traduction_{self.lang_code}.json")
        if not os.path.exists(translation_file):
             translation_file = os.path.join(self.project_dir, f"{self.basename}_pour_traduction.json")
             
        template_file = os.path.join(self.project_dir, f"{self.basename}_template.pdf")
        # Attention au suffixe défini en haut du fichier, on suppose '_svg_mapping.json'
        svg_mapping_file = os.path.join(self.project_dir, f"{self.basename}_svg_mapping.json")
        
        temp_text_file = os.path.join(self.project_dir, f"{self.basename}_temp_text.pdf")
        output_pdf = os.path.join(self.project_dir, f"{self.basename}_traduit_{self.lang_code}.pdf")
        
        # 3. Exécution de la logique (copiée de votre main() original)
        print(f"--- BUILD PDF via GUI ({self.lang_code}) ---")
        
        if not os.path.exists(format_file): raise FileNotFoundError(f"Manquant: {format_file}")
        if not os.path.exists(translation_file): raise FileNotFoundError(f"Manquant: {translation_file}")

        with open(format_file, 'r', encoding='utf-8') as f: format_data = json.load(f)
        global_styles = format_data.get('global_styles', {})
        
        with open(translation_file, 'r', encoding='utf-8') as f:
            t_items = json.load(f)
            t_data = {}
            # Adaptation structure liste -> dict
            for item in t_items:
                t_data[item['id']] = item.get('target', '') or item['source']
        
        with open(svg_mapping_file, 'r', encoding='utf-8') as f: svg_mapping_data = json.load(f)

        # Appel des fonctions existantes du module
        if not setup_fonts(FONT_MAPPING_FILE, FONT_DIR, discover_fonts(format_data)):
            raise RuntimeError("Erreur configuration polices")

        create_text_overlay_pdf(format_data, t_data, svg_mapping_data, temp_text_file, global_styles)
        merge_template_and_text(template_file, temp_text_file, output_pdf)
        
        if os.path.exists(temp_text_file): os.remove(temp_text_file)
        
        return output_pdf
