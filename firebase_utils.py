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
                
                # Decodificar el Base64
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
            # Añade timestamp para seguimiento
            data['timestamp'] = datetime.now().isoformat()
            doc_ref.set(data, merge=True) # merge=True permite actualizar sin borrar otros campos
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

    @firestore.transactional
    def complete_order_transaction(self, transaction, order_id):
        """
        Función transaccional para completar un pedido.
        Esto asegura que la actualización del stock y del pedido sea atómica.
        """
        order_ref = self.db.collection('orders').document(order_id)
        order_snapshot = order_ref.get(transaction=transaction)
        if not order_snapshot.exists:
            return False, "El pedido no existe."
        
        order_data = order_snapshot.to_dict()
        
        # 1. Verificar stock
        inventory_updates = []
        for ing in order_data.get('ingredients', []):
            item_ref = self.db.collection('inventory').document(ing['name']) # Asumimos ID de inventario es el nombre
            item_snapshot = item_ref.get(transaction=transaction)
            if not item_snapshot.exists:
                return False, f"Ingrediente '{ing['name']}' no encontrado en el inventario."
            
            current_quantity = item_snapshot.to_dict().get('quantity', 0)
            if current_quantity < ing['quantity']:
                return False, f"Stock insuficiente para '{ing['name']}'. Necesitas {ing['quantity']}, tienes {current_quantity}."
            
            new_quantity = current_quantity - ing['quantity']
            inventory_updates.append({'ref': item_ref, 'quantity': new_quantity})

        # 2. Si hay stock, actualizar todo
        for update in inventory_updates:
            transaction.update(update['ref'], {'quantity': update['quantity']})
            
        transaction.update(order_ref, {'status': 'completed'})
        
        return True, f"Pedido '{order_data['title']}' completado con éxito."

    def complete_order(self, order_id):
        """Punto de entrada para la transacción de completar pedido."""
        transaction = self.db.transaction()
        return self.complete_order_transaction(transaction, order_id)
