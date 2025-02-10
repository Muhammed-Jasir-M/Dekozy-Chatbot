from datetime import datetime  # For handling dates and times
import logging  # For logging errors and info messages
import random  # For generating random order ID suffixes
import string  # For generating random order ID suffixes
from typing import Any, Text, Dict, List, Tuple  # For type annotations

from rasa_sdk import Action, Tracker  # Base class for custom Rasa actions and tracker for conversation state
from rasa_sdk.executor import CollectingDispatcher  # For sending messages back to the user

import firebase_admin  # Firebase admin SDK for connecting to Firebase
from firebase_admin import credentials, firestore  # For credential management and Firestore database interactions

########################## Initialize Firebase ##########################

try:
    # Load Firebase credentials from the JSON file and initialize the Firebase app
    cred = credentials.Certificate("./aura-kart-firebase-adminsdk-448ve-f76ba9a07e.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()  # Create a Firestore client instance
    logging.info("Firebase initialized successfully")
except Exception as e:
    # Log any errors encountered during Firebase initialization
    logging.error(f"Firebase initialization error: {e}")

########################## Action Search Product ##########################

class ActionSearchProduct(Action):
    def name(self) -> Text:
        # Return the name of the action to be used in the Rasa domain
        return "action_search_product"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Retrieve the product slot value from the user's input
        product = tracker.get_slot("product")

        # Validate if a product was provided; if not, ask the user to specify one
        if not product:
            dispatcher.utter_message(text="Could you please specify what product you're looking for?")
            return []
        
        try: 
            # Convert product name to lowercase for consistent querying
            product = product.lower()

            # Access the 'products' collection in Firestore
            products_ref = db.collection('products')
            # Query Firestore for products whose name starts with the input string
            query = products_ref.where('name', '>=', product)\
                            .where('name', '<=', product + '\uf8ff')\
                            .limit(5)\
                            .get()          
                  
            # If no product is found, notify the user
            if not query:
                dispatcher.utter_message(text=f"Sorry, I couldn't find {product} in our store.")
                return []
                
            # Process each document (product) found in the query
            products_found = []
            for doc in query:
                product_data = doc.to_dict()  # Convert document to dictionary
                products_found.append(
                    f"• {product_data.get('name', 'N/A')}:\n"
                    f"  Price: ${product_data.get('price', 'N/A')}\n"
                    f"  Stock: {product_data.get('stock', 'N/A')} units\n"
                    f"  ID: {doc.id}\n"
                )
            
            # Build and send the response message with product details
            response = "Here's what I found:\n\n" + "\n".join(products_found)
            dispatcher.utter_message(text=response)

        except Exception as e:
            # Log and notify the user if an error occurs during the search
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
        
        # Retrieve the user's ID and the product/quantity from slots
        user_id = tracker.sender_id
        product = tracker.get_slot("product")
        quantity = tracker.get_slot("quantity") or 1

        # Validate and convert quantity to an integer
        try:
            quantity = int(quantity)
        except ValueError:
            dispatcher.utter_message(text="Please provide a valid quantity.")
            return []

        # Validate if product input is provided
        if not product:
            dispatcher.utter_message(text="Please specify the product you want to add.")
            return []

        try:
            # Normalize the product name
            product = product.lower()

            # Check if the product exists and retrieve its data from Firestore
            product_ref = db.collection('products').where('name', '==', product).limit(1).get()
            if not product_ref:
                dispatcher.utter_message(text=f"Sorry, {product} is not available.")
                return []
            
            product_data = product_ref[0].to_dict()
            
            # Check if enough stock is available
            if product_data.get('stock', 0) < quantity:
                dispatcher.utter_message(text=f"Sorry, only {product_data.get('stock')} units available.")
                return []

            # Retrieve or create the user's cart from Firestore
            cart_ref = db.collection('carts').document(user_id)
            cart_doc = cart_ref.get()
            if cart_doc.exists: 
                cart_data = cart_doc.to_dict()
                cart = cart_data.get("items", [])
            else:
                cart = []

            # Check if the product is already in the cart
            product_in_cart = next((item for item in cart if item["product"] == product), None)
            price = product_data.get('price', 0)
 
            if product_in_cart:
                # Update the quantity and total if the product is already in the cart
                product_in_cart["quantity"] += quantity
                product_in_cart["total"] = product_in_cart["quantity"] * price
                response = f"Updated {product} quantity to {product_in_cart['quantity']} in your cart."
            else:
                # Otherwise, add the product as a new item in the cart
                cart.append({
                    "product": product,
                    "quantity": quantity,
                    "price": price,
                    "total": quantity * price
                })                
                response = f"Added {quantity} {product}(s) to your cart."            
                        
            # Update the user's cart in Firestore
            cart_ref.set({'items': cart}, merge=True)
            dispatcher.utter_message(text=response)
            
        except Exception as e:
            # Log and notify the user if an error occurs while adding to the cart
            logging.error(f"Error adding to cart: {e}")
            dispatcher.utter_message(text="An error occurred while adding the product to your cart.")

        return []

########################## Action Place Order ##########################

class ActionPlaceOrder(Action):
    def name(self) -> Text:
        return "action_place_order"
    
    def generate_order_id(self) -> str:
        """Generate a unique order ID using the current timestamp and a random suffix."""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"ORD-{timestamp}-{random_suffix}"

    def validate_stock(self, items: List[Dict]) -> Tuple[bool, List[str]]:
        """Validate that there is sufficient stock for all items in the cart."""
        out_of_stock = []
        for item in items:
            product_ref = db.collection('products').where('name', '==', item['product']).limit(1).get()
            if product_ref:
                product = product_ref[0].to_dict()
                if product.get('stock', 0) < item['quantity']:
                    out_of_stock.append(item['product'])
        # Return a tuple: (True if all items are in stock, list of items with insufficient stock)
        return len(out_of_stock) == 0, out_of_stock
    
    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
    
        # Retrieve the user's ID from the conversation tracker
        user_id = tracker.sender_id

        try:
            # Retrieve the user's cart from Firestore
            cart_ref = db.collection("carts").document(user_id)
            cart_doc = cart_ref.get()

            # Check if the cart exists and is not empty
            if not cart_doc.exists:
                dispatcher.utter_message(text="Your cart is empty.")
                return []
    
            cart_data = cart_doc.to_dict()
            items = cart_data.get("items", [])
            if not items:
                dispatcher.utter_message(text="Your cart is empty.")
                return []
            
            # Validate stock availability for all items in the cart
            stock_valid, out_of_stock = self.validate_stock(items)
            if not stock_valid:
                message = "Cannot place order. These items have insufficient stock:\n"
                message += "\n".join([f"• {item}" for item in out_of_stock])
                dispatcher.utter_message(text=message)
                return []
            
            # Create order details including a unique order ID and total amount
            order_id = self.generate_order_id()
            order_data = {
                "order_id": order_id,
                "user_id": user_id,
                "items": items,
                "status": "placed",
                "timestamp": firestore.SERVER_TIMESTAMP,
                "total_amount": sum(item['price'] * item['quantity'] for item in items)
            }

            # Begin a Firestore transaction to ensure atomic updates
            transaction = db.transaction()

            @firestore.transactional
            def place_order_transaction(transaction, order_id):
                # Loop through each item to update the stock in the products collection
                for item in items:
                    product_ref = db.collection('products').where('name', '==', item['product']).limit(1).get()[0].reference
                    product_data = product_ref.get().to_dict()
                    new_stock = product_data['stock'] - item['quantity']
                    transaction.update(product_ref, {'stock': new_stock})

                # Create a new order document in the orders collection
                order_ref = db.collection("orders").document(order_id)
                transaction.set(order_ref, order_data)

                # Delete the cart document as the order has been placed
                transaction.delete(cart_ref)

            try:
                # Execute the transaction
                place_order_transaction(transaction, order_id)                
                # Send order confirmation to the user with details
                message = (
                    f"✅ Order placed successfully!\n\n"
                    f"Order ID: {order_id}\n"
                    f"Total Amount: ${order_data['total_amount']:.2f}\n\n"
                    f"You will receive a confirmation email shortly.\n"
                    f"Track your order status using the order ID."
                )
                dispatcher.utter_message(text=message)

            except Exception as e:
                # Log and notify the user if the transaction fails
                logging.error(f"Transaction failed: {e}")
                dispatcher.utter_message(text="Failed to place order. Please try again.")
 
        except Exception as e:
            # Log and notify the user if an error occurs while placing the order
            logging.error(f"Error placing order: {e}")
            dispatcher.utter_message(text="An error occurred while placing your order. Please try again later.")

        return []
    
########################## Action Order Status ##########################

class ActionOrderStatus(Action):
    def name(self) -> Text:
        return "action_order_status"

    def get_status_emoji(self, status: str) -> str:
        """Return an emoji that corresponds to the order status."""
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
        """Format the order details into a readable message."""
        status = order_data.get("status", "unknown")
        emoji = self.get_status_emoji(status)
        
        # Build the message with order details and status emoji
        message = (
            f"Order Status {emoji}\n\n"
            f"Order ID: {order_data.get('order_id')}\n"
            f"Status: {status.title()}\n"
            f"Placed on: {order_data.get('timestamp').strftime('%Y-%m-%d %H:%M')}\n"
            f"Total Amount: ${order_data.get('total_amount', 0):.2f}\n\n"
            "Items:\n"
        )

        # Append details for each item in the order
        for item in order_data.get('items', []):
            message += (
                f"• {item['product'].title()}\n"
                f"  Quantity: {item['quantity']}\n"
                f"  Price: ${item['price']:.2f}\n"
            )

        # If the order is shipped, include tracking information
        if status == "shipped":
            message += f"\nTracking Number: {order_data.get('tracking_number', 'N/A')}"

        return message
        
    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Retrieve the order ID from the user's input
        order_id = tracker.get_slot("order_id")

        # Validate if an order ID was provided
        if not order_id:
            dispatcher.utter_message(text="Please provide your order ID.")
            return []
        
        try:
            # Retrieve the order document from Firestore using the provided order ID
            order_ref = db.collection("orders").document(order_id)
            order_doc = order_ref.get()

            # If the order exists, format and send its details; otherwise, notify the user
            if order_doc.exists:
                order_data = order_doc.to_dict()
                message = self.format_order_details(order_data)
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="I couldn't find any order with that ID.")

        except Exception as e:
            # Log and notify the user if an error occurs while retrieving order status
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
        
        # Retrieve the FAQ topic provided by the user
        faq_topic = tracker.get_slot("faq_topic")

        # Predefined FAQ responses for common topics
        faq_responses = {
            "shipping": "Our standard shipping takes 3-5 business days.",
            "returns": "You can return your product within 30 days of purchase.",
            "payment": "We accept credit cards, debit cards, and PayPal."
        } 
        
        # If a recognized FAQ topic is provided, return its answer; otherwise, ask for clarification
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
        
        # Respond with a generic fallback message if the user's intent cannot be determined
        dispatcher.utter_message(
            text="I'm sorry, I didn't understand that. Can you try rephrasing your question?"
        )
        return []
    
########################## Action View Cart ##########################

class ActionViewCart(Action):
    def name(self) -> Text:
        return "action_view_cart"

    def check_stock_status(self, items: List[Dict]) -> List[Dict]:
        """Check the current stock status for each item in the cart."""
        for item in items:
            product_ref = db.collection('products').where('name', '==', item['product']).limit(1).get()
            if product_ref:
                product = product_ref[0].to_dict()
                # Mark item as in stock if available stock meets or exceeds desired quantity
                item['in_stock'] = product.get('stock', 0) >= item['quantity']
                item['available_stock'] = product.get('stock', 0)
        return items

    def calculate_cart_total(self, items: List[Dict]) -> float:
        """Calculate the total price for all items in the cart."""
        return sum(item.get('price', 0) * item.get('quantity', 0) for item in items)

    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
    
        # Retrieve the user's ID from the conversation tracker
        user_id = tracker.sender_id

        try:
            # Fetch the user's cart document from Firestore
            cart_ref = db.collection("carts").document(user_id)
            cart_doc = cart_ref.get()

            # If the cart does not exist or is empty, inform the user
            if not cart_doc.exists:
                dispatcher.utter_message(text="Your cart is empty.")
                return []

            cart_data = cart_doc.to_dict()
            items = cart_data.get("items", [])
            if not items:
                dispatcher.utter_message(text="Your cart is empty.")
                return []
            
            # Check the stock status of each item in the cart
            items = self.check_stock_status(items)

            # Group items by product name to consolidate quantities and totals
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

            # Build the cart summary message with details for each product
            message = "🛒 Your Cart:\n\n"
            for product, details in grouped_items.items():
                # Determine the stock status and corresponding emoji
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

            # Calculate and append the overall total for the cart
            cart_total = self.calculate_cart_total(items)
            message += f"\nTotal: ${cart_total:.2f}"

            # Warn the user if any items have insufficient stock
            out_of_stock = [p for p, d in grouped_items.items() if not d['in_stock']]
            if out_of_stock:
                message += "\n\n⚠️ Some items have insufficient stock. Please update quantities."

            dispatcher.utter_message(text=message)

        except Exception as e:
            # Log and notify the user if an error occurs while retrieving the cart
            logging.error(f"Error retrieving cart: {e}")
            dispatcher.utter_message(text="An error occurred while retrieving your cart.")

        return []

########################## Action Add To Wishlist ##########################

class ActionAddToWishlist(Action):
    def name(self) -> Text:
        return "action_add_to_wishlist"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Retrieve user ID and product slot value
        user_id = tracker.sender_id
        product = tracker.get_slot("product")

        # Validate if a product is specified
        if not product:
            dispatcher.utter_message(text="Please specify a product to add to wishlist.")
            return []

        try:
            # Check if the product exists in Firestore
            product_ref = db.collection('products').where('name', '==', product.lower()).limit(1).get()
            if not product_ref:
                dispatcher.utter_message(text=f"Product {product} not found.")
                return []

            # Add the product to the user's wishlist using an array union operation
            wishlist_ref = db.collection('wishlists').document(user_id)
            wishlist_ref.set({
                'items': firestore.ArrayUnion([{
                    'product': product.lower(),
                    'added_at': firestore.SERVER_TIMESTAMP
                }])
            }, merge=True)

            dispatcher.utter_message(text=f"{product} added to your wishlist!")

        except Exception as e:
            # Log and notify the user if an error occurs while adding to the wishlist
            logging.error(f"Wishlist error: {e}")
            dispatcher.utter_message(text="Error adding to wishlist.")

        return []

########################## Action View Wishlist ##########################

class ActionViewWishlist(Action):
    def name(self) -> Text:
        return "action_view_wishlist"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Retrieve the user ID from the tracker
        user_id = tracker.sender_id

        try:
            # Get the user's wishlist document from Firestore
            wishlist_ref = db.collection('wishlists').document(user_id)
            wishlist_doc = wishlist_ref.get()

            # If the wishlist is empty or doesn't exist, inform the user
            if not wishlist_doc.exists or not wishlist_doc.to_dict().get('items'):
                dispatcher.utter_message(text="Your wishlist is empty.")
                return []

            wishlist_items = wishlist_doc.to_dict().get('items', [])
            message = "🌟 Your Wishlist:\n\n"
            
            # Loop through each item in the wishlist and fetch product details
            for item in wishlist_items:
                product_ref = db.collection('products').where('name', '==', item['product']).limit(1).get()
                if product_ref:
                    product_data = product_ref[0].to_dict()
                    message += (
                        f"• {item['product'].title()}\n"
                        f"  Price: ${product_data.get('price', 'N/A')}\n"
                        f"  Stock: {product_data.get('stock', 0)} units\n\n"
                    )

            dispatcher.utter_message(text=message)

        except Exception as e:
            # Log and notify the user if an error occurs while retrieving the wishlist
            logging.error(f"Wishlist view error: {e}")
            dispatcher.utter_message(text="Error retrieving wishlist.")

        return []

########################## Action Product Recommendations ##########################

class ActionProductRecommendations(Action):
    def name(self) -> Text:
        return "action_product_recommendations"

    def get_recommendations(self, recent_purchases):
        """Generate product recommendations based on the categories of recent purchases."""
        recommendations = []
        for purchase in recent_purchases:
            # Query for up to 3 products in the same category as the purchased item
            category_ref = db.collection('products').where('category', '==', purchase['category']).limit(3).get()
            recommendations.extend([doc.to_dict() for doc in category_ref])
        return recommendations[:5]  # Limit the recommendations to 5 items

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Retrieve the user ID
        user_id = tracker.sender_id

        try:
            # Fetch recent orders for the user from Firestore, ordered by timestamp
            orders_ref = db.collection('orders').where('user_id', '==', user_id).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(3)
            recent_orders = orders_ref.get()

            recent_purchases = []
            # Extract purchased items from recent orders
            for order in recent_orders:
                order_data = order.to_dict()
                recent_purchases.extend(order_data.get('items', []))

            # Generate recommendations based on recent purchases
            recommendations = self.get_recommendations(recent_purchases)

            if not recommendations:
                dispatcher.utter_message(text="No personalized recommendations at the moment.")
                return []

            # Build the recommendations message
            message = "🎁 Recommended for You:\n\n"
            for product in recommendations:
                message += (
                    f"• {product.get('name', 'N/A').title()}\n"
                    f"  Price: ${product.get('price', 'N/A')}\n"
                    f"  Category: {product.get('category', 'N/A')}\n\n"
                )

            dispatcher.utter_message(text=message)

        except Exception as e:
            # Log and notify the user if an error occurs while generating recommendations
            logging.error(f"Recommendation error: {e}")
            dispatcher.utter_message(text="Error generating recommendations.")

        return []
    
########################## Action Remove From Wishlist ##########################

class ActionRemoveFromWishlist(Action):
    def name(self) -> Text:
        return "action_remove_from_wishlist"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Retrieve user ID and product from the tracker
        user_id = tracker.sender_id
        product = tracker.get_slot("product")

        # Validate if a product is specified for removal
        if not product:
            dispatcher.utter_message(text="Please specify a product to remove from wishlist.")
            return []

        try:
            # Remove the specified product from the wishlist using an array removal operation
            wishlist_ref = db.collection('wishlists').document(user_id)
            wishlist_ref.update({
                'items': firestore.ArrayRemove([{
                    'product': product.lower()
                }])
            })

            dispatcher.utter_message(text=f"{product} removed from your wishlist.")

        except Exception as e:
            # Log and notify the user if an error occurs while removing the product from the wishlist
            logging.error(f"Wishlist removal error: {e}")
            dispatcher.utter_message(text="Error removing from wishlist.")

        return []
