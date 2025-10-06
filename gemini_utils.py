import google.generativeai as genai
import logging
from PIL import Image
import streamlit as st
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiUtils:
    def __init__(self):
        self.api_key = st.secrets.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no encontrada en secrets")
        
        genai.configure(api_key=self.api_key)
        # Usar un modelo de visión conocido y estable
        self.model = genai.GenerativeModel('gemini-1.5-flash-latest')
        logger.info(f"Modelo Gemini 'gemini-1.5-flash-latest' inicializado.")

    def analyze_image(self, image_pil: Image, description: str = ""):
        """Analiza una imagen PIL y devuelve una respuesta JSON."""
        try:
            prompt = f"""
            Analiza esta imagen de un objeto de inventario.
            Descripción adicional: "{description}"
            
            Tu tarea es identificar y describir el objeto principal. Responde únicamente con un objeto JSON válido con estas claves:
            - "elemento_identificado": (string) El nombre específico del objeto.
            - "cantidad_aproximada": (integer) El número de unidades que ves.
            - "estado_condicion": (string) La condición aparente (ej: "Nuevo", "Usado", "Empaquetado").
            - "posible_categoria_de_inventario": (string) Una categoría de inventario (ej: "Bebidas", "Limpieza").

            IMPORTANTE: Tu respuesta debe ser solo el objeto JSON, sin incluir ```json al principio o al final.
            """
            
            response = self.model.generate_content([prompt, image_pil])
            
            if response and response.text:
                return response.text.strip()
            else:
                return json.dumps({"error": "No se pudo analizar la imagen"})
                
        except Exception as e:
            logger.error(f"Error al analizar imagen con Gemini: {e}")
            return json.dumps({"error": f"Error en el análisis de Gemini: {str(e)}"})
