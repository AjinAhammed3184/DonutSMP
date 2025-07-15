import logging
import requests
import re
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import os

# --- CONFIGURATION ---

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
DONUT_SMP_API_KEY = os.environ.get('DONUT_SMP_API_KEY')

# --- SETUP LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- API CLIENT & HELPERS ---
BASE_URL = "https://api.donutsmp.net/v1"
HEADERS = {'Authorization': f'Bearer {DONUT_SMP_API_KEY}'}
LEADERBOARD_CATEGORIES = [
    'money', 'playtime', 'kills', 'deaths', 'mobskilled', 'sell',
    'shop', 'brokenblocks', 'placedblocks', 'shards'
]
ITEMS_PER_PAGE = 10

def make_api_request(endpoint: str) -> dict | list | None:
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS)
        if response.status_code in [200, 500]:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            logger.warning(f"API Error on {endpoint}: {response.status_code} - {response.text}")
            return None
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error(f"Failed to call API endpoint {endpoint}: {e}")
        return None

def escape_markdown(text: str) -> str:
    text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def format_item_id(item_id: str) -> str:
    return item_id.replace('minecraft:', '').replace('_', ' ').title()

# --- COMMAND HANDLERS ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🍩 *DonutSMP Bot Commands*\n\n"
        "`/isonline {username}`\n"
        "Checks if a player is online\.\n\n"
        "`/stats {username}`\n"
        "Shows detailed stats for a player\.\n\n"
        "`/auctions {page}`\n"
        "Lists all items currently for sale\.\n\n"
        "`/ah {item name}`\n"
        "Searches for an item on the AH \(can be very slow\)\.\n\n"
        "`/price {item name}`\n"
        "Finds the single lowest price for an item \(can be very slow\)\.\n\n"
        "`/sales {page}`\n"
        "Lists recent auction house sales\.\n\n"
        "`/leaderboard {category} {page}`\n"
        "Shows a server leaderboard\.\n\n"
        "*Available categories for leaderboard:*\n"
        f"`{', '.join(LEADERBOARD_CATEGORIES)}`"
    )
    await update.message.reply_text(help_text, parse_mode='MarkdownV2')

async def isonline_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Usage: `/isonline {username}`', parse_mode='MarkdownV2')
        return
    username = context.args[0]
    await update.message.reply_text(f"🔍 Searching for {escape_markdown(username)}\.\.\.", parse_mode='MarkdownV2')
    data = make_api_request(f"/lookup/{username}")
    if data is None:
        message = f"🤷 Player `{escape_markdown(username)}` not found\."
    elif "user is not currently online" in data.get("message", ""):
        message = f"❌ **{escape_markdown(username)}** is Offline\."
    elif data.get('status') == 200:
        player = data.get('result', {})
        location = escape_markdown(player.get('location', 'Unknown'))
        rank = escape_markdown(player.get('rank', 'Unknown'))
        message = (
            f"✅ **{escape_markdown(username)} is Online\!**\n\n"
            f"Currently on: `{location}`\n"
            f"Rank: `{rank}`"
        )
    else:
        message = "Sorry, an unknown API error occurred\."
    await update.message.reply_text(message, parse_mode='MarkdownV2')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Usage: `/stats {username}`', parse_mode='MarkdownV2')
        return
    username = context.args[0]
    await update.message.reply_text(f"📊 Fetching stats for {escape_markdown(username)}\.\.\.", parse_mode='MarkdownV2')
    data = make_api_request(f"/stats/{username}")
    if data is None:
        await update.message.reply_text(f"🤷 Player `{escape_markdown(username)}` not found\.", parse_mode='MarkdownV2')
        return
    stats = data.get('result', {})
    if not stats:
        await update.message.reply_text("Could not retrieve stats for this player\.", parse_mode='MarkdownV2')
        return
    money = int(float(stats.get('money', 0)))
    kills = int(stats.get('kills', 0))
    deaths = int(stats.get('deaths', 0))
    playtime_ms = int(stats.get('playtime', 0))
    total_seconds = playtime_ms / 1000
    days = int(total_seconds // (24 * 3600))
    hours = int((total_seconds % (24 * 3600)) // 3600)
    playtime_str = f"{days} days, {hours} hours"
    message = (
        f"*Stats for {escape_markdown(username)}*\n"
        f"💰 Money: `{escape_markdown(f'{money:,}')}`\n"
        f"⚔️ Kills: `{escape_markdown(kills)}`\n"
        f"💀 Deaths: `{escape_markdown(deaths)}`\n"
        f"⏰ Playtime: `{escape_markdown(playtime_str)}`"
    )
    await update.message.reply_text(message, parse_mode='MarkdownV2')

# --- RESTORED auctions_command ---
async def auctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page = context.args[0] if context.args else 1
    await update.message.reply_text(f"🛒 Fetching Auction House page {page}\.\.\.", parse_mode='MarkdownV2')
    data = make_api_request(f"/auction/list/{page}")
    auctions = data.get('result') if data else None
    if not auctions:
        await update.message.reply_text("No auction items found on this page\.", parse_mode='MarkdownV2')
        return
    message_parts = [f"*Auction House \- Page {page}*"]
    for item in auctions[:10]:
        item_name = escape_markdown(format_item_id(item.get('item', {}).get('id', 'Unknown')))
        seller = escape_markdown(item.get('seller', {}).get('name', 'Unknown'))
        price = f"{int(item.get('price', 0)):,}"
        message_parts.append(f"`{item_name}` from *{seller}* for \`${escape_markdown(price)}\`\.")
    await update.message.reply_text('\n'.join(message_parts), parse_mode='MarkdownV2')

# --- RESTORED sales_command ---
async def sales_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page = context.args[0] if context.args else 1
    await update.message.reply_text(f"📈 Fetching recent sales page {page}\.\.\.", parse_mode='MarkdownV2')
    data = make_api_request(f"/auction/transactions/{page}")
    sales = data.get('result') if data else None
    if not sales:
        await update.message.reply_text("No recent sales found on this page\.", parse_mode='MarkdownV2')
        return
    message_parts = [f"*Recent Sales \- Page {page}*"]
    for item in sales[:10]:
        item_name = escape_markdown(format_item_id(item.get('item', {}).get('id', 'Unknown')))
        seller = escape_markdown(item.get('seller', 'Unknown'))
        buyer = escape_markdown(item.get('buyer', 'Unknown'))
        price = f"{int(item.get('price', 0)):,}"
        message_parts.append(f"`{item_name}` sold by *{seller}* to *{buyer}* for \`${escape_markdown(price)}\`\.")
    await update.message.reply_text('\n'.join(message_parts), parse_mode='MarkdownV2')

# --- RESTORED leaderboard_command ---
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].lower() not in LEADERBOARD_CATEGORIES:
        await update.message.reply_text(f"Usage: `/leaderboard {{category}}`\.\nSee `/help` for categories\.", parse_mode='MarkdownV2')
        return
    category = context.args[0].lower()
    page = context.args[1] if len(context.args) > 1 else 1
    await update.message.reply_text(f"🏆 Fetching *{escape_markdown(category)}* leaderboard page {page}\.\.\.", parse_mode='MarkdownV2')
    data = make_api_request(f"/leaderboards/{category}/{page}")
    leaderboard_data = data.get('result') if data else None
    if not leaderboard_data:
        await update.message.reply_text(f"No data found for the *{escape_markdown(category)}* leaderboard\.", parse_mode='MarkdownV2')
        return
    message_parts = [f"*{escape_markdown(category.capitalize())} Leaderboard \- Page {page}*"]
    for i, entry in enumerate(leaderboard_data):
        rank = (int(page) - 1) * 50 + i + 1
        username = escape_markdown(entry.get('username', 'Unknown'))
        value = int(float(entry.get('value', 0)))
        message_parts.append(f"`{rank}`\. *{username}* \- {escape_markdown(f'{value:,}')}")
    await update.message.reply_text('\n'.join(message_parts), parse_mode='MarkdownV2')

async def build_ah_page(search_id: str, search_term: str, sorted_items: list, page_index: int):
    start_index = page_index * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    page_items = sorted_items[start_index:end_index]
    message_parts = [f"Found *{len(sorted_items)}* match\(es\) for `{escape_markdown(search_term)}`\. Page {page_index + 1}:"]
    for item in page_items:
        item_name = escape_markdown(format_item_id(item.get('item', {}).get('id', 'Unknown')))
        seller = escape_markdown(item.get('seller', {}).get('name', 'Unknown'))
        price = f"{int(item.get('price', 0)):,}"
        message_parts.append(f"`{item_name}` from *{seller}* for \`${escape_markdown(price)}\`\.")
    message_text = '\n'.join(message_parts)
    buttons = []
    if page_index > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"ah:{search_id}:{page_index - 1}"))
    if end_index < len(sorted_items):
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"ah:{search_id}:{page_index + 1}"))
    return message_text, InlineKeyboardMarkup([buttons])

async def ah_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/ah {item name}`", parse_mode='MarkdownV2')
        return
    search_term = " ".join(context.args).lower()
    await update.message.reply_text(f"🔎 Searching all auctions for `{escape_markdown(search_term)}`\. This may take a moment\.\.\.", parse_mode='MarkdownV2')
    matching_items = []
    page = 1
    while True:
        data = make_api_request(f"/auction/list/{page}")
        auctions = data.get('result') if data else None
        if not auctions:
            break
        for item in auctions:
            item_name = format_item_id(item.get('item', {}).get('id', '')).lower()
            if search_term in item_name:
                matching_items.append(item)
        page += 1
        if page > 100:
            break
    if not matching_items:
        await update.message.reply_text(f"Could not find any items matching `{escape_markdown(search_term)}`\.", parse_mode='MarkdownV2')
        return
    sorted_items = sorted(matching_items, key=lambda x: x.get('price', float('inf')))
    search_id = str(uuid.uuid4())
    context.chat_data[search_id] = {'term': search_term, 'results': sorted_items}
    message_text, keyboard = await build_ah_page(search_id, search_term, sorted_items, 0)
    await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='MarkdownV2')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        command, search_id, page_index_str = query.data.split(':')
    except ValueError:
        return
    page_index = int(page_index_str)
    if command == 'ah':
        cached_data = context.chat_data.get(search_id)
        if not cached_data:
            await query.edit_message_text(text="This search has expired or is invalid\. Please run the command again\.", parse_mode='MarkdownV2')
            return
        search_term = cached_data['term']
        sorted_items = cached_data['results']
        message_text, keyboard = await build_ah_page(search_id, search_term, sorted_items, page_index)
        try:
            await query.edit_message_text(text=message_text, reply_markup=keyboard, parse_mode='MarkdownV2')
        except:
            pass

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/price {item name}`", parse_mode='MarkdownV2')
        return
    search_term = " ".join(context.args).lower()
    await update.message.reply_text(f"🔎 Searching all auctions for `{escape_markdown(search_term)}`\. This will be very slow\.\.\.", parse_mode='MarkdownV2')
    matching_items = []
    page = 1
    while True:
        data = make_api_request(f"/auction/list/{page}")
        auctions = data.get('result') if data else None
        if not auctions:
            break
        for item in auctions:
            item_name = format_item_id(item.get('item', {}).get('id', '')).lower()
            if search_term in item_name:
                matching_items.append(item)
        page += 1
    if not matching_items:
        await update.message.reply_text(f"Could not find any items matching `{escape_markdown(search_term)}`\.", parse_mode='MarkdownV2')
        return
    lowest_auction = min(matching_items, key=lambda x: x.get('price', float('inf')))
    item_name = escape_markdown(format_item_id(lowest_auction.get('item', {}).get('id', 'Unknown')))
    seller = escape_markdown(lowest_auction.get('seller', {}).get('name', 'Unknown'))
    price = f"{int(lowest_auction.get('price', 0)):,}"
    message = (
        f"💎 *Lowest Price Found*\n\n"
        f"Item: `{item_name}`\n"
        f"Seller: *{seller}*\n"
        f"Price: \`${escape_markdown(price)}\`"
    )
    await update.message.reply_text(message, parse_mode='MarkdownV2')

# --- MAIN BOT SETUP ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("isonline", isonline_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("auctions", auctions_command))
    application.add_handler(CommandHandler("sales", sales_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("ah", ah_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    logger.info("Bot started! Press Ctrl-C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()