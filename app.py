#!/usr/bin/env python3
"""
QWYTHOS Telegram Bot — Connected to Groq Free Tier API
معالجة ملفات: PDF (عربي)، صور (OCR عربي)، كود، نصوص
مجاناً بدون بطاقة ائتمان • يدعم العربية والإنجليزية
"""

import os
import logging
import httpx
import tempfile
import asyncio
import re
from pathlib import Path
from telegram import Update, ForceReply
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not GROQ_API_KEY:
    raise ValueError("❌ Set GROQ_API_KEY in environment")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ Set TELEGRAM_BOT_TOKEN in environment")

SYSTEM_PROMPT = """أنت QWYTHOS — مساعد تقني شخصي للمهندس أحمد، يعمل كبوت تلغرام.

## سياق تشغيلك (مهم جداً)
- أنت تعمل على **جهاز أحمد الماك** (macOS) — لست تطبيقاً على الهاتف.
- تتصل بـ Telegram Bot API عبر الإنترنت من ذلك الماك.
- عندما يسأل أحمد عن البوت أو الاتصال، فالمقصود **هذا البوت على ماكه** — وليس تطبيق أندرويد أو آيفون.
- إذا لم تكن متأكداً من سياق سؤال تقني، اسأل سؤال توضيحي واحد بدل تخمين البيئة.

## أسلوبك
- تجيب بالعربية والإنجليزية حسب لغة السؤال.
- متخصص في: البرمجة، البنية التحتية، الأمن السيبراني، الذكاء الاصطناعي، التحليلات.
- قدّم أجوبة دقيقة وعملية مع أمثلة. استخدم Markdown للتنسيق.
- لا تُكرر التحية في كل رسالة — افتتح مباشرة بالإجابة.
- لا تخترع تفاصيل عن بيئة أحمد؛ إن لم تعرفها فقل ذلك صراحة."""

# امتدادات الملفات المدعومة
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.m', '.pl', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.sql', '.html', '.css', '.scss', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.md', '.txt', '.rst', '.tex', '.dockerfile', '.gitignore', '.env'}
TEXT_EXTENSIONS = {'.txt', '.md', '.log', '.csv', '.tsv', '.rtf'}
PDF_EXTENSIONS = {'.pdf'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp', '.heic'}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
TELEGRAM_MSG_LIMIT = 4000  # Telegram hard limit is 4096; keep margin


async def send_long_message(update: Update, text: str, parse_mode: str | None = "Markdown"):
    """إرسال نص طويل عبر عدة رسائل — تلغرام يرفض أكثر من 4096 حرف.

    يقسّم النص على حدود الأسطر أو المسافات، ويتراجع إلى نص عادي إذا فشل Markdown.
    """
    if not text:
        text = "(لا يوجد رد)"

    # Split into chunks respecting line boundaries when possible
    chunks = []
    remaining = text
    while len(remaining) > TELEGRAM_MSG_LIMIT:
        split_at = remaining.rfind("\n", 0, TELEGRAM_MSG_LIMIT)
        if split_at < TELEGRAM_MSG_LIMIT // 2:
            split_at = remaining.rfind(" ", 0, TELEGRAM_MSG_LIMIT)
        if split_at <= 0:
            split_at = TELEGRAM_MSG_LIMIT
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    chunks.append(remaining)

    total = len(chunks)
    for i, chunk in enumerate(chunks):
        prefix = f"({i+1}/{total})\n" if total > 1 else ""
        body = prefix + chunk
        try:
            await update.message.reply_text(body, parse_mode=parse_mode)
        except Exception:
            # Markdown parse failure or other error → resend as plain text
            await update.message.reply_text(body)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تقرير حالة البوت — مفيد للتشخيص من الهاتف"""
    import subprocess, platform, datetime

    def run(cmd):
        try:
            return subprocess.run(cmd, shell=True, capture_output=True,
                                  text=True, timeout=5).stdout.strip()
        except Exception:
            return "غير متاح"

    # هل الماك مستيقظ/على الشاحن؟
    batt = run("pmset -g batt | head -2")
    sleep_state = run("pmset -g | grep -E '^ sleep'")
    caffeinate = run("pgrep -fl caffeinate | head -1")

    # آخر تحديث وصل من تلغرام (نبض الاتصال)
    uptime = run("ps -p $(pgrep -f 'app.py' | head -1) -o etime= 2>/dev/null")

    text = (
        "🩺 **حالة QWYTHOS Bot**\n\n"
        f"🖥 **الجهاز:** {platform.node()} (macOS)\n"
        f"🔋 **الطاقة:**\n`{batt}`\n"
        f"😴 **حالة النوم:**\n`{sleep_state or 'غير معروفة'}`\n"
        f"☕ **منع النوم:** {'نشط ✅' if caffeinate else 'غير نشط ⚠️'}\n"
        f"⏱ **مدة التشغيل:** {uptime or 'غير معروفة'}\n\n"
        "**ملاحظة:** إذا كان الماك نائماً، لن يستقبل البوت رسائلك "
        "حتى يستيقظ — هذا طبيعي لأن البوت يعمل على الماك نفسه."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب"""
    await update.message.reply_text(
        "🚀 **QWYTHOS Assistant** جاهز!\n\n"
        "🤖 مساعد تقني ذكي على Groq Free Tier\n"
        "📌 النموذج: `openai/gpt-oss-120b` (120B params)\n"
        "🔄 Fallback: `qwen/qwen3.8-27b` (عند أي مشكل)\n\n"
        "**قدرات الملفات:**\n"
        "📄 **PDF عربي** — استخراج نص + OCR (pdf2text-arabic)\n"
        "🖼 **صور** — OCR عربي (Tesseract)\n"
        "💻 **كود** — قراءة وتحليل (Python, JS, Go, Rust, إلخ)\n"
        "📝 **نصوص** — قراءة مباشرة\n\n"
        "اسألني أي شيء تقني — أو أرسل ملفاً!",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية — مع كشف روابط TikTok تلقائياً"""
    user_msg = update.message.text

    # كشف روابط TikTok → معالجة خاصة بملخص عربي
    tiktok_urls = extract_tiktok_urls(user_msg)
    if tiktok_urls:
        await handle_tiktok_links(update, context, tiktok_urls)
        return

    await process_user_query(update, user_msg)


async def process_user_query(update: Update, query: str):
    """معالجة استعلام المستخدم وإرسال الرد"""
    await update.message.reply_chat_action(ChatAction.TYPING)

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": query}
                    ],
                    "max_tokens": 65536,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            )

        if resp.status_code == 200:
            reply = resp.json()["choices"][0]["message"]["content"]
            await send_long_message(update, reply)
            save_to_memory(query, reply)

        elif resp.status_code == 429:
            logger.warning("Rate limited on gpt-oss-120b, falling back to qwen3.8-27b")
            reply = await call_groq_fallback(query)
            await send_long_message(
                update,
                "⚠️ وصلت الحد للطلبات (429).\n"
                "_استخدام النموذج الاحتياطي: qwen3.8-27b_\n\n" + reply
            )
        else:
            await update.message.reply_text(
                f"❌ خطأ: `{resp.status_code}`\n```{resp.text[:300]}```",
                parse_mode="Markdown"
            )

    except httpx.TimeoutException:
        await update.message.reply_text("⏰ انتهت المهلة. جرّب تلخيص السؤال.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ خطأ غير متوقع: {str(e)[:300]}")


async def call_groq_fallback(user_msg: str) -> str:
    """استدعاء النموذج الاحتياطي — qwen3.8-27b"""
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "qwen/qwen3.8-27b",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ],
                "max_tokens": 16384,
                "temperature": 0.7,
            }
        )
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    return "عذراً، فشل الاتصال بكلا النموذجين. جرّب لاحقاً."


# ==================== معالجات الملفات ====================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملفات المرسلة (PDF، كود، نصوص)"""
    document = update.message.document
    file_name = document.file_name or "unknown"
    file_size = document.file_size or 0

    # التحقق من الحجم
    if file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"❌ الملف كبير جداً ({file_size/1024/1024:.1f} MB).\n"
            f"الحد الأقصى: {MAX_FILE_SIZE/1024/1024} MB"
        )
        return

    ext = Path(file_name).suffix.lower()

    await update.message.reply_text(
        f"📥 جاري معالجة: `{file_name}` ({file_size/1024:.1f} KB)...",
        parse_mode="Markdown"
    )

    # تحميل الملف
    file = await document.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

    try:
        # معالجة حسب النوع
        if ext in PDF_EXTENSIONS:
            content = await process_pdf(tmp_path)
        elif ext in CODE_EXTENSIONS:
            content = await process_code_file(tmp_path, ext)
        elif ext in TEXT_EXTENSIONS:
            content = await process_text_file(tmp_path)
        else:
            content = f"❌ نوع ملف غير مدعوم: `{ext}`\n\n**المدعوم:**\n" \
                      f"PDF: {', '.join(PDF_EXTENSIONS)}\n" \
                      f"كود: {', '.join(sorted(CODE_EXTENSIONS))[:100]}...\n" \
                      f"نصوص: {', '.join(TEXT_EXTENSIONS)}"

        # إرسال المحتوى للنموذج مع سياق الملف
        if content.startswith("❌"):
            await send_long_message(update, content)
        else:
            await process_user_query(
                update,
                f"📎 **ملف مرفق: `{file_name}`**\n\n---\n{content[:15000]}"
            )

    except Exception as e:
        logger.error(f"File processing error: {e}")
        await update.message.reply_text(f"❌ خطأ في معالجة الملف: {str(e)[:300]}")
    finally:
        # تنظيف الملف المؤقت
        try:
            os.unlink(tmp_path)
        except:
            pass


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الصور المرسلة (OCR عربي)"""
    # الحصول على أكبر نسخة من الصورة
    photo = update.message.photo[-1]
    file_size = photo.file_size or 0

    if file_size > MAX_FILE_SIZE:
        await update.message.reply_text("❌ الصورة كبيرة جداً. الحد الأقصى: 20 MB")
        return

    await update.message.reply_text("🖼 جاري استخراج النص من الصورة (OCR عربي)...")

    file = await photo.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

    try:
        text = await ocr_image_arabic(tmp_path)
        if text.strip():
            await send_long_message(
                update,
                f"🖼 **نص مستخرج من الصورة (OCR):**\n\n---\n{text[:10000]}"
            )
        else:
            await update.message.reply_text("⚠️ لم يتم استخراج نص من الصورة. تأكد من وضوح النص.")
    except Exception as e:
        logger.error(f"OCR error: {e}")
        await update.message.reply_text(f"❌ خطأ في OCR: {str(e)[:300]}")
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


# ==================== دوال المعالجة ====================

async def process_pdf(pdf_path: str) -> str:
    """استخراج نص من PDF عربي باستخدام pdf2text-arabic"""
    try:
        from pdf2text_arabic import extract_pdf
        # استخراج مع دعم OCR تلقائي للصفحات الممسوحة
        text = extract_pdf(
            pdf_path,
            ocr_strategy="auto",  # يستخدم OCR للصفحات الممسوحة فقط
            detect_footer=True,
            crop_top=8.0,
            crop_bottom=4.5,
            crop_unit="pct",
            auto_crop_top=True,
            auto_crop_bottom=True,
        )
        if not text.strip():
            return "⚠️ PDF فارغ أو لا يحتوي على نص قابل للاستخراج."
        return text
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return f"❌ خطأ في استخراج PDF: {str(e)}"


async def process_code_file(file_path: str, ext: str) -> str:
    """قراءة وتحليل ملف كود"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.count('\n') + 1
        chars = len(content)
        return f"```{ext[1:]}\n{content}\n```\n\n📊 **إحصائيات:** {lines} سطر، {chars} حرف"
    except UnicodeDecodeError:
        return f"❌ لا يمكن قراءة الملف كنص (ترميز غير UTF-8): `{ext}`"
    except Exception as e:
        return f"❌ خطأ في قراءة الكود: {str(e)}"


async def process_text_file(file_path: str) -> str:
    """قراءة ملف نصي"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except UnicodeDecodeError:
        return "❌ لا يمكن قراءة الملف (ترميز غير UTF-8)"
    except Exception as e:
        return f"❌ خطأ: {str(e)}"


async def ocr_image_arabic(image_path: str) -> str:
    """OCR عربي للصور باستخدام Tesseract"""
    try:
        import pytesseract
        from PIL import Image

        # فتح الصورة
        img = Image.open(image_path)

        # تحسين الصورة للعربية
        # تحويل إلى تدرج رمادي
        if img.mode != 'L':
            img = img.convert('L')

        # زيادة التباين
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        # OCR مع اللغة العربية
        text = pytesseract.image_to_string(img, lang='ara', config='--psm 6')

        return text.strip()
    except Exception as e:
        logger.error(f"OCR error: {e}")
        raise


# ==================== معالج روابط TikTok ====================

TIKTOK_URL_PATTERN = re.compile(
    r'(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/[\w\-\./?=&%]+',
    re.IGNORECASE
)


def extract_tiktok_urls(text: str) -> list:
    """استخراج روابط TikTok من النص"""
    urls = TIKTOK_URL_PATTERN.findall(text)
    # تحويل tuples إلى strings
    return [''.join(url) if isinstance(url, tuple) else url for url in urls]


async def process_tiktok_url(url: str) -> str:
    """استخراج بيانات TikTok وإنشاء ملخص عربي"""
    try:
        import yt_dlp

        ydl_opts = {
            'extract_flat': False,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'getcomments': False,  # لا يعمل مع TikTok حالياً
        }

        # تشغيل yt-dlp في thread منفصل لتجنب الحظر
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
        )

        # استخراج المعلومات المهمة
        title = info.get('title', 'بدون عنوان')
        description = info.get('description', 'لا يوجد وصف')
        uploader = info.get('uploader', 'مجهول')
        uploader_url = info.get('uploader_url', '')
        channel = info.get('channel', uploader)
        view_count = info.get('view_count', 0)
        like_count = info.get('like_count', 0)
        comment_count = info.get('comment_count', 0)
        repost_count = info.get('repost_count', 0)
        save_count = info.get('save_count', 0)
        duration = info.get('duration', 0)
        upload_date = info.get('upload_date', '')
        hashtags = re.findall(r'#\w+', description)
        track = info.get('track', 'صوت أصلي')
        webpage_url = info.get('webpage_url', url)

        # تنسيق التاريخ
        date_str = ''
        if upload_date and len(upload_date) == 8:
            date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

        # تنسيق المدة
        duration_str = ''
        if duration:
            mins, secs = divmod(duration, 60)
            duration_str = f"{mins}:{secs:02d}"

        # بناء ملخص البيانات
        metadata = f"""📱 **معلومات فيديو TikTok:**

**العنوان:** {title}
**الوصف:** {description}
**الصانع:** {channel} ({uploader_url})
**الصوت:** {track}
**التاريخ:** {date_str}
**المدة:** {duration_str}

**📊 الإحصائيات:**
• المشاهدات: {view_count:,}
• الإعجابات: {like_count:,}
• التعليقات: {comment_count:,}
• إعادة النشر: {repost_count:,}
• الحفظ: {save_count:,}

**🏷️ الهاشتاجات:** {', '.join(hashtags) if hashtags else 'لا يوجد'}

**الرابط:** {webpage_url}"""

        return metadata

    except Exception as e:
        logger.error(f"TikTok extraction error: {e}")
        return f"❌ خطأ في استخراج بيانات TikTok: {str(e)}"


async def handle_tiktok_links(update: Update, context: ContextTypes.DEFAULT_TYPE, urls: list):
    """معالجة روابط TikTok المرسلة"""
    for url in urls:
        await update.message.reply_text(
            f"🔍 جاري تحليل رابط TikTok...\n{url}",
            parse_mode="Markdown"
        )

        # استخراج البيانات
        metadata = await process_tiktok_url(url)

        if metadata.startswith("❌"):
            await send_long_message(update, metadata)
        else:
            # إرسال للـ Groq لملخص عربي
            summary_prompt = f"""حلل بيانات فيديو TikTok التالية وقدم ملخصاً عربياً شاملاً ومفيداً:

{metadata}

المطلوب:
1. ملخص مختصر لمحتوى الفيديو
2. طبيعة المحتوى (ترفيهي، تعليمي، تسويقي، إلخ)
3. مستوى التفاعل والجودة
4. هل يستحق المشاهدة ولماذا
5. أي ملاحظات إضافية

اكتب بالعربية بأسلوب احترافي ومباشر."""

            await process_user_query(update, summary_prompt)


def save_to_memory(user_msg: str, reply: str):
    """حفظ المحادثة في SQLite"""
    import sqlite3, datetime
    db_path = "/Users/ahmedabushama/qwythos-telegram-bot/memory.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_msg TEXT,
        bot_reply TEXT,
        ts TEXT
    )""")
    c.execute("INSERT INTO chats (user_msg, bot_reply, ts) VALUES (?, ?, ?)",
              (user_msg, reply, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()


def main():
    print("🚀 تشغيل QWYTHOS Telegram Bot...")
    print(f"   النموذج الأساسي: openai/gpt-oss-120b")
    print(f"   النموذج الاحتياطي: qwen/qwen3.8-27b")
    print(f"   الذاكرة المحلية: SQLite (memory.db)")
    print(f"   معالجة ملفات: PDF عربي، صور OCR، كود، نصوص")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ الروبوت نشط — افتح تيليجرام وأرسل /start إلى @qwythos_assistant_bot")
    print("📎 أرسل: PDF، صور، ملفات كود (.py, .js, إلخ)، ملفات نصية")
    app.run_polling()


if __name__ == "__main__":
    main()