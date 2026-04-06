import os
import json
from datetime import date
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

# ── 설정 ──────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "여기에_텔레그램_토큰")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "여기에_Gemini_키")
DATA_FILE = "tasks.json"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ── 데이터 저장/불러오기 ──────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_tasks(user_id: str):
    data = load_data()
    today = str(date.today())
    if user_id not in data:
        data[user_id] = {}
    if today not in data[user_id]:
        data[user_id][today] = []
        save_data(data)
    return data[user_id][today], data, today

# ── Gemini AI 호출 ────────────────────────────────────
def ask_gemini(system_prompt: str, user_message: str) -> str:
    response = model.generate_content(f"{system_prompt}\n\n{user_message}")
    return response.text

# ── 키보드 메뉴 ───────────────────────────────────────
def main_keyboard():
    buttons = [
        [KeyboardButton("📋 오늘 할 일 보기"), KeyboardButton("➕ 할 일 추가")],
        [KeyboardButton("✅ 완료 체크"), KeyboardButton("🎯 우선순위 정해줘")],
        [KeyboardButton("🌙 하루 회고"), KeyboardButton("🗑️ 할 일 삭제")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ── 할 일 목록 포맷 ───────────────────────────────────
def format_tasks(tasks):
    if not tasks:
        return "📭 오늘 등록된 할 일이 없어요!"
    lines = []
    for i, t in enumerate(tasks, 1):
        check = "✅" if t.get("done") else "⬜"
        priority = t.get("priority", "")
        priority_emoji = {"높음": "🔴", "중간": "🟡", "낮음": "🟢"}.get(priority, "")
        lines.append(f"{check} {i}. {priority_emoji} {t['title']}")
    return "\n".join(lines)

# ── /start 명령어 ─────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"안녕하세요, {name}님! 👋\n\n"
        "저는 하루 일정을 도와주는 AI 비서예요.\n\n"
        "📋 할 일 추가/관리\n"
        "🎯 우선순위 자동 추천\n"
        "🌙 저녁 하루 회고\n\n"
        "아래 버튼으로 시작해보세요!",
        reply_markup=main_keyboard()
    )

# ── 메시지 처리 ───────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    tasks, data, today = get_user_tasks(user_id)

    state = context.user_data.get("state")

    # ── 할 일 추가 모드 ──
    if state == "adding":
        new_task = {"title": text, "done": False, "priority": ""}
        tasks.append(new_task)
        data[user_id][today] = tasks
        save_data(data)
        context.user_data["state"] = None
        await update.message.reply_text(
            f"✅ '{text}' 추가됐어요!\n\n{format_tasks(tasks)}",
            reply_markup=main_keyboard()
        )
        return

    # ── 완료 체크 모드 ──
    if state == "checking":
        try:
            idx = int(text) - 1
            if 0 <= idx < len(tasks):
                tasks[idx]["done"] = not tasks[idx]["done"]
                status = "완료" if tasks[idx]["done"] else "미완료"
                data[user_id][today] = tasks
                save_data(data)
                context.user_data["state"] = None
                await update.message.reply_text(
                    f"'{tasks[idx]['title']}' → {status} 처리했어요!\n\n{format_tasks(tasks)}",
                    reply_markup=main_keyboard()
                )
            else:
                await update.message.reply_text("번호를 다시 확인해주세요!")
        except ValueError:
            await update.message.reply_text("숫자로 입력해주세요! (예: 1)")
        return

    # ── 삭제 모드 ──
    if state == "deleting":
        try:
            idx = int(text) - 1
            if 0 <= idx < len(tasks):
                removed = tasks.pop(idx)
                data[user_id][today] = tasks
                save_data(data)
                context.user_data["state"] = None
                await update.message.reply_text(
                    f"🗑️ '{removed['title']}' 삭제했어요!\n\n{format_tasks(tasks)}",
                    reply_markup=main_keyboard()
                )
            else:
                await update.message.reply_text("번호를 다시 확인해주세요!")
        except ValueError:
            await update.message.reply_text("숫자로 입력해주세요! (예: 2)")
        return

    # ── 버튼 처리 ──
    if text == "📋 오늘 할 일 보기":
        msg = f"📋 오늘의 할 일 목록\n{'─'*20}\n{format_tasks(tasks)}"
        done = sum(1 for t in tasks if t.get("done"))
        if tasks:
            msg += f"\n\n진행률: {done}/{len(tasks)} 완료 🎉"
        await update.message.reply_text(msg, reply_markup=main_keyboard())

    elif text == "➕ 할 일 추가":
        context.user_data["state"] = "adding"
        await update.message.reply_text(
            "추가할 할 일을 입력해주세요! ✏️\n(예: 보고서 작성, 운동 30분)",
            reply_markup=main_keyboard()
        )

    elif text == "✅ 완료 체크":
        if not tasks:
            await update.message.reply_text("등록된 할 일이 없어요!", reply_markup=main_keyboard())
        else:
            context.user_data["state"] = "checking"
            await update.message.reply_text(
                f"완료할 항목 번호를 입력하세요!\n\n{format_tasks(tasks)}",
                reply_markup=main_keyboard()
            )

    elif text == "🗑️ 할 일 삭제":
        if not tasks:
            await update.message.reply_text("삭제할 할 일이 없어요!", reply_markup=main_keyboard())
        else:
            context.user_data["state"] = "deleting"
            await update.message.reply_text(
                f"삭제할 항목 번호를 입력하세요!\n\n{format_tasks(tasks)}",
                reply_markup=main_keyboard()
            )

    elif text == "🎯 우선순위 정해줘":
        if not tasks:
            await update.message.reply_text("할 일을 먼저 추가해주세요!", reply_markup=main_keyboard())
            return
        await update.message.reply_text("⏳ 우선순위 분석 중...")
        task_list = "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(tasks)])
        system = (
            "당신은 생산성 전문가입니다. 사용자의 할 일 목록을 분석해서 "
            "우선순위(높음/중간/낮음)를 정해주고, 각각 짧게 이유를 설명해주세요. "
            "친근하고 간결하게 한국어로 답변하세요."
        )
        result = ask_gemini(system, f"오늘 할 일 목록:\n{task_list}\n\n우선순위를 정해주세요.")

        for i, task in enumerate(tasks):
            for line in result.split('\n'):
                if task['title'] in line or str(i+1) + '.' in line:
                    if '높음' in line:
                        tasks[i]['priority'] = '높음'
                    elif '중간' in line:
                        tasks[i]['priority'] = '중간'
                    elif '낮음' in line:
                        tasks[i]['priority'] = '낮음'
        data[user_id][today] = tasks
        save_data(data)

        await update.message.reply_text(
            f"🎯 우선순위 분석 결과\n{'─'*20}\n{result}\n\n{format_tasks(tasks)}",
            reply_markup=main_keyboard()
        )

    elif text == "🌙 하루 회고":
        await update.message.reply_text("⏳ 하루 회고 작성 중...")
        done_tasks = [t['title'] for t in tasks if t.get('done')]
        undone_tasks = [t['title'] for t in tasks if not t.get('done')]
        summary = f"완료: {done_tasks}\n미완료: {undone_tasks}"
        system = (
            "당신은 따뜻한 AI 코치입니다. 사용자의 오늘 하루를 정리해주고, "
            "잘한 점을 칭찬하고, 내일을 위한 짧은 조언을 해주세요. "
            "친근하고 따뜻하게 한국어로 200자 이내로 답변하세요."
        )
        result = ask_gemini(system, f"오늘의 결과:\n{summary}")
        await update.message.reply_text(
            f"🌙 오늘 하루 회고\n{'─'*20}\n{result}",
            reply_markup=main_keyboard()
        )

    else:
        system = (
            "당신은 친근한 하루 일정 도우미입니다. "
            "할 일 관리, 생산성, 동기부여에 대해 도움을 드립니다. "
            "간결하고 친근하게 한국어로 답변하세요."
        )
        result = ask_gemini(system, text)
        await update.message.reply_text(result, reply_markup=main_keyboard())

# ── 실행 ──────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 봇 실행 중...")
    app.run_polling()