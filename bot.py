import os
import io
import asyncio
import logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from PyPDF2 import PdfReader, PdfWriter
import pytesseract
import aiofiles
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment
TOKEN = os.getenv('BOT_TOKEN')

# Constants
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_IMAGE_FORMATS = ['jpg', 'jpeg', 'png', 'webp', 'bmp']
ALLOWED_DOC_FORMATS = ['pdf']

# Store user session data
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when /start is issued."""
    user = update.effective_user
    welcome_text = f"""
👋 G'day mate! Welcome to FTDify!

I'm your all-in-one file management bot. I can help you convert, compress, and manage your files with ease.

📌 Available Commands:
/convert - Convert images to different formats
/compress - Compress PDF files
/watermark - Add text watermark to images
/metadata - Get file information
/ocr - Extract text from images
/help - Show all available commands
/about - Learn more about this bot

Ready to start? Just send me a file or use a command above!
    """
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when /help is issued."""
    help_text = """
❓ **How to use FTDify Bot**

📁 **File Conversion**
• Send any image and use /convert to change format
• Supported: JPG, PNG, WEBP, BMP

📦 **PDF Compression**
• Send PDF and use /compress to reduce size
• Keeps quality while making file smaller

🖼️ **Watermark**
• Send image and use /watermark
• Add custom text watermark to your images

📝 **OCR (Text Extraction)**
• Send image with text and use /ocr
• Extract text from images, screenshots, or documents

ℹ️ **Metadata**
• Send any file and use /metadata
• View file details and information

⚠️ **Limitations**
• Max file size: 50MB
• Files are processed immediately and deleted
• No data storage - your privacy is respected

Need help? Just ask! 🎯
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when /about is issued."""
    about_text = """
ℹ️ **About FTDify Bot**

📁 **Version:** 1.0.0
👨‍💻 **Developer:** FTDify Team
⚡ **Status:** Active

**Features:**
✅ File conversion
✅ PDF compression
✅ Image watermarking
✅ OCR text extraction
✅ File metadata

**Privacy Policy:**
• No files are stored permanently
• All processing is done in memory
• Files are deleted immediately after processing

**Compliance:**
✅ Telegram Terms of Service
✅ Telegram Ads Policy
✅ Data Privacy Regulations

Made with ❤️ for the Telegram community
    """
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads."""
    document = update.message.document
    file_size = document.file_size
    
    if file_size > MAX_FILE_SIZE:
        await update.message.reply_text("⚠️ File is too large! Maximum size is 50MB.")
        return
    
    # Store file info in context for later use
    file_id = document.file_id
    file_name = document.file_name
    mime_type = document.mime_type
    
    context.user_data['last_file'] = {
        'file_id': file_id,
        'file_name': file_name,
        'mime_type': mime_type
    }
    
    await update.message.reply_text(
        f"✅ File received: {file_name}\n"
        f"📊 Size: {file_size / 1024:.2f} KB\n"
        f"📌 Use a command to process this file!\n"
        f"Available: /convert, /compress, /watermark, /ocr, /metadata"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads."""
    photo = update.message.photo[-1]  # Get the largest photo
    file_size = photo.file_size
    
    if file_size > MAX_FILE_SIZE:
        await update.message.reply_text("⚠️ File is too large! Maximum size is 50MB.")
        return
    
    context.user_data['last_file'] = {
        'file_id': photo.file_id,
        'file_name': 'image.jpg',
        'mime_type': 'image/jpeg'
    }
    
    await update.message.reply_text(
        "✅ Image received!\n"
        "📌 Use a command to process:\n"
        "/convert - Change format\n"
        "/watermark - Add watermark\n"
        "/ocr - Extract text"
    )

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert image to different format."""
    if 'last_file' not in context.user_data:
        await update.message.reply_text("⚠️ Please send a file first!")
        return
    
    file_info = context.user_data['last_file']
    if not file_info['mime_type'].startswith('image/'):
        await update.message.reply_text("⚠️ This command only works with images!")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("JPG", callback_data="convert_jpg"),
            InlineKeyboardButton("PNG", callback_data="convert_png"),
        ],
        [
            InlineKeyboardButton("WEBP", callback_data="convert_webp"),
            InlineKeyboardButton("BMP", callback_data="convert_bmp"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔄 Select the format you want to convert to:",
        reply_markup=reply_markup
    )

async def compress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compress PDF file."""
    if 'last_file' not in context.user_data:
        await update.message.reply_text("⚠️ Please send a PDF file first!")
        return
    
    file_info = context.user_data['last_file']
    if not file_info['file_name'].lower().endswith('.pdf'):
        await update.message.reply_text("⚠️ This command only works with PDF files!")
        return
    
    await update.message.reply_text("📦 Compressing PDF... Please wait.")
    
    try:
        # Get file
        file = await context.bot.get_file(file_info['file_id'])
        file_bytes = await file.download_as_bytearray()
        
        # Read PDF
        pdf_reader = PdfReader(io.BytesIO(file_bytes))
        pdf_writer = PdfWriter()
        
        # Compress by removing unused objects and compressing streams
        for page in pdf_reader.pages:
            pdf_writer.add_page(page)
        
        # Compress the PDF
        pdf_writer.compress_content_streams()
        
        # Save compressed PDF
        output = io.BytesIO()
        pdf_writer.write(output)
        output.seek(0)
        
        compressed_size = len(output.getvalue())
        original_size = len(file_bytes)
        reduction = ((original_size - compressed_size) / original_size) * 100
        
        # Send compressed file
        await update.message.reply_document(
            document=output,
            filename=f"compressed_{file_info['file_name']}",
            caption=f"✅ Compression complete!\n"
                   f"📊 Original: {original_size / 1024:.2f} KB\n"
                   f"📦 Compressed: {compressed_size / 1024:.2f} KB\n"
                   f"💾 Reduction: {reduction:.1f}%"
        )
        
    except Exception as e:
        logger.error(f"Compression error: {e}")
        await update.message.reply_text("❌ Error compressing PDF. Please try again.")

async def watermark_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add watermark to image."""
    if 'last_file' not in context.user_data:
        await update.message.reply_text("⚠️ Please send an image first!")
        return
    
    # Ask for watermark text
    context.user_data['awaiting_watermark'] = True
    await update.message.reply_text(
        "✏️ Please send the text you want to use as a watermark.\n"
        "Reply with the text you'd like to add to your image."
    )

async def handle_watermark_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle watermark text input."""
    if not context.user_data.get('awaiting_watermark'):
        return
    
    watermark_text = update.message.text
    context.user_data['awaiting_watermark'] = False
    
    file_info = context.user_data['last_file']
    await update.message.reply_text(f"🖼️ Adding watermark: '{watermark_text}'... Please wait.")
    
    try:
        # Get file
        file = await context.bot.get_file(file_info['file_id'])
        file_bytes = await file.download_as_bytearray()
        
        # Open image
        image = Image.open(io.BytesIO(file_bytes))
        
        # Create a copy for watermark
        watermarked = image.copy()
        draw = ImageDraw.Draw(watermarked)
        
        # Try to load a font, fallback to default
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except:
            font = ImageFont.load_default()
        
        # Calculate text position (bottom right)
        text_width = draw.textlength(watermark_text, font=font)
        text_height = 36
        x = watermarked.width - text_width - 20
        y = watermarked.height - text_height - 20
        
        # Add shadow for better visibility
        draw.text((x+2, y+2), watermark_text, fill='black', font=font)
        draw.text((x, y), watermark_text, fill='white', font=font)
        
        # Save to bytes
        output = io.BytesIO()
        watermarked.save(output, format=image.format if image.format else 'PNG')
        output.seek(0)
        
        await update.message.reply_document(
            document=output,
            filename=f"watermarked_{file_info['file_name']}",
            caption=f"✅ Watermark added successfully!"
        )
        
    except Exception as e:
        logger.error(f"Watermark error: {e}")
        await update.message.reply_text("❌ Error adding watermark. Please try again.")

async def metadata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get file metadata."""
    if 'last_file' not in context.user_data:
        await update.message.reply_text("⚠️ Please send a file first!")
        return
    
    file_info = context.user_data['last_file']
    file = await context.bot.get_file(file_info['file_id'])
    
    metadata_text = f"""
📄 **File Metadata**

📌 **Name:** {file_info['file_name']}
📊 **Size:** {file.file_size / 1024:.2f} KB
📁 **Type:** {file_info['mime_type']}
🆔 **File ID:** {file_info['file_id'][:15]}...
📅 **Uploaded:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    await update.message.reply_text(metadata_text, parse_mode='Markdown')

async def ocr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extract text from image using OCR."""
    if 'last_file' not in context.user_data:
        await update.message.reply_text("⚠️ Please send an image first!")
        return
    
    file_info = context.user_data['last_file']
    if not file_info['mime_type'].startswith('image/'):
        await update.message.reply_text("⚠️ This command only works with images!")
        return
    
    await update.message.reply_text("📝 Extracting text from image... Please wait.")
    
    try:
        # Get file
        file = await context.bot.get_file(file_info['file_id'])
        file_bytes = await file.download_as_bytearray()
        
        # Open image and extract text
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
        
        if text.strip():
            response = f"📝 **Extracted Text:**\n\n{text[:1000]}"
            if len(text) > 1000:
                response += f"\n\n... and {len(text) - 1000} more characters"
            await update.message.reply_text(response, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ No text found in the image.")
            
    except Exception as e:
        logger.error(f"OCR error: {e}")
        await update.message.reply_text("❌ Error extracting text. Please try again.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks for conversion."""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('convert_'):
        return
    
    format_type = query.data.split('_')[1]
    
    if 'last_file' not in context.user_data:
        await query.edit_message_text("⚠️ Please send a file first!")
        return
    
    file_info = context.user_data['last_file']
    await query.edit_message_text(f"🔄 Converting to {format_type.upper()}... Please wait.")
    
    try:
        # Get file
        file = await context.bot.get_file(file_info['file_id'])
        file_bytes = await file.download_as_bytearray()
        
        # Open and convert image
        image = Image.open(io.BytesIO(file_bytes))
        
        # Convert format
        output = io.BytesIO()
        image.save(output, format=format_type.upper())
        output.seek(0)
        
        # Generate new filename
        base_name = os.path.splitext(file_info['file_name'])[0]
        new_name = f"{base_name}.{format_type}"
        
        await query.message.reply_document(
            document=output,
            filename=new_name,
            caption=f"✅ Successfully converted to {format_type.upper()}!"
        )
        await query.message.delete()
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await query.edit_message_text(f"❌ Error converting to {format_type.upper()}. Please try again.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and notify user."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ An error occurred. Please try again or contact support."
        )

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("compress", compress_command))
    application.add_handler(CommandHandler("watermark", watermark_command))
    application.add_handler(CommandHandler("metadata", metadata_command))
    application.add_handler(CommandHandler("ocr", ocr_command))
    
    # Add message handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_watermark_text))
    
    # Add callback handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Start the bot
    print("🚀 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
