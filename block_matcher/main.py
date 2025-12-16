import sys
import os
from PyQt5.QtWidgets import QApplication
from .core.session_manager import load_or_create_session
from .gui.main_window import BlockValidationInterface
from .core.extract import DualOutputGenerator  # extract.py à la racine du projet

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m block_matcher.main <basename>")
        sys.exit(1)
    
    basename = sys.argv[1]

    # IMPORTANT : ici on est déjà dans data/<project_name> grâce à run.py
    pdf_path = f"{basename}.pdf"
    mineru_json_path = f"{basename}_model.json"
    session_file = f"{basename}_session.json"

    print("\n" + "="*70)
    print(f"  🚀 Lancement du projet: {basename}")
    print("="*70)

    # CAS 1 : le fichier de session existe dans ce dossier → on le charge tel quel
    if os.path.exists(session_file):
        print(f"[INFO] Session existante trouvée : {session_file}")
        session_data = load_or_create_session(basename)
    else:
        # CAS 2 : aucune session → on fait le matching automatique MinerU ↔ PyMuPDF
        print(f"[INFO] Aucune session trouvée, création avec matching automatique.")

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF introuvable : {pdf_path}")
        if not os.path.exists(mineru_json_path):
            raise FileNotFoundError(f"JSON MinerU introuvable : {mineru_json_path}")

        # 1) Construire enriched_data + page_dimensions via DualOutputGenerator
        generator = DualOutputGenerator(
            enriched_data=None,
            page_dimensions={},
            global_styles_data=None
        )
        mineru_data = generator._load_mineru_data(mineru_json_path)
        enriched_data = generator._process_with_visual_matching(pdf_path, mineru_data)
        page_dimensions = generator.page_dimensions

        # 2) Créer la session (ceci écrit <basename>_session.json dans ce dossier)
        session_data = load_or_create_session(
            basename=basename,
            pdf_path=pdf_path,
            enriched_data=enriched_data,
            page_dimensions=page_dimensions,
        )
        print(f"[INFO] Nouvelle session créée : {session_file}")

    # 3) Lancer l’UI avec session_data (dans les deux cas)
    app = QApplication(sys.argv)
    window = BlockValidationInterface(session_data)
    window.show()
    sys.exit(app.exec_())
