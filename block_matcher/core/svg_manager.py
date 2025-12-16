# core/svg_manager.py
import os
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

# On utilise QImageReader car l'environnement contient déjà PyQt5
from PyQt5.QtGui import QImageReader

class SvgManager:
    """
    Gère le fichier de mapping SVG et le dossier des images.
    """
    def __init__(self, session_root: str, basename: str):
        self.session_root = Path(session_root)
        self.basename = basename
        self.svg_dir = self.session_root / "svgs"
        self.mapping_file = self.session_root / f"{basename}_svg_mapping.json"
        
        self.mapping_data = {}
        self._ensure_environment()
        self.load_mapping()

    def _ensure_environment(self):
        """Vérifie et crée le dossier svgs et le fichier de mapping si nécessaire."""
        if not self.svg_dir.exists():
            self.svg_dir.mkdir(parents=True, exist_ok=True)
            print(f"[SvgManager] Dossier créé : {self.svg_dir}")
        
        if not self.mapping_file.exists():
            self.save_mapping({})  # Créer un fichier vide valide
            print(f"[SvgManager] Fichier mapping créé : {self.mapping_file}")

    def load_mapping(self):
        """Charge les données du fichier JSON."""
        if not self.mapping_file.exists():
            self.mapping_data = {}
            return
        
        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                self.mapping_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[SvgManager] Erreur lecture JSON : {e}")
            self.mapping_data = {}

    def save_mapping(self, data: dict = None):
        """Sauvegarde les données dans le fichier JSON."""
        if data is not None:
            self.mapping_data = data
            
        try:
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.mapping_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SvgManager] Erreur écriture JSON : {e}")

    def _get_image_ratio(self, file_path: Path) -> float:
        """
        Calcule le ratio largeur/hauteur de l'image.
        Pour SVG : utilise viewBox ou width/height.
        Pour PNG/JPG : utilise QImageReader.
        """
        try:
            # 1. Cas SVG : Parsing XML pour trouver la viewBox
            if file_path.suffix.lower() == '.svg':
                try:
                    tree = ET.parse(file_path)
                    root = tree.getroot()
                    
                    # Priorité 1 : viewBox="min-x min-y width height"
                    viewBox = root.get('viewBox')
                    if viewBox:
                        # Séparateurs possibles : espace ou virgule
                        parts = viewBox.replace(',', ' ').split()
                        if len(parts) >= 4:
                            w, h = float(parts[2]), float(parts[3])
                            if h > 0:
                                return round(w / h, 4)
                    
                    # Priorité 2 : width/height attributes
                    w_str = root.get('width')
                    h_str = root.get('height')
                    if w_str and h_str:
                        # Nettoyer les unités (ex: "24px" -> 24.0)
                        def parse_val(v):
                            return float(''.join(c for c in v if c.isdigit() or c == '.'))
                        w = parse_val(w_str)
                        h = parse_val(h_str)
                        if h > 0:
                            return round(w / h, 4)
                except Exception:
                    pass # Échec XML, on passe à la suite (ou défaut)

            # 2. Cas Général (PNG, JPG, ou SVG si parsing XML échoué)
            # QImageReader est robuste et gère aussi le SVG si le plugin QtSVG est là
            reader = QImageReader(str(file_path))
            size = reader.size()
            if size.isValid() and size.height() > 0:
                return round(size.width() / size.height(), 4)
                
        except Exception as e:
            print(f"[SvgManager] Impossible de détecter le ratio pour {file_path.name}: {e}")
            
        return 1.0 # Valeur par défaut de sécurité

    def add_image(self, file_path: str, alias: str) -> bool:
        """
        Ajoute une image au mapping.
        Calcule automatiquement le ratio largeur/hauteur.
        """
        src_path = Path(file_path).resolve()
        
        if not src_path.exists():
            print(f"[SvgManager] Erreur : Le fichier source n'existe pas : {src_path}")
            return False
            
        if not self.svg_dir.exists():
            try:
                self.svg_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"[SvgManager] Erreur critique création dossier : {e}")
                return False

        dest_filename = src_path.name
        dest_path = (self.svg_dir / dest_filename).resolve()
        
        # Gestion copie (éviter WinError 32 si même fichier)
        if src_path == dest_path:
            print(f"[SvgManager] Info : Fichier déjà en place. Pas de copie.")
        elif dest_path.exists():
             print(f"[SvgManager] Info : Utilisation du fichier existant dans svgs/.")
        else:
            try:
                shutil.copy2(src_path, dest_path)
            except Exception as e:
                print(f"[SvgManager] Erreur copie fichier : {e}")
                return False
        
        # --- CALCUL AUTOMATIQUE DU RATIO ---
        detected_ratio = self._get_image_ratio(dest_path)
        print(f"[SvgManager] Ratio détecté pour {dest_filename} : {detected_ratio}")

        # Création de l'entrée JSON
        default_entry = {
            "file": dest_filename,
            "taille_texte_reference": 10.5,
            "ratio_largeur_hauteur": detected_ratio, # <--- ICI
            "ajustement_vertical": 0
        }
        
        self.mapping_data[alias] = default_entry
        self.save_mapping()
        return True

    def remove_entry(self, alias: str) -> bool:
        """Supprime une entrée du mapping."""
        if alias in self.mapping_data:
            del self.mapping_data[alias]
            self.save_mapping()
            return True
        return False

    def update_entry(self, alias: str, key: str, value):
        """Met à jour une propriété d'une entrée existante."""
        if alias in self.mapping_data:
            self.mapping_data[alias][key] = value
            self.save_mapping()
            return True
        return False
    
    def rename_alias(self, old_alias: str, new_alias: str) -> bool:
        """Renomme une clé dans le mapping."""
        if old_alias not in self.mapping_data:
            return False
        if new_alias in self.mapping_data:
            return False
            
        data = self.mapping_data[old_alias]
        del self.mapping_data[old_alias]
        self.mapping_data[new_alias] = data
        self.save_mapping()
        return True
