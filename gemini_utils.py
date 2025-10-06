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
        self.model = self._get_robust_model()
    
    def _get_robust_model(self):
        """
        Intenta inicializar el mejor modelo de Gemini disponible de una lista priorizada.
        Esto hace que la aplicación sea más resiliente a cambios en la disponibilidad de modelos.
        """
        # Lista de modelos desde el más nuevo/potente al más estable/antiguo como fallback
        model_candidates = [
            "gemini-1.5-pro-latest",   # El más potente
            "gemini-1.5-flash-latest", # El más rápido y recomendado para la mayoría de casos
            "gemini-1.0-pro-vision-latest" # Un modelo de visión estable como último recurso
        ]
        
        for model_name in model_candidates:
            try:
                model = genai.GenerativeModel(model_name)
                logger.info(f"✅ Modelo de Gemini '{model_name}' inicializado con éxito.")
                return model
            except Exception as e:
                logger.warning(f"⚠️ Modelo '{model_name}' no disponible o falló la inicialización: {e}")
                continue
        
        # Si ningún modelo de la lista funciona, se lanza un error crítico.
        raise Exception("No se pudo inicializar ningún modelo de Gemini compatible. Revisa tu API Key y la configuración del proyecto de Google AI.")
    
    def analyze_image(self, image_pil: Image, description: str = ""):
        """
        Analiza una imagen (en formato PIL) y devuelve una respuesta JSON estructurada.
        """
        try:
            # Se mantiene el prompt optimizado para forzar una salida JSON limpia,
            # lo que es crucial para que la app no falle al procesar la respuesta.
            prompt = f"""
            Analiza esta imagen de un objeto de inventario.
            Descripción adicional proporcionada por el sistema de detección: "{description}"
            
            Tu tarea es actuar como un experto en catalogación. Responde ÚNICAMENTE con un objeto JSON válido con las siguientes claves:
            - "elemento_identificado": (string) El nombre específico y descriptivo del objeto.
            - "cantidad_aproximada": (integer) El número de unidades que ves en la imagen.
            - "estado_condicion": (string) La condición aparente (ej: "Nuevo en caja", "Usado con desgaste ligero", "Empaquetado").
            - "posible_categoria_de_inventario": (string) La categoría más lógica para este item (ej: "Electrónica", "Suministros de Oficina", "Alimentos no perecederos").

            IMPORTANTE: Tu respuesta debe ser solo el objeto JSON, sin texto adicional, explicaciones, ni las marcas ```json.
            """
            
            response = self.model.generate_content([prompt, image_pil])
            
            if response and response.text:
                return response.text.strip()
            else:
                # Devuelve un error JSON si la respuesta está vacía
                return json.dumps({"error": "La IA no devolvió una respuesta válida."})
                
        except Exception as e:
            logger.error(f"Error crítico durante el análisis de imagen con Gemini: {e}")
            # Devuelve un error JSON si ocurre una excepción en la llamada a la API
            return json.dumps({"error": f"No se pudo contactar al servicio de IA: {str(e)}"})

