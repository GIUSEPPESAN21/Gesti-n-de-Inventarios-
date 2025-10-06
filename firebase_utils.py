import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import logging
from datetime import datetime
import streamlit as st

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# La función transaccional atómica ya no es necesaria con el método manual.

class FirebaseManager:
    def __init__(self):
        self.db = None
        self.project_id = "reconocimiento-inventario"
        self._initialize_firebase()
    
    def _initialize_firebase(self):
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

    # ... (El resto de los métodos permanecen igual)
    def save_inventory_item(self, data, custom_id):
        try:
            doc_ref = self.db.collection('inventory').document(custom_id)
            data['timestamp'] = datetime.now().isoformat()
            doc_ref.set(data, merge=True)
            logger.info(f"Elemento de inventario guardado/actualizado: {custom_id}")
        except Exception as e:
            logger.error(f"Error al guardar en 'inventory': {e}")
            raise

    def get_all_inventory_items(self):
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
        try:
            self.db.collection('inventory').document(doc_id).delete()
            logger.info(f"Elemento de inventario {doc_id} eliminado.")
        except Exception as e:
            logger.error(f"Error al eliminar de 'inventory': {e}")
            raise

    def create_order(self, order_data):
        try:
            order_data['timestamp'] = datetime.now().isoformat()
            self.db.collection('orders').add(order_data)
            logger.info("Nuevo pedido creado.")
        except Exception as e:
            logger.error(f"Error al crear pedido: {e}")
            raise

    def get_orders(self, status='processing'):
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
        try:
            self.db.collection('orders').document(order_id).delete()
            logger.info(f"Pedido {order_id} cancelado.")
        except Exception as e:
            logger.error(f"Error al cancelar pedido: {e}")
            raise

    def complete_order(self, order_id):
        """
        Completa un pedido usando una transacción manual para garantizar la atomicidad.
        """
        transaction = self.db.transaction()
        try:
            # 1. Leer el pedido DENTRO de la transacción
            order_ref = self.db.collection('orders').document(order_id)
            order_snapshot = order_ref.get(transaction=transaction)
            if not order_snapshot.exists:
                raise ValueError("El pedido no existe.")
            
            order_data = order_snapshot.to_dict()

            # 2. Iterar sobre los ingredientes para verificar y descontar el stock
            for ing in order_data.get('ingredients', []):
                item_ref = self.db.collection('inventory').document(ing['id'])
                item_snapshot = item_ref.get(transaction=transaction)
                
                if not item_snapshot.exists:
                    raise ValueError(f"Ingrediente ID '{ing['id']}' no encontrado.")
                
                current_quantity = item_snapshot.to_dict().get('quantity', 0)
                if current_quantity < ing['quantity']:
                    raise ValueError(f"Stock insuficiente para '{ing.get('name', ing['id'])}'.")
                
                new_quantity = current_quantity - ing['quantity']
                transaction.update(item_ref, {'quantity': new_quantity})

            # 3. Actualizar el estado del pedido
            transaction.update(order_ref, {'status': 'completed'})
            
            # 4. Si todo fue exitoso, confirmar los cambios
            transaction.commit()
            
            return True, f"Pedido '{order_data['title']}' completado con éxito."

        except Exception as e:
            # 5. Si algo falla, revertir todo
            transaction.rollback()
            logger.error(f"Fallo la transacción para el pedido {order_id}: {e}")
            return False, f"Error en la transacción: {str(e)}"

