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
                return dispatcher.utter_message(text="We don't have any featured categories at the moment.")
            
            # Format response
            category_list = []
            for category in categories:
                cat_data = category.to_dict()
                title = cat_data.get('Name', 'Unnamed category')
                category_list.append(f"• {title}")
            
            if category_list:
                message = "Here are our featured categories:\n" + "\n".join(category_list)
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="We don't have any featured categories at the moment.")
                
        except Exception as e:
            logging.error(f"Error fetching categories: {e}")
            dispatcher.utter_message(text="Sorry, we're having trouble accessing categories. Please try again later.") 

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
                dispatcher.utter_message(text="We don't have any featured brands at the moment.")
                return []
    
            # Format response
            brand_list = []
            for brand in brands:
                brand_data = brand.to_dict()
                title = brand_data.get('Name', 'Unnamed brand')
                productCount = brand_data.get('ProductsCount', 0)
                brand_list.append(f"• {title} ({productCount} products)")
            
            if brand_list:
                message = "Here are our brands:\n" + "\n".join(brand_list)
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="We don't have any featured brands at the moment.")
                
        except Exception as e:
            logging.error(f"Error fetching brands: {e}")
            dispatcher.utter_message(text="Sorry, we're having trouble accessing brands. Please try again later.") 
            
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
                dispatcher.utter_message(text="We don't have any products at the moment.")
                return []
            
            # Format response
            product_list = []
            for product in products:
                product_data = product.to_dict()
                title = product_data.get('Title', 'Unnamed product')
                price = product_data.get('Price', 0)
                sale_price = product_data.get('SalePrice', 0)
                stock = product_data.get('Stock', 0)

                if sale_price > 0:
                    product_list.append(f"• {title} - ₹{price} (On sale: ₹{sale_price} - {stock} in stock)")
                else:
                    product_list.append(f"• {title} - ₹{price} - {stock} in stock")
            
            if product_list:
                message = "Here are our products:\n" + "\n".join(product_list)
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text="We don't have any products at the moment.")
                
        except Exception as e:
            logging.error(f"Error fetching products: {e}")
            dispatcher.utter_message(text="Sorry, we're having trouble accessing products. Please try again later.") 
            
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
                dispatcher.utter_message(text="Could you please specify the product you're looking for?")
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
                message = f"Here are products matching '{product_name}':\n"
                for product in matching_products[:5]:
                    if product['sale_price'] > 0:
                        message += f"• {product['title']} - ₹{product['price']} (On sale: ₹{product['sale_price']}) - {product['stock']} in stock\n"
                    else:
                        message += f"• {product['title']} - ₹{product['price']} - {product['stock']} in stock\n"
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"We couldn't find any products matching '{product_name}'. Would you like to try a different search?")
                
        except Exception as e:
            logging.error(f"Error searching for product: {e}")
            dispatcher.utter_message(text="Sorry, we're having trouble searching products. Please try again later.") 
            
        return []

######################## Search Product By Price ########################

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
                dispatcher.utter_message(text="Please provide valid price range numbers.")
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
                message = f"Products between ${min_price} and ${max_price}:\n"
                message += "\n".join(format_product(product) for product[:5])
                
                if len(matching_products) > 5:
                    message += f"\n... and {len(matching_products) - 5} more products"
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"No products found between ${min_price} and ${max_price}.")
                
        except Exception as e:
            logging.error(f"Error searching products by price: {e}")
            dispatcher.utter_message(text="Sorry, I'm having trouble searching products by price range.")
            
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
                dispatcher.utter_message(text="I'm not sure which category you're interested in. Could you specify a category?")
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
                dispatcher.utter_message(text=f"I couldn't find a category named '{category_name}'. Would you like to see all our categories?")
                return []
            
            # Now get products in this category
            products_ref = db.collection('Products').where('CategoryId', '==', category_id).limit(10)
            products = products_ref.get()
            
            if not products:
                dispatcher.utter_message(text=f"We don't have any products in the '{category_name}' category at the moment.")
                return []
            
            # Format response
            product_list = []
            for product in products:
                product_data = product.to_dict()
                title = product_data.get('Title', 'Unnamed product')
                price = product_data.get('Price', 0)
                sale_price = product_data.get('SalePrice', 0)
                
                if sale_price > 0:
                    product_list.append(f"• {title} - ${price} (On sale: ${sale_price})")
                else:
                    product_list.append(f"• {title} - ${price}")
            
            if product_list:
                message = f"Here are products in the '{category_name}' category:\n" + "\n".join(product_list)
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"We don't have any products in the '{category_name}' category at the moment.")
                
        except Exception as e:
            logging.error(f"Error fetching products by category: {e}")
            dispatcher.utter_message(text="Sorry, I'm having trouble retrieving products by category right now.")
            
        return []

######################## Show Products By Category ########################

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
                dispatcher.utter_message(text="I'm not sure which brand you're interested in. Could you specify a brand?")
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
                    
                    product_info = {
                        'title': title,
                        'price': price,
                        'sale_price': sale_price
                    }
                    matching_products.append(product_info)
            
            if matching_products:
                message = f"Here are products from '{brand_name}':\n"
                for product in matching_products[:5]:
                    if product['sale_price'] > 0:
                        message += f"• {product['title']} - ${product['price']} (On sale: ${product['sale_price']})\n"
                    else:
                        message += f"• {product['title']} - ${product['price']}\n"
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"I couldn't find any products from the brand '{brand_name}'. Would you like to see all our brands?")
                
        except Exception as e:
            logging.error(f"Error fetching products by brand: {e}")
            dispatcher.utter_message(text="Sorry, I'm having trouble retrieving products by brand right now.")
            
        return []