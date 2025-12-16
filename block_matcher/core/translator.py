# block_matcher/core/translator.py

import json
import os
import google.generativeai as genai

class AutoTranslator:
    def __init__(self, api_key):
        self.api_key = api_key
        
    def translate_file(self, input_path, lang_code="FR"):
        """
        Traduit le fichier JSON via Google Gemini.
        Retourne le chemin du fichier généré ou lève une exception.
        """
        if not self.api_key:
            raise ValueError("Clé API manquante.")

        print(f"--- TRADUCTION GEMINI ({lang_code}) ---")
        genai.configure(api_key=self.api_key)
        
        # Modèle validé
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash-lite", # Ou votre modèle qui marche
            system_instruction=(
                f"Tu es un traducteur professionnel JSON. "
                f"Ta mission : Traduire le champ 'source' vers la langue '{lang_code}' et remplir le champ 'target'.\n"
                "RÈGLES :\n"
                "1. Ne modifie JAMAIS les 'id' ni le texte 'source'.\n"
                "2. Conserve strictement les balises XML/techniques (<gs...>, <svg...>) à leur place logique.\n"
                "3. Renvoie la structure JSON exacte reçue en entrée."
            )
        )

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Fichier introuvable : {input_path}")

        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        json_string = json.dumps(data, ensure_ascii=False)
        
        # Appel API
        response = model.generate_content(
            json_string,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
            }
        )

        # Parsage
        translated_data = json.loads(response.text)
        
        # Gestion format liste/dict (sécurité)
        if isinstance(translated_data, dict) and len(translated_data) == 1:
            first_val = list(translated_data.values())[0]
            if isinstance(first_val, list):
                translated_data = first_val

        # Sauvegarde avec votre nommage corrigé
        # Ex: "Prey_pour_traduction.json" -> "Prey_pour_traduction_FR.json"
        output_filename = input_path.replace(".json", f"_{lang_code}.json")
        
        # Sécurité si le replace n'a pas marché (ex: pas d'extension .json)
        if output_filename == input_path:
             output_filename = f"{input_path}_{lang_code}.json"

        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(translated_data, f, indent=2, ensure_ascii=False)

        return output_filename
