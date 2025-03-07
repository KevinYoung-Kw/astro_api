from flask import Flask, request, abort, Blueprint, jsonify
from bs4 import BeautifulSoup
import requests
import os
import json
from datetime import datetime
import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Import OpenCC for Chinese conversion
try:
    from opencc import OpenCC
    OPENCC_AVAILABLE = True
except ImportError:
    OPENCC_AVAILABLE = False
    logging.warning("OpenCC not available. Chinese conversion will not work.")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache storage
CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(CACHE_DIR, "astro_cache.json")
cache = {}
scheduler = None

# Initialize Chinese converter
t2s_converter = None
if OPENCC_AVAILABLE:
    try:
        t2s_converter = OpenCC('t2s')  # Traditional to Simplified
        logger.info("Traditional to Simplified Chinese converter loaded")
    except Exception as e:
        logger.error(f"Error initializing OpenCC: {e}")
        OPENCC_AVAILABLE = False

def convert_to_simplified(text):
    """Convert traditional Chinese text to simplified Chinese"""
    if OPENCC_AVAILABLE and t2s_converter:
        return t2s_converter.convert(text)
    return text  # Return original if conversion not available

def load_cache():
    """Load cache from file if exists"""
    global cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            logger.info("Cache loaded successfully")
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
        cache = {}

def save_cache():
    """Save cache to file"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info("Cache saved successfully")
    except Exception as e:
        logger.error(f"Error saving cache: {e}")

def is_cache_valid(num):
    """Check if cache is still valid (same day)"""
    today = datetime.now().strftime("%Y-%m-%d")
    return (str(num) in cache and 
            'date' in cache[str(num)] and 
            cache[str(num)]['date'] == today)

def fetch_astro_data(num, force_update=False):
    """Fetch astrology data from source website"""
    # If data is in cache and valid, return it unless force_update is True
    if not force_update and is_cache_valid(num):
        logger.debug(f"Using valid cache for astrology {num}")
        return cache[str(num)]
        
    try:
        r = requests.get(f'http://astro.click108.com.tw/daily_{num}.php?iAstro={num}')
        r.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(r.text, 'html.parser')
        astro = soup.select("div.TODAY_CONTENT > h3")[0]
        items = soup.select("div.TODAY_CONTENT > p")
        
        # Format data - Store both raw HTML response and structured data
        result = {
            "title": astro.text,
            "items": [item.text for item in items],
            "html": astro.text + "<br>" + "<br>".join([item.text + "<br>" for item in items]),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat()
        }
        
        # Update cache
        cache[str(num)] = result
        return result
    except Exception as e:
        logger.error(f"Error fetching astrology data: {e}")
        raise

def fetch_all_astro_data():
    """Fetch data for all 12 astrology signs"""
    logger.info("Scheduled job: Fetching data for all astrology signs")
    updated = False
    
    for num in range(12):  # 0-11 for the 12 signs
        try:
            # Check if current data is different from cached data
            if needs_update(num):
                logger.info(f"Updating data for astrology sign {num}")
                fetch_astro_data(num, force_update=True)
                updated = True
            else:
                logger.info(f"No updates needed for astrology sign {num}")
        except Exception as e:
            logger.error(f"Error updating astrology sign {num}: {e}")
    
    # Save cache if any updates were made
    if updated:
        logger.info("Updates found, saving cache")
        save_cache()
    else:
        logger.info("No updates found for any astrology sign")

def needs_update(num):
    """Check if the astrology data needs to be updated"""
    try:
        # If not in cache or not valid for today, definitely needs update
        if str(num) not in cache or not is_cache_valid(num):
            return True
            
        # Fetch current data without saving to cache
        r = requests.get(f'http://astro.click108.com.tw/daily_{num}.php?iAstro={num}')
        r.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.select("div.TODAY_CONTENT > p")
        current_items = [item.text for item in items]
        
        # Compare with cached items
        if str(num) in cache and 'items' in cache[str(num)]:
            cached_items = cache[str(num)]['items']
            # Check if content has changed
            if cached_items != current_items:
                logger.info(f"Content changed for astrology {num}")
                return True
                
        return False
    except Exception as e:
        logger.error(f"Error checking for updates for astrology {num}: {e}")
        # In case of error, assume update is needed
        return True

def setup_scheduler():
    """Set up the scheduler for periodic data fetching"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
    
    scheduler = BackgroundScheduler()
    # Schedule jobs at 8:00 AM and 8:00 PM every day
    scheduler.add_job(
        fetch_all_astro_data, 
        CronTrigger(hour='8,20'), 
        id='fetch_astro_morning_evening'
    )
    
    # Add a job that runs immediately when the app starts
    scheduler.add_job(
        fetch_all_astro_data, 
        id='fetch_astro_startup'
    )
    
    scheduler.start()
    logger.info("Scheduler started with jobs at 8:00 AM and 8:00 PM")

# Create Flask app
app = Flask(__name__)

# 保留原有的路由和功能
@app.route("/astro_api", methods=['GET'])
def astro_api():
    if request.method == 'GET':
        try:
            num = int(request.values['num'])
        except (KeyError, ValueError):
            abort(400, "Missing or invalid 'num' parameter")
            
    if (num > 11) or (num < 0):
        abort(400, "Invalid astrology number (must be 0-11)")
    
    # 检查是否需要转换为简体中文
    convert_to_simple = request.args.get('convert', '').lower() in ['1', 'true', 'yes', 'y']
    
    # 检查缓存
    if is_cache_valid(num):
        logger.info(f"Serving cached data for astrology {num}")
        resp_data = cache[str(num)]["html"]
    else:
        logger.info(f"Fetching fresh data for astrology {num}")
        try:
            data = fetch_astro_data(num)
            # Cache is updated within fetch_astro_data
            save_cache()
            resp_data = data["html"]
        except Exception:
            # 如果获取失败且缓存中存在该星座数据(即使不是今天的)，则使用缓存数据
            if str(num) in cache:
                logger.warning(f"Using outdated cache for astrology {num} due to fetch error")
                resp_data = cache[str(num)]["html"]
            else:
                abort(500, "Failed to fetch astrology data")
    
    # 如果需要，转换为简体中文
    if convert_to_simple:
        if OPENCC_AVAILABLE:
            resp_data = convert_to_simplified(resp_data)
        else:
            logger.warning("Traditional to Simplified conversion requested but OpenCC not available")
    
    return resp_data

# 新增API路由
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route("/astro/<int:num>", methods=['GET'])
def astro_json_api(num):
    """API endpoint to get astrology data in JSON format"""
    try:
        if not (0 <= num <= 11):
            return jsonify({"error": "Invalid astrology number (must be 0-11)"}), 400
        
        # 检查是否需要转换为简体中文
        convert_to_simple = request.args.get('convert', '').lower() in ['1', 'true', 'yes', 'y']
        
        # Check cache first
        if is_cache_valid(num):
            logger.info(f"Serving cached data for astrology {num}")
            data = cache[str(num)]
        else:
            logger.info(f"Fetching fresh data for astrology {num}")
            try:
                data = fetch_astro_data(num)
                # Cache is updated within fetch_astro_data
                save_cache()
            except Exception as e:
                # 如果获取失败且缓存中存在该星座数据，则使用缓存数据
                if str(num) in cache:
                    logger.warning(f"Using outdated cache for astrology {num} due to fetch error: {e}")
                    data = cache[str(num)]
                else:
                    return jsonify({"error": "Failed to fetch astrology data"}), 500
        
        # 如果需要，转换为简体中文
        if convert_to_simple and OPENCC_AVAILABLE:
            response_data = {
                "title": convert_to_simplified(data["title"]),
                "items": [convert_to_simplified(item) for item in data["items"]],
                "date": data["date"],
                "simplified": True
            }
        else:
            response_data = {
                "title": data["title"],
                "items": data["items"],
                "date": data["date"],
                "simplified": False
            }
        
        # Return data in JSON format
        return jsonify(response_data)
            
    except Exception as e:
        logger.error(f"Error in API: {e}")
        return jsonify({"error": "Internal server error"}), 500

# Add route to manually trigger update
@api_bp.route("/update", methods=['GET'])
def manual_update():
    """Endpoint to manually trigger astrology data update"""
    try:
        fetch_all_astro_data()
        return jsonify({"status": "success", "message": "Data update triggered successfully"})
    except Exception as e:
        logger.error(f"Error triggering data update: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Register blueprint
app.register_blueprint(api_bp)

def create_app():
    """Application factory function for WSGI servers"""
    # Load cache when app starts
    load_cache()
    
    # Fetch all astrology data immediately
    logger.info("Application startup: Fetching all astrology data")
    try:
        fetch_all_astro_data()  # Synchronously fetch data at startup
    except Exception as e:
        logger.error(f"Error fetching astrology data at startup: {e}")
    
    # Set up the scheduler for future updates
    setup_scheduler()
    return app

if __name__ == "__main__":
    # Load cache at startup
    load_cache()
    
    # Fetch all astrology data immediately
    logger.info("Application startup: Fetching all astrology data")
    try:
        fetch_all_astro_data()  # Synchronously fetch data at startup
    except Exception as e:
        logger.error(f"Error fetching astrology data at startup: {e}")
    
    # Set up scheduler
    setup_scheduler()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)