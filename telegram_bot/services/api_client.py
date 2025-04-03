import json
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")
logger = logging.getLogger(__name__)


class ApiClient:
    @staticmethod
    def update_order_status(order_id, status):
        """Обновить статус заказа"""
        try:
            data = {"status": status}
            logger.info(f"Updating order {order_id} status to {status}")
            response = requests.patch(f"{API_BASE_URL}/orders/{order_id}/", json=data)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Order {order_id} status updated successfully")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating order status: {str(e)}")
            if hasattr(e, "response") and e.response:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            return {"error": str(e)}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response: {str(e)}")
            return {"error": f"Error decoding JSON response: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error updating order status: {str(e)}")
            return {"error": str(e)}
