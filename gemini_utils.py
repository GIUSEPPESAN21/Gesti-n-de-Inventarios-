import google.generativeai as genai
import logging
from PIL import Image
import streamlit as st
import json

# Configurar logging para ver qué modelo se está utilizando
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiUtils:
    def __init__(self):
        # Obtener API key desde Streamlit secrets
        self.api_key = st.secrets.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no encontrada en secrets")
        
        genai.configure(api_key=self.api_key)
        
        # Inicializa el modelo usando el método robusto de selección
        self.model = self._get_robust_vision_model()
    
    def _get_robust_vision_model(self):
        """
        Intenta inicializar el mejor modelo de VISIÓN de Gemini disponible.
        Realiza una pequeña llamada de prueba para asegurar que el modelo no solo existe,
        sino que también es compatible con análisis de imágenes.
        """
        # Lista de modelos de visión, desde el más nuevo al más estable
        model_candidates = [
            "gemini-1.5-pro-latest",
            "gemini-1.5-flash-latest",
            "gemini-pro-vision" # Un modelo de visión clásico como fallback
        ]
        
        for model_name in model_candidates:
            try:
                model = genai.GenerativeModel(model_name)
                # Prueba rápida para asegurar que el modelo puede manejar imágenes
                model.generate_content(["test", Image.new('RGB', (1, 1), color = 'red')])
                logger.info(f"✅ Modelo de visión '{model_name}' inicializado y verificado con éxito.")
                return model
            except Exception as e:
                logger.warning(f"⚠️ Modelo de visión '{model_name}' no disponible o no compatible: {e}")
                continue
        
        raise Exception("No se pudo inicializar ningún modelo de visión de Gemini compatible. Revisa tu API Key.")
    
    def analyze_image(self, image_pil: Image, description: str = ""):
        """
        Analiza una imagen (en formato PIL) y devuelve una respuesta JSON estructurada.
        """
        try:
            # El prompt se mantiene optimizado para forzar una salida JSON limpia.
            prompt = f"""
            Analiza esta imagen de un objeto de inventario.
            Descripción adicional del sistema de detección: "{description}"
            
            Tu tarea es actuar como un experto catalogador. Responde ÚNICAMENTE con un objeto JSON válido con estas claves:
            - "elemento_identificado": (string) El nombre específico y descriptivo del objeto.
            - "cantidad_aproximada": (integer) El número de unidades que ves.
            - "estado_condicion": (string) La condición aparente (ej: "Nuevo en caja", "Usado").
            - "caracteristicas_distintivas": (string) Una lista de características visuales en una sola cadena de texto.
            - "posible_categoria_de_inventario": (string) La categoría más lógica (ej: "Electrónica").

            Ejemplo de respuesta:
            {{
              "elemento_identificado": "Reloj de pulsera negro",
              "cantidad_aproximada": 1,
              "estado_condicion": "Nuevo",
              "caracteristicas_distintivas": "Correa de silicona negra, esfera digital, diseño moderno",
              "posible_categoria_de_inventario": "Accesorios Personales"
            }}
            
            IMPORTANTE: Tu respuesta debe ser solo el objeto JSON, sin texto adicional, explicaciones, ni las marcas ```json.
            """
            
            response = self.model.generate_content([prompt, image_pil])
            
            if response and response.text:
                return response.text.strip()
            else:
                return json.dumps({"error": "La IA no devolvió una respuesta válida."})
                
        except Exception as e:
            logger.error(f"Error crítico durante el análisis con Gemini: {e}")
            return json.dumps({"error": f"No se pudo contactar al servicio de IA: {str(e)}"})

