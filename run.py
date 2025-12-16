#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de lancement intelligent pour Block Validator

Usage: python run.py <project_name>
Exemple: python run.py KLegacy

Structure attendue:
  data/
    KLegacy/
      ├── KLegacy.pdf
      └── KLegacy_model.json
"""

import sys
import os
from pathlib import Path


def print_usage():
    """Afficher l'aide d'utilisation"""
    print("=" * 70)
    print("  🎯 BLOCK VALIDATOR - Lanceur de projet")
    print("=" * 70)
    print("\n📖 Usage:")
    print("  python run.py <project_name>")
    print("\n📝 Exemples:")
    print("  python run.py KLegacy")
    print("  python run.py Yokai")
    print("\n📂 Structure attendue:")
    print("  data/")
    print("    <project_name>/")
    print("      ├── <project_name>.pdf")
    print("      └── <project_name>_model.json")
    print("\n💡 Projets disponibles:")
    list_available_projects()
    print("\n🎨 Fonctionnalités:")
    print("  • Validation et édition des blocs MinerU")
    print("  • Gestion des isolated_spans")
    print("  • Création de nouveaux blocs")
    print("  • Highlight visuel avec clignotement")
    print("  • Sauvegarde avec métadonnées")
    print("=" * 70)


def list_available_projects():
    """Lister les projets disponibles dans data/"""
    data_dir = Path("data")
    
    if not data_dir.exists():
        print("  ⚠️  Aucun répertoire 'data/' trouvé")
        return
    
    projects = []
    for item in data_dir.iterdir():
        if item.is_dir():
            pdf = item / f"{item.name}.pdf"
            json_file = item / f"{item.name}_model.json"
            
            # Vérifier aussi les métadonnées de validation
            meta_file = item / f"{item.name}_validation_metadata.json"
            has_meta = meta_file.exists()
            
            if pdf.exists() and json_file.exists():
                status = "✓"
                if has_meta:
                    status += " 📊"  # Indicateur de validation précédente
            else:
                status = "✗"
            
            projects.append(f"  {status} {item.name}")
    
    if projects:
        print("\n".join(sorted(projects)))
        print("\n  Légende: ✓ = Prêt  |  📊 = Validation sauvegardée")
    else:
        print("  (Aucun projet trouvé)")


def validate_project(project_name: str) -> tuple:
    """
    Valider qu'un projet existe avec ses fichiers
    
    Args:
        project_name: Nom du projet
        
    Returns:
        (project_dir, pdf_path, json_path)
        
    Raises:
        FileNotFoundError: Si le projet ou ses fichiers sont introuvables
    """
    project_dir = Path("data") / project_name
    
    # Vérifier le dossier du projet
    if not project_dir.exists():
        raise FileNotFoundError(
            f"❌ Projet '{project_name}' introuvable.\n"
            f"   Attendu: {project_dir}\n\n"
            f"💡 Créez le dossier: mkdir -p {project_dir}"
        )
    
    if not project_dir.is_dir():
        raise FileNotFoundError(
            f"❌ '{project_dir}' existe mais n'est pas un dossier"
        )
    
    # Vérifier le PDF
    pdf_path = project_dir / f"{project_name}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"❌ PDF introuvable: {pdf_path}\n"
            f"💡 Le PDF doit s'appeler exactement '{project_name}.pdf'"
        )
    
    # Vérifier le JSON
    json_path = project_dir / f"{project_name}_model.json"
    if not json_path.exists():
        raise FileNotFoundError(
            f"❌ JSON MinerU introuvable: {json_path}\n"
            f"💡 Le JSON doit s'appeler exactement '{project_name}_model.json'"
        )
    
    return project_dir, pdf_path, json_path


def check_metadata(project_dir: Path, project_name: str):
    """
    Vérifier et afficher les métadonnées de validation existantes
    
    Args:
        project_dir: Répertoire du projet
        project_name: Nom du projet
    """
    meta_file = project_dir / f"{project_name}_validation_metadata.json"
    
    if meta_file.exists():
        print(f"📊 Métadonnées de validation trouvées")
        
        try:
            import json
            with open(meta_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Compter les validations
            total_manual = 0
            total_preserved = 0
            total_isolated = 0
            
            for page in metadata.get('pages', []):
                for block in page.get('blocks', []):
                    if block.get('match_source') == 'manual':
                        total_manual += 1
                    if block.get('preserve_empty'):
                        total_preserved += 1
                    if block.get('block_type') == 'isolated_span' and block.get('include_in_output'):
                        total_isolated += 1
            
            if total_manual or total_preserved or total_isolated:
                print(f"   • {total_manual} blocs manuels")
                print(f"   • {total_preserved} blocs vides conservés")
                print(f"   • {total_isolated} isolated spans inclus")
        
        except Exception as e:
            print(f"   ⚠️ Impossible de lire les métadonnées: {e}")


def main():
    """Point d'entrée principal"""
    
    # Vérifier les arguments
    if len(sys.argv) < 2:
        print("❌ Erreur: Nom du projet manquant\n")
        print_usage()
        sys.exit(1)
    
    # Gestion de l'aide
    if sys.argv[1] in ['-h', '--help', 'help', 'list']:
        print_usage()
        sys.exit(0)
    
    project_name = sys.argv[1]
    
    print("=" * 70)
    print(f"  🚀 Lancement du projet: {project_name}")
    print("=" * 70)
    
    try:
        # Valider le projet
        project_dir, pdf_path, json_path = validate_project(project_name)
        
        print(f"✓ Projet trouvé: {project_dir}")
        print(f"✓ PDF: {pdf_path.name}")
        print(f"✓ JSON: {json_path.name}")
        
        # Vérifier les métadonnées
        check_metadata(project_dir, project_name)
        
        # Sauvegarder le répertoire courant
        original_dir = os.getcwd()
        
        # Changer vers le dossier du projet
        os.chdir(project_dir)
        print(f"✓ Répertoire de travail: {project_dir}")
        
        # Lancer l'application
        print("\n🔄 Chargement de l'interface de validation...")
        print("=" * 70 + "\n")
        
        # Importer et lancer
        from block_matcher.main import main as validator_main
        
        # Remplacer sys.argv pour passer le nom du projet
        sys.argv = ["block_matcher", project_name]
        
        # Lancer l'application
        validator_main()
        
    except FileNotFoundError as e:
        print(f"\n{e}\n")
        print_usage()
        sys.exit(1)
        
    except ImportError as e:
        print(f"\n❌ Erreur d'import: {e}")
        print("\n💡 Vérifiez que:")
        print("  - Le package 'block_matcher' existe")
        print("  - Le fichier 'extract.py' est à la racine")
        print("  - Les dépendances sont installées (pip install PyQt5 PyMuPDF)")
        sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interruption par l'utilisateur")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        # Restaurer le répertoire original (si possible)
        try:
            os.chdir(original_dir)
        except:
            pass


if __name__ == "__main__":
    main()
