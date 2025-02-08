from datetime import datetime
import logging
import random
import string
from typing import Any, Text, Dict, List, Tuple

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

import firebase_admin
from firebase_admin import credentials, firestore

########################## Initialize Firebase ##########################

try:
    cred = credentials.Certificate("./aura-kart-firebase-adminsdk-448ve-f76ba9a07e.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logging.info("Firebase initialized successfully")
except Exception as e:
    logging.error(f"Firebase initialization error: {e}")

########################## Action Search Product ##########################

class ActionSearchProduct(Action):
    def name(self) -> Text:
        return "action_search_product"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get product from user input
        product = tracker.get_slot("product")

        # Validate product input
        if not product:
            dispatcher.utter_message(text="Could you please specify what product you're looking for?")
            return []
        
        try: 
            product = product.lower()

            # Search for product in Firestore collection and get its data
            products_ref = db.collection('products')
            query = products_ref.where('name', '>=', product)\
                            .where('name', '<=', product + '\uf8ff')\
                            .limit(5)\
                            .get()          
                  
            # If no product found, inform user and return
            if not query:
                dispatcher.utter_message(text=f"Sorry, I couldn't find  {product} in our store.")
                return []
                
            # If product found, display its data and return
            products_found = []
            for doc in query:
                product_data = doc.to_dict()
                products_found.append(
                    f"• {product_data.get('name', 'N/A')}:\n"
                    f"  Price: ${product_data.get('price', 'N/A')}\n"
                    f"  Stock: {product_data.get('stock', 'N/A')} units\n"
                    f"  ID: {doc.id}\n"
                )
            
            response = "Here's what I found:\n\n" + "\n".join(products_found)
            dispatcher.utter_message(text=response)

        except Exception as e:
            logging.error(f"Error searching product: {e}")
            dispatcher.utter_message(text="An error occurred while searching for products. Please try again later.")

        return []
    
########################## Action Add To Cart ##########################

class ActionAddToCart(Action):
    def name(self) -> Text:
        return "action_add_to_cart"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get user ID from tracker
        user_id = tracker.sender_id

        # Get product from user input
        product = tracker.get_slot("product")
        # Get quantity from user input
        quantity = tracker.get_slot("quantity") or 1

        # Validate quantity input
        try:
            quantity = int(quantity)
        except ValueError:
            dispatcher.utter_message(text="Please provide a valid quantity.")
            return []

        # Validate product input
        if not product:
            dispatcher.utter_message(text="Please specify the product you want to add.")
            return []

        try:
            product = product.lower()

            # Check product availability
            product_ref = db.collection('products').where('name', '==', product).limit(1).get()
            if not product_ref:
                dispatcher.utter_message(text=f"Sorry, {product} is not available.")
                return []
            
            product_data = product_ref[0].to_dict()
            
            # Check stock
            if product_data.get('stock', 0) < quantity:
                dispatcher.utter_message(text=f"Sorry, only {product_data.get('stock')} units available.")
                return []

            # Get the user's cart from Firestore collection
            cart_ref = db.collection('carts').document(user_id)
            cart_doc = cart_ref.get()

            # If the user doesn't have a cart, create a new one
            if cart_doc.exists: 
                cart_data = cart_doc.to_dict()
                cart = cart_data.get("items", [])
            else:
                cart = []

            # Check if the product is already in the cart
            product_in_cart = next((item for item in cart if item["product"] == product), None)
            price = product_data.get('price', 0)
 
            if product_in_cart:
                # Update the quantity of the existing product
                product_in_cart["quantity"] += quantity
                product_in_cart["total"] = product_in_cart["quantity"] * price
                response = f"Updated {product} quantity to {product_in_cart['quantity']} in your cart."
            else:
                # Add new product to the cart
                cart.append({
                    "product": product,
                    "quantity": quantity,
                    "price": price,
                    "total": quantity * price
                })                
                response = f"Added {quantity} {product}(s) to your cart."            
                        
            # Update cart
            cart_ref.set({'items': cart}, merge=True)

            dispatcher.utter_message(text=response)
            
        except Exception as e:
            logging.error(f"Error adding to cart: {e}")
            dispatcher.utter_message(text="An error occurred while adding the product to your cart.")

        return []

########################## Action Place Order ##########################

class ActionPlaceOrder(Action):
    def name(self) -> Text:
        return "action_place_order"
    
    def generate_order_id(self) -> str:
        """Generate a unique order ID."""
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"ORD-{timestamp}-{random_suffix}"

    def validate_stock(self, items: List[Dict]) -> Tuple[bool, List[str]]:
        """Validate stock availability for all items."""
        out_of_stock = []
        for item in items:
            product_ref = db.collection('products').where('name', '==', item['product']).limit(1).get()
            if product_ref:
                product = product_ref[0].to_dict()
                if product.get('stock', 0) < item['quantity']:
                    out_of_stock.append(item['product'])
        return len(out_of_stock) == 0, out_of_stock
    
    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
    
        # Get user ID from tracker
        user_id = tracker.sender_id

        try:
            # Get the user's cart from Firestore collection
            cart_ref = db.collection("carts").document(user_id)
            cart_doc = cart_ref.get()

            # If the user doesn't have a cart, return
            if not cart_doc.exists:
                dispatcher.utter_message(text="Your cart is empty.")
                return []
    
            cart_data = cart_doc.to_dict()
            items = cart_data.get("items", [])

            if not items:
                dispatcher.utter_message(text="Your cart is empty.")
                return []
            
            # Validate stock
            stock_valid, out_of_stock = self.validate_stock(items)
            if not stock_valid:
                message = "Cannot place order. These items have insufficient stock:\n"
                message += "\n".join([f"• {item}" for item in out_of_stock])
                dispatcher.utter_message(text=message)
                return []
            
            # Create order
            order_id = self.generate_order_id()
            order_data = {
                "order_id": order_id,
                "user_id": user_id,
                "items": items,
                "status": "placed",
                "timestamp": firestore.SERVER_TIMESTAMP,
                "total_amount": sum(item['price'] * item['quantity'] for item in items)
            }

            # Use transaction to ensure atomicity
            transaction = db.transaction()

            @firestore.transactional
            def place_order_transaction(transaction, order_id):
                # Update product stock
                for item in items:
                    product_ref = db.collection('products').where('name', '==', item['product']).limit(1).get()[0].reference
                    product_data = product_ref.get().to_dict()
                    new_stock = product_data['stock'] - item['quantity']
                    transaction.update(product_ref, {'stock': new_stock})

                # Create order
                order_ref = db.collection("orders").document(order_id)
                transaction.set(order_ref, order_data)

                # Clear cart
                transaction.delete(cart_ref)

            try:
                place_order_transaction(transaction, order_id)                
                # Send confirmation
                message = (
                    f"✅ Order placed successfully!\n\n"
                    f"Order ID: {order_id}\n"
                    f"Total Amount: ${order_data['total_amount']:.2f}\n\n"
                    f"You will receive a confirmation email shortly.\n"
                    f"Track your order status using the order ID."
                )
                dispatcher.utter_message(text=message)

            except Exception as e:
                logging.error(f"Transaction failed: {e}")
                dispatcher.utter_message(text="Failed to place order. Please try again.")
 
        except Exception as e:
            logging.error(f"Error placing order: {e}")
            dispatcher.utter_message(text="An error occurred while placing your order. Please try again later.")

        return []
    
########################## Action Order Status ##########################

class ActionOrderStatus(Action):
    def name(self) -> Text:
        return "action_order_status"

    def get_status_emoji(self, status: str) -> str:
        """Return appropriate emoji for order status."""
        status_emojis = {
            "placed": "📦",
            "confirmed": "✅",
            "processing": "⚙️",
            "shipped": "🚚",
            "delivered": "🏠",
            "cancelled": "❌"
        }
        return status_emojis.get(status.lower(), "❓")
    
    def format_order_details(self, order_data: Dict) -> str:
        """Format order details for display."""
        status = order_data.get("status", "unknown")
        emoji = self.get_status_emoji(status)
        
        message = (
            f"Order Status {emoji}\n\n"
            f"Order ID: {order_data.get('order_id')}\n"
            f"Status: {status.title()}\n"
            f"Placed on: {order_data.get('timestamp').strftime('%Y-%m-%d %H:%M')}\n"
            f"Total Amount: ${order_data.get('total_amount', 0):.2f}\n\n"
            "Items:\n"
        )

        for item in order_data.get('items', []):
            message += (
                f"• {item['product'].title()}\n"
                f"  Quantity: {item['quantity']}\n"
                f"  Price: ${item['price']:.2f}\n"
            )

        if status == "shipped":
            message += f"\nTracking Number: {order_data.get('tracking_number', 'N/A')}"

        return message
        
    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get order ID from tracker
        order_id = tracker.get_slot("order_id")

        # Validate order ID
        if not order_id:
            dispatcher.utter_message(text="Please provide your order ID.")
            return []
        
        try:
            # Get the order data from Firestore collection
            order_ref = db.collection("orders").document(order_id)
            order_doc = order_ref.get()

            # If the order exists, return status. otherwise return
            if order_doc.exists:
                order_data = order_doc.to_dict()
                message = self.format_order_details(order_data)
                dispatcher.utter_message(text=message)

            else:
                dispatcher.utter_message(text="I couldn't find any order with that ID.")

        except Exception as e:
            logging.error("Error checking order status: {e}")
            dispatcher.utter_message(text="An error occurred while retrieving order status. Please try again later.")

        return []
    
########################## Action FAQ ##########################

class ActionFAQ(Action):
    def name(self) -> Text:
        return "action_faq"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get FAQ topic from tracker
        faq_topic = tracker.get_slot("faq_topic")

        # Define FAQ responses in a dictionary.
        faq_responses = {
            "shipping": "Our standard shipping takes 3-5 business days.",
            "returns": "You can return your product within 30 days of purchase.",
            "payment": "We accept credit cards, debit cards, and PayPal."
        } 
        
        # If FAQ topic is provided, return the corresponding response. Otherwise, provide a general response.
        if faq_topic and faq_topic.lower() in faq_responses:
            response = faq_responses[faq_topic.lower()]
        else:
            response = "Could you please specify your query? For example, you can ask about shipping, returns, or payment."

        dispatcher.utter_message(text=response)

        return []
    
########################## Action Default NLU Fallback ##########################

class ActionDefaultFallback(Action):
    def name(self) -> Text:
        return "action_nlu_fallback"

    def run(self, dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Respond with a fallback message
        dispatcher.utter_message(
            text="I'm sorry, I didn't understand that. Can you try rephrasing your question?"
        )

        return []

########################## Action view Cart ##########################

class ActionViewCart(Action):
    def name(self) -> Text:
        return "action_view_cart"

    def check_stock_status(self, items: List[Dict]) -> List[Dict]:
        """Check current stock status for each item."""
        for item in items:
            product_ref = db.collection('products').where('name', '==', item['product']).limit(1).get()
            if product_ref:
                product = product_ref[0].to_dict()
                item['in_stock'] = product.get('stock', 0) >= item['quantity']
                item['available_stock'] = product.get('stock', 0)
        return items

    def calculate_cart_total(self, items: List[Dict]) -> float:
        """Calculate total price of all items in cart."""
        return sum(item.get('price', 0) * item.get('quantity', 0) for item in items)

    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
    
        # Get user ID from tracker
        user_id = tracker.sender_id

        try:
            # Get the user's cart from Firestore collection
            cart_ref = db.collection("carts").document(user_id)
            cart_doc = cart_ref.get()

            # If the user doesn't have a cart, return
            if not cart_doc.exists:
                dispatcher.utter_message(text="Your cart is empty.")
                return []

            # If the user does have a cart, return the items in the cart
            cart_data = cart_doc.to_dict()
            items = cart_data.get("items", [])

            if not items:
                dispatcher.utter_message(text="Your cart is empty.")
                return []
            
            # Check stock status for all items
            items = self.check_stock_status(items)

            # Group items by product for better organization
            grouped_items = {}
            for item in items:
                product = item['product']
                if product in grouped_items:
                    grouped_items[product]['quantity'] += item['quantity']
                    grouped_items[product]['total'] += item['price'] * item['quantity']
                else:
                    grouped_items[product] = {
                        'quantity': item['quantity'],
                        'price': item['price'],
                        'total': item['price'] * item['quantity'],
                        'in_stock': item.get('in_stock', True),
                        'available_stock': item.get('available_stock', 0)
                    }

             # Create cart summary
            message = "🛒 Your Cart:\n\n"
            # Loop through each product
            for product, details in grouped_items.items():
                # Determine stock status with emoji
                if details['in_stock']:
                    stock_status = "✅ In Stock"
                else:
                    stock_status = f"⚠️ Only {details['available_stock']} available"

                message += (
                    f"• {product.title()}\n"           
                    f"  Quantity: {details['quantity']}\n"    
                    f"  Price: ${details['price']:.2f} each\n"  
                    f"  Subtotal: ${details['total']:.2f}\n"    
                    f"  Status: {stock_status}\n\n"           
                )

            # Add cart total
            cart_total = self.calculate_cart_total(items)
            message += f"\nTotal: ${cart_total:.2f}"

            # Add warning for out-of-stock items
            out_of_stock = [p for p, d in grouped_items.items() if not d['in_stock']]
            if out_of_stock:
                message += "\n\n⚠️ Some items have insufficient stock. Please update quantities."

            dispatcher.utter_message(text=message)

        except Exception as e:
            logging.error(f"Error retrieving cart: {e}")
            dispatcher.utter_message(text="An error occurred while retrieving your cart.")

        return []
    