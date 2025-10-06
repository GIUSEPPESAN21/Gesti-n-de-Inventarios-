import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import logging
from datetime import datetime
import streamlit as st

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FirebaseManager:
    def __init__(self):
        self.db = None
        self.project_id = "reconocimiento-inventario" # Asegúrate que este sea tu Project ID de Firebase
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Inicializa Firebase usando Streamlit secrets de forma segura."""
        try:
            if not firebase_admin._apps:
                creds_base64 = st.secrets.get('FIREBASE_SERVICE_ACCOUNT_BASE64')
                if not creds_base64:
                    raise ValueError("El secret 'FIREBASE_SERVICE_ACCOUNT_BASE64' no fue encontrado.")
                
                creds_json_str = base64.b64decode(creds_base64).decode('utf-8')
                creds_dict = json.loads(creds_json_str)
                
                cred = credentials.Certificate(creds_dict)
                firebase_admin.initialize_app(cred, {'projectId': self.project_id})
                logger.info("Firebase inicializado correctamente.")
            
            self.db = firestore.client()
        except Exception as e:
            logger.error(f"Error fatal al inicializar Firebase: {e}")
            raise

    # --- Métodos para Inventario ---
    def save_inventory_item(self, data, custom_id):
        """Guarda o actualiza un item en la colección 'inventory' usando un ID personalizado."""
        try:
            doc_ref = self.db.collection('inventory').document(custom_id)
            data['timestamp'] = datetime.now().isoformat()
            doc_ref.set(data, merge=True)
            logger.info(f"Elemento de inventario guardado/actualizado: {custom_id}")
        except Exception as e:
            logger.error(f"Error al guardar en 'inventory': {e}")
            raise

    def get_all_inventory_items(self):
        """Obtiene todos los elementos de la colección 'inventory'."""
        try:
            docs = self.db.collection('inventory').stream()
            items = []
            for doc in docs:
                item = doc.to_dict()
                item['id'] = doc.id
                items.append(item)
            return items
        except Exception as e:
            logger.error(f"Error al obtener de 'inventory': {e}")
            return []

    def delete_inventory_item(self, doc_id):
        """Elimina un elemento de inventario por su ID."""
        try:
            self.db.collection('inventory').document(doc_id).delete()
            logger.info(f"Elemento de inventario {doc_id} eliminado.")
        except Exception as e:
            logger.error(f"Error al eliminar de 'inventory': {e}")
            raise

    # --- Métodos para Pedidos ---
    def create_order(self, order_data):
        """Crea un nuevo pedido en la colección 'orders'."""
        try:
            order_data['timestamp'] = datetime.now().isoformat()
            self.db.collection('orders').add(order_data)
            logger.info("Nuevo pedido creado.")
        except Exception as e:
            logger.error(f"Error al crear pedido: {e}")
            raise

    def get_orders(self, status='processing'):
        """Obtiene pedidos, filtrados por estado ('processing', 'completed', o None para todos)."""
        try:
            query = self.db.collection('orders')
            if status:
                query = query.where(filter=firestore.FieldFilter('status', '==', status))
            
            docs = query.stream()
            orders = []
            for doc in docs:
                order = doc.to_dict()
                order['id'] = doc.id
                orders.append(order)
            return orders
        except Exception as e:
            logger.error(f"Error al obtener pedidos: {e}")
            return []

    def cancel_order(self, order_id):
        """Elimina un pedido por su ID."""
        try:
            self.db.collection('orders').document(order_id).delete()
            logger.info(f"Pedido {order_id} cancelado.")
        except Exception as e:
            logger.error(f"Error al cancelar pedido: {e}")
            raise

    # CORRECCIÓN: Se quita el decorador @firestore.transactional y se renombra la función.
    # Esta función ahora contiene únicamente la lógica que debe ejecutarse de forma atómica.
    def _complete_order_atomic(self, transaction, order_id):
        """
        Lógica atómica para completar un pedido. Se ejecuta dentro de una transacción.
        """
        order_ref = self.db.collection('orders').document(order_id)
        order_snapshot = order_ref.get(transaction=transaction)
        if not order_snapshot.exists:
            return False, "El pedido no existe."
        
        order_data = order_snapshot.to_dict()
        
        inventory_updates = []
        for ing in order_data.get('ingredients', []):
            # Asumimos que el ID del item en inventario es su nombre. ¡Esto debe ser consistente!
            # Si usas un ID numérico o SKU, debes buscar por ese campo.
            item_ref = self.db.collection('inventory').document(ing['name'])
            item_snapshot = item_ref.get(transaction=transaction)
            
            if not item_snapshot.exists:
                return False, f"Ingrediente '{ing['name']}' no encontrado en el inventario."
            
            current_quantity = item_snapshot.to_dict().get('quantity', 0)
            if current_quantity < ing['quantity']:
                return False, f"Stock insuficiente para '{ing['name']}'. Necesitas {ing['quantity']}, tienes {current_quantity}."
            
            new_quantity = current_quantity - ing['quantity']
            inventory_updates.append({'ref': item_ref, 'quantity': new_quantity})

        for update in inventory_updates:
            transaction.update(update['ref'], {'quantity': update['quantity']})
            
        transaction.update(order_ref, {'status': 'completed'})
        
        return True, f"Pedido '{order_data['title']}' completado con éxito."

    # CORRECCIÓN: La función principal ahora crea la transacción y llama a transaction.run()
    def complete_order(self, order_id):
        """Punto de entrada para la transacción de completar pedido."""
        try:
            transaction = self.db.transaction()
            # transaction.run() ejecuta la función atómica de forma segura.
            # Le pasamos la función y los argumentos necesarios (sin 'transaction').
            return transaction.run(self._complete_order_atomic, order_id)
        except Exception as e:
            logger.error(f"Fallo la transacción para completar el pedido {order_id}: {e}")
            return False, f"Error en la transacción: {e}"

