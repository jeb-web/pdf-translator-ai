import json
import os
import argparse
import sys
import google.generativeai as genai
from google.api_core import retry

def load_api_key():
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            return config.get("api_key", "")
    except FileNotFoundError:
        return ""

DEFAULT_API_KEY = load_api_key()


def translate_with_gemini(input_path, lang_code, api_key):
    print(f"--- TRADUCTION VIA GOOGLE GEMINI ({lang_code}) ---")
    
    # 1. Configuration de l'API
    genai.configure(api_key=api_key)
    
    # On configure le modèle avec instruction système
    # Gemini 1.5 Flash est idéal pour le volume et la vitesse
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=(
            f"Tu es un traducteur professionnel JSON. "
            f"Ta mission : Traduire le champ 'source' vers la langue '{lang_code}' et remplir le champ 'target'.\n"
            "RÈGLES :\n"
            "1. Ne modifie JAMAIS les 'id' ni le texte 'source'.\n"
            "2. Conserve strictement les balises XML/techniques (<gs...>, <svg...>) à leur place logique dans la phrase traduite.\n"
            "3. Renvoie la structure JSON exacte reçue en entrée."
        )
    )

    # 2. Chargement du fichier
    if not os.path.exists(input_path):
        print("Erreur : Fichier introuvable.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 3. Préparation de l'envoi
    # On convertit le JSON en string pour le prompt
    json_string = json.dumps(data, ensure_ascii=False)
    
    # Estimation grossière (1 token ~= 4 chars). 
    # Gemini 1.5 Flash accepte 1M tokens, donc quasi aucune limite ici.
    print(f"Taille des données : {len(json_string)} caractères. Envoi en cours...")

    try:
        # 4. Appel API avec contrainte JSON forcée
        # response_mime_type="application/json" oblige le modèle à renvoyer du JSON pur.
        response = model.generate_content(
            json_string,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.1, # Faible créativité pour respecter le format
            }
        )

        # 5. Récupération et Parsage
        translated_text = response.text
        
        # Parfois Gemini renvoie un objet racine ou une liste direct. 
        # On tente de charger pour voir.
        translated_data = json.loads(translated_text)
        
        # Vérification structurelle rapide (Gemini met parfois tout dans une clé si on ne précise pas)
        # Si le JSON reçu est une liste, c'est parfait.
        # Sinon, on vérifie si c'est un dict avec une seule clé contenant la liste.
        if isinstance(translated_data, dict) and len(translated_data) == 1:
            # On récupère la première valeur si c'est une liste
            first_val = list(translated_data.values())[0]
            if isinstance(first_val, list):
                translated_data = first_val

        # 6. Sauvegarde
        output_filename = input_path.replace(".json", f"_{lang_code}.json")
        if output_filename == input_path:
            output_filename = input_path + f".{lang_code}.json"

        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(translated_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Succès ! Fichier généré : {output_filename}")

    except Exception as e:
        print(f"\n❌ ERREUR : {e}")
        # En cas de blocage de sécurité (safety settings), Gemini peut refuser de répondre.
        # Pour ce type de contenu (traduction technique), c'est rare, mais possible.

# --- ENTRY POINT ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Traduit un fichier JSON via Google Gemini API.")
    parser.add_argument("file", help="Chemin du fichier JSON source")
    parser.add_argument("--lang", default="FR", help="Langue cible (par défaut: FR)")
    parser.add_argument("--key", help="Clé API Google (optionnel si GOOGLE_API_KEY défini)")

    args = parser.parse_args()

    api_key = args.key or DEFAULT_API_KEY
    if not api_key:
        print("Erreur : Aucune clé API trouvée.")
        print("Définissez la variable d'env GOOGLE_API_KEY ou utilisez --key")
        sys.exit(1)

    translate_with_gemini(args.file, args.lang, api_key)
