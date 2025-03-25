import os
import json
import logging
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

import firebase_admin
from firebase_admin import credentials, firestore

######################## Initialize Firebase ########################

def initialize_firebase():
    """Initialize Firebase with either environment variable or local credentials file."""
    try:
        if not firebase_admin._apps:
            # First, try to use environment variable (for Render deployment)
            firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
            if firebase_creds_json:
                # Parse the JSON string from environment variable
                cred_dict = json.loads(firebase_creds_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                logging.info("Firebase initialized successfully from environment variable")
            else:
                # Fallback to local file for development
                cred_path = os.environ.get('FIREBASE_CREDENTIALS_PATH', './aura-kart-firebase-adminsdk-448ve-f76ba9a07e.json')
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logging.info(f"Firebase initialized successfully from local file: {cred_path}")
        else:
            logging.info("Firebase already initialized")
            
        return firestore.client()
    except Exception as e:
        logging.error(f"Firebase initialization error: {e}")
        return None

# Initialize Firebase and get db client
db = initialize_firebase()

######################## Show Categories ########################

class ActionShowCategories(Action):
    def name(self) -> Text:
        return "action_show_categories"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            # Get featured categories from Firestore
            categories_ref = db.collection('Categories').where('IsFeatured', '==', True)
            categories = categories_ref.get()
            
            if not categories:
                dispatcher.utter_message(text="🏷️ Our category showcase is taking a quick break. Check back soon for exciting updates!")
                return []
            
            # Format response
            category_list = []
            for category in categories:
                cat_data = category.to_dict()
                if not cat_data.get('ParentId'):
                    title = cat_data.get('Name', 'Unnamed Category')
                    
                    # Find subcategories for this category
                    subcategories = db.collection('Categories').where('parentId', '==', category.id).get()
                    subcategory_names = [sub.to_dict().get('Name', 'Unnamed Subcategory') for sub in subcategories]
                    
                    if subcategory_names:
                        category_list.append(f"🌟 {title} (Subcategories: {', '.join(subcategory_names)})")
                    else:
                        category_list.append(f"🌟 {title}")
  
            message = "🌈 Discover Our Featured Categories:\n" + "\n".join(category_list)
            dispatcher.utter_message(text=message)
                
        except Exception as e:
            logging.error(f"Error fetching categories: {e}")
            dispatcher.utter_message(text="🤖 Oops! Our category navigator is temporarily out of service. Please try again later.") 

        return []

######################## Show Brands ########################

class ActionShowBrands(Action):
    def name(self) -> Text:
        return "action_show_brands"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            # Get featured brands from Firestore
            brands_ref = db.collection('Brands').where('IsFeatured', '==', True)
            brands = brands_ref.get()
            
            if not brands:
                dispatcher.utter_message(text="🏢 Our brand showcase is taking a short break. Exciting brands coming soon!")
                return []
    
            # Format response
            brand_list = []
            for brand in brands:
                brand_data = brand.to_dict()
                title = brand_data.get('Name', 'Unnamed Brand')
                productCount = brand_data.get('ProductsCount', 0)
                brand_list.append(f"🏷️ {title} (Available Products: {productCount})")
            
            message = "🌟 Featured Brands We Love:\n" + "\n".join(brand_list)
            dispatcher.utter_message(text=message)
                
        except Exception as e:
            logging.error(f"Error fetching brands: {e}")
            dispatcher.utter_message(text="🤖 Sorry, our brand explorer is currently out of service. We'll be back soon!") 
            
        return []

######################## Show Products ########################

class ActionShowProducts(Action):
    def name(self) -> Text:
        return "action_show_products"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            # Get featured products from Firestore
            products_ref = db.collection('Products').where('IsFeatured', '==', True).limit(6)
            products = products_ref.get()
            
            if not products:
                dispatcher.utter_message(text="🛍️ Our product shelves are looking a bit empty today. New arrivals coming soon!")
                return []
            
            # Format response
            product_list = []
            for product in products:
                product_data = product.to_dict()
                title = product_data.get('Title', 'Unnamed Product')
                price = product_data.get('Price', 0)
                sale_price = product_data.get('SalePrice', 0)
                stock = product_data.get('Stock', 0)

                if sale_price > 0 and sale_price < price:
                    product_list.append(f"🔥 {title}\n   Regular Price: ₹{price}\n   🏷️ Special Offer: ₹{sale_price}\n   📦 {stock} left in stock")
                else:
                    product_list.append(f"✨ {title}\n   Price: ₹{price}\n   📦 {stock} left in stock")
            
            message = "🌈 Our Handpicked Featured Products:\n\n" + "\n\n".join(product_list)
            dispatcher.utter_message(text=message)
                
        except Exception as e:
            logging.error(f"Error fetching products: {e}")
            dispatcher.utter_message(text="🤖 Our product showcase is momentarily unavailable. We apologize for the inconvenience!") 
            
        return []

######################## Search Product By Name ########################

class ActionSearchProduct(Action):
    def name(self) -> Text:
        return "action_search_product"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            # Get the product name from the entity
            product_name = tracker.get_slot('product')
            
            if not product_name:
                dispatcher.utter_message(text="🔍 What product are you hunting for today? Let me help you find it!")
                return []
            
            products_ref = db.collection('Products')
            products = products_ref.get()
            
            search_term = product_name.lower()
            matching_products = []
            
            for product in products:
                product_data = product.to_dict()
                title = product_data.get('Title', '')
                if search_term in title.lower():
                    price = product_data.get('Price', 0)
                    sale_price = product_data.get('SalePrice', 0)
                    stock = product_data.get('Stock', 0)
                    
                    product_info = {
                        'title': title,
                        'price': price,
                        'sale_price': sale_price,
                        'stock': stock
                    }
                    matching_products.append(product_info)
            
            if matching_products:
                message = f"🔍 Results for '{product_name}':\n\n"
                for product in matching_products[:5]:
                    if product['sale_price'] > 0 and product['sale_price'] < product['price']:
                        message += (f"🌟 {product['title']}\n"
                                    f"   Regular Price: ₹{product['price']}\n"
                                    f"   🏷️ Special Offer: ₹{product['sale_price']}\n"
                                    f"   📦 {product['stock']} available\n\n")
                    else:
                        message += (f"✨ {product['title']}\n"
                                    f"   Price: ₹{product['price']}\n"
                                    f"   📦 {product['stock']} available\n\n")
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"🤷‍♀️ No matches found for '{product_name}'. Want to try a different search?")
                
        except Exception as e:
            logging.error(f"Error searching for product: {e}")
            dispatcher.utter_message(text="🤖 Our search magic is temporarily on the fritz. Please try again later!") 
            
        return []

######################## Search Product By Price Range ########################

class ActionSearchProductByPriceRange(Action):
    def name(self) -> Text:
        return "action_search_product_by_price_range"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            # Extract price range from slots or entities
            min_price = tracker.get_slot('min_price') or 0
            max_price = tracker.get_slot('max_price') or float('inf')
            
            # Validate price range
            try:
                min_price = float(min_price)
                max_price = float(max_price)
            except ValueError:
                dispatcher.utter_message(text="🚫 Oops! Please provide valid price range numbers.")
                return []
            
            # Search for products in price range
            products_ref = db.collection('Products')
            products = products_ref.get()
            
            matching_products = []
            for product in products:
                product_data = product.to_dict()
                price = product_data.get('Price', 0)
                
                if min_price <= price <= max_price:
                    matching_products.append(product_data)
            
            if matching_products:
                message = f"🔍 Products between ₹{min_price} and ₹{max_price}:\n\n"
                for product in matching_products[:5]:
                    title = product.get('Title', 'Unnamed Product')
                    price = product.get('Price', 0)
                    sale_price = product.get('SalePrice', 0)
                    stock = product.get('Stock', 0)

                    if sale_price > 0 and sale_price < price:
                        message += (f"🌟 {title}\n"
                                    f"   Regular Price: ₹{price}\n"
                                    f"   🏷️ Special Offer: ₹{sale_price}\n"
                                    f"   📦 {stock} available\n\n")
                    else:
                        message += (f"✨ {title}\n"
                                    f"   Price: ₹{price}\n"
                                    f"   📦 {stock} available\n\n")
                
                if len(matching_products) > 5:
                    message += f"... and {len(matching_products) - 5} more products"
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"🤷‍♀️ No products found between ₹{min_price} and ₹{max_price}.")
                
        except Exception as e:
            logging.error(f"Error searching products by price: {e}")
            dispatcher.utter_message(text="🤖 Sorry, I'm having trouble searching products by price range.") 
            
        return []

######################## Show Products By Category ########################

class ActionShowProductsByCategory(Action):
    def name(self) -> Text:
        return "action_show_products_by_category"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            # Get the category name from the entity
            category_name = tracker.get_slot('category')
            
            if not category_name:
                dispatcher.utter_message(text="🤔 Which category are you interested in? Let me help you explore!")
                return []
            
            # First, find the category ID by name
            categories_ref = db.collection('Categories')
            categories = categories_ref.get()
            
            category_id = None
            for category in categories:
                category_data = category.to_dict()
                if category_name.lower() in category_data.get('Name', '').lower():
                    category_id = category.id
                    break
            
            if not category_id:
                dispatcher.utter_message(text=f"🤷‍♀️ We couldn't find a category named '{category_name}'. Would you like to see all our categories?")
                return []
            
            # Now get products in this category
            products_ref = db.collection('Products').where('CategoryId', '==', category_id).limit(10)
            products = products_ref.get()
            
            if not products:
                dispatcher.utter_message(text=f"🏷️ We don't have any products in the '{category_name}' category at the moment.")
                return []
            
            # Format response
            product_list = []
            for product in products:
                product_data = product.to_dict()
                title = product_data.get('Title', 'Unnamed product')
                price = product_data.get('Price', 0)
                sale_price = product_data.get('SalePrice', 0)
                stock = product_data.get('Stock', 0)
                
                if sale_price > 0 and sale_price < price:
                    product_list.append(f"🌟 {title}\n   Regular Price: ₹{price}\n   🏷️ Special Offer: ₹{sale_price}\n   📦 {stock} available")
                else:
                    product_list.append(f"✨ {title}\n   Price: ₹{price}\n   📦 {stock} available")
            
            message = f"🏷️ Products in the '{category_name}' Category:\n\n" + "\n\n".join(product_list)
            dispatcher.utter_message(text=message)
                
        except Exception as e:
            logging.error(f"Error fetching products by category: {e}")
            dispatcher.utter_message(text="🤖 Sorry, I'm having trouble retrieving products by category right now.") 
            
        return []

######################## Show Products By Brand ########################

class ActionShowProductsByBrand(Action):
    def name(self) -> Text:
        return "action_show_products_by_brand"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            # Get the brand name from the entity
            brand_name = tracker.get_slot('brand')
            
            if not brand_name:
                dispatcher.utter_message(text="🤔 Which brand are you curious about? Let me help you explore!")
                return []
            
            products_ref = db.collection('Products')
            products = products_ref.get()
            
            # Filter products with matching brand
            matching_products = []
            for product in products:
                product_data = product.to_dict()
                brand_data = product_data.get('Brand', {})
                
                if brand_data and brand_name.lower() in brand_data.get('Name', '').lower():
                    title = product_data.get('Title', 'Unnamed product')
                    price = product_data.get('Price', 0)
                    sale_price = product_data.get('SalePrice', 0)
                    stock = product_data.get('Stock', 0)
                    
                    product_info = {
                        'title': title,
                        'price': price,
                        'sale_price': sale_price,
                        'stock': stock
                    }
                    matching_products.append(product_info)
            
            if matching_products:
                message = f"🏷️ Products from '{brand_name}':\n\n"
                for product in matching_products[:5]:
                    if product['sale_price'] > 0 and product['sale_price'] < product['price']:
                        message += (f"🌟 {product['title']}\n"
                                    f"   Regular Price: ₹{product['price']}\n"
                                    f"   🏷️ Special Offer: ₹{product['sale_price']}\n"
                                    f"   📦 {product['stock']} available\n\n")
                    else:
                        message += (f"✨ {product['title']}\n"
                                    f"   Price: ₹{product['price']}\n"
                                    f"   📦 {product['stock']} available\n\n")
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"🤷‍♀️ No products found from the brand '{brand_name}'. Would you like to see all our brands?")
                
        except Exception as e:
            logging.error(f"Error fetching products by brand: {e}")
            dispatcher.utter_message(text="🤖 Sorry, I'm having trouble retrieving products by brand right now.") 
            
        return []

######################## Order Status Tracking ########################

class ActionTrackOrder(Action):
    def name(self) -> Text:
        return "action_track_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            order_id = tracker.get_slot('order_id')
            
            if not order_id:
                dispatcher.utter_message(text="🔍 Please provide a valid order ID to track your purchase.")
                return []
            
            order_ref = db.collection('Orders').document(order_id)
            order = order_ref.get()
            
            if not order.exists:
                dispatcher.utter_message(text=f"🤷‍♀️ No order found with ID {order_id}.")
                return []
            
            order_data = order.to_dict()
            status = order_data.get('status', 'N/A')
            estimated_delivery = order_data.get('deliveryDate', 'N/A')
            items = order_data.get('items', [])
            total = order_data.get('totalAmount', 0)

            status_messages = {
                'OrderStatus.processing': '🔄 Your order is being prepared',
                'OrderStatus.shipped': '🚚 Your order is on its way',
                'OrderStatus.pending': '⏳ Your order is pending',
                'OrderStatus.delivered': '✅ Your order has been successfully delivered',
                'OrderStatus.cancelled': '❌ Your order has been cancelled'
            }
            
            friendly_status = status_messages.get(status, status)
            
            message = f"""
                🧾 Order Status Details:
                - 🏷️ Order ID: {order_id}
                - 📊 Current Status: {friendly_status}
                - 📅 Estimated Delivery: {estimated_delivery}
                - 📦 Total Items: {len(items)}
                - 💰 Total Amount: ₹{total}
            """
            
            dispatcher.utter_message(text=message)
            
        except Exception as e:
            logging.error(f"Error tracking order: {e}")
            dispatcher.utter_message(text="🤖 Sorry, we couldn't retrieve order details at the moment.") 
        
        return []

######################## User Profile ########################

class ActionUserProfile(Action):
    def name(self) -> Text:
        return "action_get_user_profile"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            user_id = tracker.get_slot('user_id')
            
            if not user_id:
                dispatcher.utter_message(text="🔍 Please provide a valid user ID.")
                return []
            
            user_ref = db.collection('Users').document(user_id)
            user = user_ref.get()
            
            if not user.exists:
                dispatcher.utter_message(text=f"🤷‍♀️ No user found with ID {user_id}.")
                return []
            
            user_data = user.to_dict()
            message = f"""
                👤 User Profile:
                - 🏷️ First Name: {user_data.get('FirstName', 'N/A')}
                - 📛 Last Name: {user_data.get('LastName', 'N/A')}
                - 🆔 Username: {user_data.get('Username', 'N/A')}
                - 📧 Email: {user_data.get('Email', 'N/A')}
                - 📞 Phone: {user_data.get('Phone', 'N/A')}
                - 📅 Joined: {user_data.get('CreatedAt', 'N/A')}
            """
            
            dispatcher.utter_message(text=message)
            
        except Exception as e:
            logging.error(f"Error retrieving user profile: {e}")
            dispatcher.utter_message(text="🤖 Sorry, we couldn't retrieve user profile details.") 
        
        return []

######################## Product Recommendations ########################

class ActionProductRecommendations(Action):
    def name(self) -> Text:
        return "action_product_recommendations"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            featured_products = (db.collection('Products')
                .where('IsFeatured', '==', True)
                .where('Stock', '>', 0)
                .limit(5)
                .get())
            
            recommendations = []
            for product in featured_products:
                product_data = product.to_dict()
                title = product_data.get('Title', 'Unnamed Product')
                price = product_data.get('Price', 0)
                sale_price = product_data.get('SalePrice', price)
                stock = product_data.get('Stock', 0)
                
                if sale_price > 0 and sale_price < price:
                    recommendation = (f"🌟 {title}\n"
                                      f"   Regular Price: ₹{price}\n"
                                      f"   🏷️ Special Offer: ₹{sale_price}\n"
                                      f"   📦 {stock} available")
                else:
                    recommendation = (f"✨ {title}\n"
                                      f"   Price: ₹{price}\n"
                                      f"   📦 {stock} available")
                recommendations.append(recommendation)
            
            if recommendations:
                message = "🌈 Recommended Products Just for You:\n\n" + "\n\n".join(recommendations)
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="🤷‍♀️ No recommendations available at the moment.")
            
        except Exception as e:
            logging.error(f"Error generating recommendations: {e}")
            dispatcher.utter_message(text="🤖 Sorry, we couldn't generate product recommendations right now.") 
        
        return []

########################.####################.########################