

import os
import io
import time
import math
import sqlite3
import random
import traceback
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from urllib.parse import quote_plus, unquote_plus

import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# SymPy
from sympy import (
    symbols, Symbol, Eq, sympify, simplify, factor, expand,
    diff, integrate, solveset, S, latex, limit, series,
    sin, cos, tan, log, exp, sqrt, pi, E, I
)
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication, convert_xor
from sympy.core.sympify import SympifyError

# Matplotlib (for plots)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np



from PIL import Image
import pytesseract
import cv2
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# ---------------------------
# Конфигурация
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or "7955033715:AAHCitRiRD7nFTeX8YO-B1heGlneRAxuLto"
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан. Установите переменную окружения BOT_TOKEN или впишите токен в код.")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_PATH = "mathmaster_new.db"
IMG_DIR = "plots"
os.makedirs(IMG_DIR, exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------------------------
# Database helpers
# ---------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        grade INTEGER,
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0,
        created_at TEXT,
        last_active TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER,
        command TEXT,
        query TEXT,
        answer TEXT,
        timestamp TEXT,
        difficulty INTEGER DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS achievements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER,
        name TEXT,
        description TEXT,
        earned_at TEXT,
        icon TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS favorites(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER,
        title TEXT,
        content TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS quiz_cards(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        question TEXT,
        right_answer TEXT,
        wrong1 TEXT,
        wrong2 TEXT,
        wrong3 TEXT,
        explanation TEXT,
        difficulty INTEGER DEFAULT 1,
        box INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS quiz_stats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE,
        correct INTEGER DEFAULT 0,
        total INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        max_streak INTEGER DEFAULT 0,
        updated_at TEXT
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_history_user ON history(tg_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_quiz_stats_user ON quiz_stats(tg_id)")

    c.execute("SELECT COUNT(*) FROM quiz_cards")
    if c.fetchone()[0] == 0:
        seed_quiz_data = [
            ("линейные уравнения", "Реши: 2x + 5 = 13", "4", "5", "3", "8", "Переносим 5: 2x = 8, делим на 2: x = 4", 1),
            ("квадратные уравнения", "Реши: x^2 - 5x + 6 = 0", "2, 3", "1, 6", "0, 5", "-2, -3", "D = 25-24=1, x=(5±1)/2", 1),
            ("производная", "Найди производную: x^3", "3x^2", "x^2", "3x", "x^3", "Правило степени: (x^n)' = n·x^(n-1)", 1),
            ("интегралы", "Найди интеграл: ∫2x dx", "x^2 + C", "x^2", "2x^2 + C", "x + C", "∫x^n dx = x^(n+1)/(n+1) + C", 1),
            ("тригонометрия", "sin^2 x + cos^2 x = ?", "1", "0", "sin x", "cos x", "Основная тригонометрическая тождественность", 1)
        ]
        for topic, question, right, w1, w2, w3, expl, diffc in seed_quiz_data:
            c.execute(
                "INSERT INTO quiz_cards (topic, question, right_answer, wrong1, wrong2, wrong3, explanation, difficulty) VALUES (?,?,?,?,?,?,?,?)",
                (topic, question, right, w1, w2, w3, expl, diffc)
            )

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def ensure_user(message):
    user = message.from_user
    if not user:
        return
    conn = db()
    c = conn.cursor()
    c.execute("SELECT tg_id FROM users WHERE tg_id=?", (user.id,))
    row = c.fetchone()
    if not row:
        c.execute(
            """INSERT INTO users(tg_id, username, first_name, last_name, grade, created_at, last_active)
               VALUES(?,?,?,?,?,?,?)""",
            (
                user.id, user.username or "", user.first_name or "", user.last_name or "", None,
                datetime.now().isoformat(), datetime.now().isoformat()
            )
        )
        initial_achievements = [
            ("Первый шаг", "Зарегистрировался в боте", "🎯"),
            ("Любознательный", "Задал первый вопрос", "🔍"),
            ("Новичок", "Решил первую задачу", "⭐")
        ]
        for name, desc, icon in initial_achievements:
            c.execute(
                "INSERT INTO achievements(tg_id, name, description, earned_at, icon) VALUES(?,?,?,?,?)",
                (user.id, name, desc, datetime.now().isoformat(), icon)
            )
        c.execute("INSERT INTO quiz_stats (tg_id, correct, total, streak, max_streak, updated_at) VALUES (?,?,?,?,?,?)",
                  (user.id, 0, 0, 0, 0, datetime.now().isoformat()))
        conn.commit()
        print(f"✅ Создан новый пользователь: {user.id}")
    else:
        c.execute("UPDATE users SET last_active = ? WHERE tg_id = ?", (datetime.now().isoformat(), user.id))
        conn.commit()
    conn.close()

def save_history(tg_id: int, command: str, query: str, answer: str, difficulty: int = 1):
    conn = db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history(tg_id, command, query, answer, timestamp, difficulty) VALUES(?,?,?,?,?,?)",
        (tg_id, command, query, answer, datetime.now().isoformat(), difficulty)
    )
    conn.commit()
    conn.close()
    add_xp(tg_id, difficulty * 10)

def add_xp(tg_id: int, amount: int):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT xp, level FROM users WHERE tg_id = ?", (tg_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    xp, level = row
    xp = (xp or 0) + amount
    new_level = xp // 1000 + 1
    c.execute("UPDATE users SET xp = ?, level = ? WHERE tg_id = ?", (xp, new_level, tg_id))
    if new_level > level:
        add_achievement(tg_id, f"Уровень {new_level}", f"Достигнут уровень {new_level}", "🏆")
    conn.commit()
    conn.close()

def add_achievement(tg_id: int, name: str, description: str, icon: str = "🏆"):
    conn = db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO achievements(tg_id, name, description, earned_at, icon) VALUES(?,?,?,?,?)",
        (tg_id, name, description, datetime.now().isoformat(), icon)
    )
    conn.commit()
    conn.close()

def get_user_stats(tg_id: int):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE tg_id = ?", (tg_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return 1, 0, 0, 0
    level, xp = result or (1, 0)
    c.execute("SELECT COUNT(*) FROM history WHERE tg_id = ?", (tg_id,))
    total_solved = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(DISTINCT date(timestamp)) FROM history WHERE tg_id = ?", (tg_id,))
    active_days = c.fetchone()[0] or 0
    conn.close()
    return level or 1, xp or 0, total_solved, active_days


def get_history(tg_id: int, limit: int = 5):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT command, query, answer, timestamp FROM history WHERE tg_id = ? ORDER BY id DESC LIMIT ?",
              (tg_id, limit))
    history = c.fetchall()
    conn.close()
    return history

def clear_history(tg_id: int):
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE tg_id = ?", (tg_id,))
    conn.commit()
    conn.close()

# ---------------------------
# SymPy helpers
# ---------------------------
ALLOWED_VARS = ['x', 'y', 'z', 'a', 'b', 'c', 't', 'n']
SYMBOLS = {name: Symbol(name) for name in ALLOWED_VARS}
transformations = standard_transformations + (implicit_multiplication, convert_xor)

def safe_parse(expr_text: str):
    if expr_text is None:
        raise ValueError("Пустое выражение")
    try:
        return parse_expr(expr_text, transformations=transformations, local_dict=SYMBOLS)
    except Exception:
        try:
            return sympify(expr_text, locals=SYMBOLS)
        except Exception:
            raise ValueError(f"Не удалось разобрать выражение: {expr_text}")

def parse_equation(text: str):
    text = (text or "").strip()
    if '=' in text:
        parts = text.split('=', 1)
        left = parts[0].strip() or '0'
        right = parts[1].strip() or '0'
        L = safe_parse(left)
        R = safe_parse(right)
        return Eq(L, R)
    else:
        return Eq(safe_parse(text), 0)

def solve_equation_stepwise(eq: Eq, var=SYMBOLS['x']):
    try:
        expr = simplify(eq.lhs - eq.rhs)
        if expr.is_polynomial(var) and expr.as_poly(var).degree() == 1:
            a = expr.coeff(var, 1)
            b = expr.subs(var, 0)
            if a == 0:
                return ["Уравнение не имеет решений"], []
            solution = -b / a
            steps = [
                f"📝 Уравнение: {eq.lhs} = {eq.rhs}",
                f"➡️ Переносим всё влево: {expr} = 0",
                f"🔍 Выделяем {var}: {a}*{var} + {b} = 0",
                f"🎯 Решение: {var} = -({b})/({a}) = {simplify(solution)}"
            ]
            return steps, [simplify(solution)]

        elif expr.is_polynomial(var) and expr.as_poly(var).degree() == 2:
            a = expr.coeff(var, 2)
            b = expr.coeff(var, 1)
            c_val = expr.subs(var, 0)
            D = simplify(b ** 2 - 4 * a * c_val)
            steps = [
                f"📝 Квадратное уравнение: {expr} = 0",
                f"📊 Коэффициенты: a = {a}, b = {b}, c = {c_val}",
                f"🧮 Дискриминант: D = b² - 4ac = {b}² - 4*{a}*{c_val} = {D}"
            ]
            if D < 0:
                steps.append("❌ D < 0: Действительных корней нет")
                return steps, []
            sqrtD = sqrt(D)
            x1 = simplify((-b + sqrtD) / (2 * a))
            x2 = simplify((-b - sqrtD) / (2 * a))
            steps += [
                f"✅ Корень 1: x₁ = (-b + √D)/(2a) = {x1}",
                f"✅ Корень 2: x₂ = (-b - √D)/(2a) = {x2}"
            ]
            return steps, [x1, x2]
        else:
            solutions = list(solveset(expr, var, domain=S.Reals))
            steps = [f"📝 Уравнение: {eq.lhs} = {eq.rhs}"]
            if solutions:
                steps.append(f"🎯 Найдено решений: {len(solutions)}")
                for i, sol in enumerate(solutions, 1):
                    steps.append(f"✅ x{i} = {simplify(sol)}")
            else:
                steps.append("❌ Решений не найдено")
            return steps, solutions
    except Exception as e:
        return [f"⚠️ Ошибка при решении: {str(e)}"], []

def explain_derivative_steps(expr_text: str) -> List[str]:
    x = SYMBOLS['x']
    try:
        expr = safe_parse(expr_text)
    except Exception as e:
        return [f"Ошибка разбора: {e}"]
    steps = [f"📝 Выражение: f(x) = {expr}"]
    try:
        if expr.is_Pow and expr.base == x and expr.exp.is_number:
            n = expr.exp
            steps += [
                f"Правило степени: (x^n)' = n·x^(n-1), n={n}",
                f"Итог: f'(x) = {n}*x^{n - 1}"
            ]
        elif expr.is_Add:
            terms = list(expr.as_ordered_terms())
            steps.append("Линейность: (u+v)' = u' + v'")
            for i, t in enumerate(terms, 1):
                steps.append(f"• d/dx({t}) вычисляем по соответствующим правилам")
        elif expr.is_Mul:
            steps.append("Производная произведения: (uv)' = u'v + uv'")
        elif expr.is_Function:
            if expr.func == sin:
                steps.append("(sin x)' = cos x")
            elif expr.func == cos:
                steps.append("(cos x)' = -sin x")
            elif expr.func == log:
                steps.append("(ln x)' = 1/x (с учётом цепочки для ln(u))")
            elif expr.func == exp:
                steps.append("(e^x)' = e^x (с учётом цепочки для e^{u})")
            else:
                steps.append("Применяем правило цепочки: (f(g(x)))' = f'(g(x))·g'(x)")
        else:
            steps.append("Применяем базовые правила дифференцирования к частям выражения.")
        res = simplify(diff(expr, x))
        steps.append(f"🎯 Результат: f'(x) = {res}")
    except Exception as e:
        steps.append(f"Ошибка вычисления: {e}")
    return steps

def explain_integral_steps(expr_text: str) -> List[str]:
    x = SYMBOLS['x']
    try:
        expr = safe_parse(expr_text)
    except Exception as e:
        return [f"Ошибка разбора: {e}"]
    steps = [f"📝 Интеграл: ∫({expr}) dx"]
    try:
        if expr.is_Pow and expr.base == x and expr.exp.is_number and expr.exp != -1:
            n = expr.exp
            steps += [
                "Формула: ∫x^n dx = x^(n+1)/(n+1) + C, n≠-1",
                f"Здесь n={n} ⇒ ∫x^{n} dx = x^{n + 1}/({n + 1}) + C"
            ]
        elif expr == 1 / x:
            steps.append("Формула: ∫1/x dx = ln|x| + C")
        elif expr.is_Function:
            if expr.func == sin:
                steps.append("Формула: ∫sin x dx = -cos x + C")
            elif expr.func == cos:
                steps.append("Формула: ∫cos x dx = sin x + C")
            elif expr.func == exp:
                steps.append("Формула: ∫e^x dx = e^x + C")
            else:
                steps.append("Ищем подходящую замену u=g(x) или используем известные интегралы.")
        elif expr.is_Add:
            steps.append("Линейность: ∫(u+v)dx = ∫u dx + ∫v dx")
        elif expr.is_Mul:
            steps.append("Пробуем вынести константу или применить замену/по частям.")
        else:
            steps.append("Применяем известные формулы интегрирования.")
        res = simplify(integrate(expr, x))
        steps.append(f"🎯 Результат: ∫({expr}) dx = {res} + C")
    except Exception as e:
        steps.append(f"Ошибка вычисления: {e}")
    return steps

# ---------------------------
# Plot builder
# ---------------------------
def build_plot(func_text: str, xmin: float, xmax: float, out_path: str):
    try:
        x = symbols('x')
        f = safe_parse(func_text)
        xs = np.linspace(xmin, xmax, 1000)
        ys = []
        for val in xs:
            try:
                y_val = float(f.subs(x, val))
                ys.append(y_val)
            except Exception:
                ys.append(np.nan)
        plt.figure(figsize=(10, 6))
        plt.plot(xs, ys, linewidth=2)
        plt.title(f'График функции: y = {func_text}', fontsize=14)
        plt.xlabel('x', fontsize=12)
        plt.ylabel('y', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.axhline(0, linewidth=0.6)
        plt.axvline(0, linewidth=0.6)
        plt.savefig(out_path, dpi=120, bbox_inches='tight')
        plt.close()
        return True
    except Exception as e:
        print(f"Ошибка построения графика: {e}")
        return False

def calculate_expression(expr_text: str):
    try:
        expr = safe_parse(expr_text)
        result = expr.evalf()
        return str(result), []
    except Exception as e:
        return None, [f"❌ Ошибка вычисления: {str(e)}"]

# ---------------------------
# MATH_SUMMARY (конспекты)
# ---------------------------
MATH_SUMMARY = {
    "квадратные уравнения": """
📚 <b>Квадратные уравнения</b>

<b>Общий вид:</b>
ax² + bx + c = 0, где a ≠ 0

<b>Дискриминант:</b>
D = b² - 4ac
x1 = (-b + √D) / (2a)
x2 = (-b - √D) / (2a)

<b>Формулы корней:</b>
• Если D > 0: два различных корня
  x₁ = (-b + √D)/(2a)
  x₂ = (-b - √D)/(2a)

• Если D = 0: один корень (два совпадающих)
  x = -b/(2a)

• Если D < 0: действительных корней нет

<b>Теорема Виета:</b>
Для приведенного квадратного уравнения x² + px + q = 0:
x₁ + x₂ = -p
x₁ * x₂ = q

<b>Пример:</b>
Решить: x² - 5x + 6 = 0
D = 25 - 24 = 1
x₁ = (5 + 1)/2 = 3
x₂ = (5 - 1)/2 = 2
    """,

    "производная": """
📚 <b>Производная</b>

<b>Определение:</b>
Производная функции f(x) в точке x₀ - это предел отношения приращения функции к приращению аргумента:
f'(x₀) = lim(Δx→0) [f(x₀+Δx) - f(x₀)]/Δx

<b>Основные правила дифференцирования:</b>
1. (c)' = 0 (константа)
2. (xⁿ)' = n*xⁿ⁻¹ (степенная функция)
3. (eˣ)' = eˣ
4. (aˣ)' = aˣ * ln(a)
5. (ln x)' = 1/x
6. (sin x)' = cos x
7. (cos x)' = -sin x
8. (tg x)' = 1/cos²x
9. (ctg x)' = -1/sin²x

<b>Правила операций:</b>
• (u + v)' = u' + v'
• (u - v)' = u' - v'
• (u * v)' = u'v + uv'
• (u/v)' = (u'v - uv')/v²

<b>Производная сложной функции:</b>
f(g(x))' = f'(g(x)) * g'(x)

<b>Пример:</b>
Найти производную: (x³ + 2x²)'
= (x³)' + (2x²)' = 3x² + 4x
    """,

    "интегралы": """
📚 <b>Интегралы</b>

<b>Неопределенный интеграл:</b>
∫f(x)dx = F(x) + C, где F'(x) = f(x)

<b>Основные интегралы:</b>
1. ∫0 dx = C
2. ∫xⁿ dx = xⁿ⁺¹/(n+1) + C (n ≠ -1)
3. ∫1/x dx = ln|x| + C
4. ∫eˣ dx = eˣ + C
5. ∫aˣ dx = aˣ/ln(a) + C
6. ∫sin x dx = -cos x + C
7. ∫cos x dx = sin x + C
8. ∫1/cos²x dx = tg x + C
9. ∫1/sin²x dx = -ctg x + C

<b>Методы интегрирования:</b>
1. <b>Замена переменной:</b> ∫f(g(x))g'(x)dx = ∫f(t)dt
2. <b>Интегрирование по частям:</b> ∫udv = uv - ∫vdu

<b>Определенный интеграл:</b>
∫[a,b] f(x)dx = F(b) - F(a)

<b>Пример:</b>
∫(3x² + 2x)dx = x³ + x² + C
    """,

    "линейные уравнения": """
📚 <b>Линейные уравнения</b>

<b>Общий вид:</b>
ax + b = 0, где a ≠ 0

<b>Алгоритм решения:</b>
1. Перенести все члены с x в одну сторону
2. Перенести свободные члены в другую сторону
3. Разделить на коэффициент при x

<b>Формула решения:</b>
x = -b/a

<b>Примеры:</b>
1. 2x + 6 = 0
   2x = -6
   x = -3

2. 3x - 5 = 7
   3x = 12
   x = 4

3. 4(x + 2) = 20
   4x + 8 = 20
   4x = 12
   x = 3

<b>Проверка решения:</b>
Подставьте найденный x в исходное уравнение
    """,

    "тригонометрия": """
📚 <b>Тригонометрия</b>

<b>Основные тождества:</b>
• sin²α + cos²α = 1
• 1 + tg²α = 1/cos²α
• 1 + ctg²α = 1/sin²α
• tgα * ctgα = 1

<b>Формулы сложения:</b>
• sin(α ± β) = sinα cosβ ± cosα sinβ
• cos(α ± β) = cosα cosβ ∓ sinα sinβ
• tg(α ± β) = (tgα ± tgβ)/(1 ∓ tgα tgβ)

<b>Формулы двойного угла:</b>
• sin2α = 2 sinα cosα
• cos2α = cos²α - sin²α = 2cos²α - 1 = 1 - 2sin²α
• tg2α = 2tgα/(1 - tg²α)

<b>Формулы приведения:</b>
sin(π/2 ± α) = cosα
cos(π/2 ± α) = ∓ sinα
sin(π ± α) = ∓ sinα
cos(π ± α) = -cosα

<b>Значения основных углов:</b>
0°: sin=0, cos=1
30°: sin=1/2, cos=√3/2
45°: sin=√2/2, cos=√2/2
60°: sin=√3/2, cos=1/2
90°: sin=1, cos=0
    """,

    "логарифмы": """
📚 <b>Логарифмы</b>

<b>Определение:</b>
logₐb = c ⇔ aᶜ = b

<b>Основные свойства:</b>
1. logₐ1 = 0
2. logₐa = 1
3. logₐ(b * c) = logₐb + logₐc
4. logₐ(b/c) = logₐb - logₐc
5. logₐbⁿ = n * logₐb
6. logₐb = 1/log_b a
7. logₐb = logₖb / logₖa (формула перехода)

<b>Натуральный логарифм:</b>
ln x = logₑx, где e ≈ 2.71828

<b>Десятичный логарифм:</b>
lg x = log₁₀x

<b>Примеры:</b>
1. log₂8 = 3 (так как 2³ = 8)
2. ln e = 1
3. lg 100 = 2
4. log₅25 = 2
    """
}

# ---------------------------
# Keyboards / UI
# ---------------------------
def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.row("🧮 Калькулятор", "📈 Графики", "🎯 Решить")
    kb.row("📐 Упростить", "🧩 Разложить", "📊 Производная")
    kb.row("∫ Интеграл", "📚 Конспекты", "🎮 Тренировка")
    kb.row("📊 Статистика", "🌟 Достижения", "⚙️ Настройки")
    kb.row("ℹ️ Помощь", "🌐 Weather Forecast", "📷 Решить по фото")
    return kb

def calc_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
    kb.row("7", "8", "9", "➗")
    kb.row("4", "5", "6", "✖️")
    kb.row("1", "2", "3", "➖")
    kb.row("0", ".", "=", "➕")
    kb.row("⬅️ Назад", "C", "()", "√")
    return kb

def settings_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📋 История", "🧹 Очистить историю")
    kb.row("⬅️ Назад в меню")
    return kb

calc_mode: Dict[int, bool] = {}
calc_buffer: Dict[int, str] = {}

def calc_reset(user_id: int):
    calc_mode[user_id] = True
    calc_buffer[user_id] = ""

def calc_append(user_id: int, token: str):
    buf = calc_buffer.get(user_id, "")
    token_map = {"➗": "/", "✖️": "*", "➖": "-", "➕": "+"}
    t = token_map.get(token, token)
    if t == "√":
        t = "sqrt("
    elif t == "()":
        if buf and (buf[-1].isalnum() or buf[-1] == ")"):
            t = "*("
        else:
            t = "("
    calc_buffer[user_id] = buf + t

def calc_eval(user_id: int) -> str:
    expr = calc_buffer.get(user_id, "")
    if not expr:
        return "0"
    try:
        res = safe_parse(expr).evalf()
        calc_buffer[user_id] = str(res)
        return str(res)
    except Exception as e:
        return f"Ошибка: {e}"

# ---------------------------
# Handlers: menu & commands
# ---------------------------
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    ensure_user(message)
    help_text = """ 🎉 <b>Добро пожаловать в MathMaster AI!</b> 🤖

Доступные возможности:
• 🧮 Калькулятор
• 📈 Графики
• 🎯 Решить
• 📐 Упростить
• 🧩 Разложить
• 📊 Производная
• ∫ Интеграл
• 📚 Конспекты
• 🎮 Тренировка
• 📊 Статистика
• 🌟 Достижения

Пример ввода выражения: <code>2*sin(pi/6)+1</code>
    """.strip()
    bot.send_message(message.chat.id, help_text, reply_markup=main_keyboard())

# ---------- Помощь (пользовательский блок) ----------
@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def help_handler(message):
    ensure_user(message)
    help_text = """🎉 <b>MathMaster AI - Помощь</b> 🤖

<b>Основные возможности:</b>
• 🧮 <b>Калькулятор</b> - вычисление выражений
• 📈 <b>Графики</b> - построение графиков функций
• 🎯 <b>Решить</b> - решение уравнений
• 📐 <b>Упростить</b> - упрощение выражений
• 🧩 <b>Разложить</b> - разложение на множители
• 📊 <b>Производная</b> - нахождение производных
• ∫ <b>Интеграл</b> - вычисление интегралов
• 📚 <b>Конспекты</b> - теоретические материалы
• 🎮 <b>Тренировка</b> - практика в виде квизов
• 📊 <b>Статистика</b> - ваша статистика
• 🌟 <b>Достижения</b> - заработанные достижения
• ⚙️ <b>Настройки</b> - управление историей

<b>Примеры использования:</b>
• Вычисление: <code>2+2*2</code>
• Уравнение: <code>2x+3=11</code>
• График: <code>sin(x) -5 5</code>
• Производная: <code>x^2</code>
• Интеграл: <code>2x</code>

Для начала работы просто выберите нужную функцию из меню или введите математическое выражение!
""".strip()
    bot.send_message(message.chat.id, help_text, reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "🧮 Калькулятор")
def calc_handler(message):
    ensure_user(message)
    calc_reset(message.from_user.id)
    bot.send_message(message.chat.id,
                     "🧮 <b>Калькулятор</b>\nНабирайте выражение кнопками. Нажмите '=' для вычисления.",
                     reply_markup=calc_keyboard())

@bot.message_handler(func=lambda m: m.text == "📈 Графики")
def plot_handler(message):
    ensure_user(message)
    msg = bot.send_message(message.chat.id,
                           "📈 <b>Построение графика</b>\nВведите функцию и диапазон:\n"
                           "<code>функция xmin xmax</code>\n\nПример: <code>sin(x) + x^2 -5 5</code>")
    bot.register_next_step_handler(msg, process_plot)

@bot.message_handler(func=lambda m: m.text == "🎯 Решить")
def solve_handler(message):
    ensure_user(message)
    msg = bot.send_message(message.chat.id,
                           "🎯 <b>Решение уравнения</b>\nВведите уравнение:\n\nПримеры:\n"
                           "<code>2x + 5 = 13</code>\n<code>x^2 - 5x + 6 = 0</code>")
    bot.register_next_step_handler(msg, process_equation)

@bot.message_handler(func=lambda m: m.text in ["📐 Упростить", "🧩 Разложить", "📊 Производная", "∫ Интеграл"])
def math_ops_handler(message):
    ensure_user(message)
    ops = {
        "📐 Упростить": ("упростить", "Упрощение выражения"),
        "🧩 Разложить": ("разложить", "Разложение на множители"),
        "📊 Производная": ("производная", "Нахождение производной"),
        "∫ Интеграл": ("интеграл", "Нахождение интеграла")
    }
    op, desc = ops[message.text]
    msg = bot.send_message(message.chat.id, f"📝 <b>{desc}</b>\nВведите выражение:\n\nПример: <code>x^2 + 2x + 1</code>")
    bot.register_next_step_handler(msg, lambda m: process_math_op(m, op))

@bot.message_handler(func=lambda m: m.text == "📚 Конспекты")
def summary_handler(message):
    ensure_user(message)
    topics = list(MATH_SUMMARY.keys())
    kb = InlineKeyboardMarkup(row_width=2)
    for topic in topics:
        kb.add(InlineKeyboardButton(topic.capitalize(), callback_data=f"topic_{topic}"))
    kb.add(InlineKeyboardButton("📖 Все конспекты", callback_data="topic_all"))
    bot.send_message(
        message.chat.id,
        "📚 <b>Выберите тему для изучения:</b>\n\nЗдесь вы найдете теоретические материалы по различным разделам математики.",
        reply_markup=kb
    )

@bot.message_handler(func=lambda m: m.text == "🎮 Тренировка")
def quiz_handler(message):
    ensure_user(message)
    start_quiz(message)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats_handler(message):
    ensure_user(message)
    show_stats(message)

@bot.message_handler(func=lambda m: m.text == "🌟 Достижения")
def achievements_handler(message):
    ensure_user(message)
    show_achievements(message)

@bot.message_handler(func=lambda m: m.text == "⚙️ Настройки")
def settings_handler(message):
    ensure_user(message)
    bot.send_message(message.chat.id, "⚙️ <b>Настройки</b>", reply_markup=settings_keyboard())

@bot.message_handler(func=lambda m: m.text in ["⬅️ Назад", "⬅️ Назад в меню", "⬅️ Назад в меню"])
def back_handler(message):
    ensure_user(message)
    calc_mode[message.from_user.id] = False
    bot.send_message(message.chat.id, "📋 <b>Главное меню</b>", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "📋 История")
def history_handler(message):
    ensure_user(message)
    show_history(message)

@bot.message_handler(func=lambda m: m.text == "🧹 Очистить историю")
def clear_history_handler(message):
    ensure_user(message)
    clear_history(message.from_user.id)
    bot.send_message(message.chat.id, "✅ История очищена!", reply_markup=settings_keyboard())

# ---------------------------
# "Открыть бота" (Weather Forecast)
# ---------------------------
@bot.message_handler(func=lambda m: m.text == "🌐 Weather Forecast")
def open_site_handler(message):
    ensure_user(message)
    local_url = "https://t.me/weatherworld4554_bot"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Открыть бота (Weather Forecast)", url=local_url))
    kb.add(InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_menu"))
    bot.send_message(message.chat.id, "🌐 Открыть Бота WeatherForecast:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    bot.send_message(call.message.chat.id, "📋 Главное меню", reply_markup=main_keyboard())

# ---------------------------
# OCR + photo solving
# ---------------------------
# Если tesseract в нестандартном месте на Windows, укажите путь:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def preprocess_image_for_ocr(path: str) -> Image.Image:
    img_cv = cv2.imread(path)
    if img_cv is None:
        raise RuntimeError("Не удалось открыть изображение для OCR.")
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    thr = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 10)
    pil_img = Image.fromarray(thr)
    return pil_img

def ocr_image_to_text(path: str) -> str:
    try:
        pil = preprocess_image_for_ocr(path)
        custom_config = r'--psm 6'
        text = pytesseract.image_to_string(pil, config=custom_config, lang='eng+rus')
        text = text.strip()
        return text
    except Exception as e:
        print("OCR error:", e)
        return ""

def detect_task_type_and_solve(recognized_text: str, user_id: int) -> str:
    txt = (recognized_text or "").replace('\n', ' ').strip()
    if not txt:
        return "❌ Не удалось распознать текст на изображении. Попробуйте сделать фото крупнее и четче."

    try:
        # Уравнение
        if '=' in txt:
            eq_text = txt
            try:
                eq = parse_equation(eq_text)
                steps, sols = solve_equation_stepwise(eq)
                resp = "🔎 Распознанный текст:\n<code>{}</code>\n\n".format(eq_text)
                resp += "🧮 Решение уравнения:\n" + "\n".join(steps)
                if sols:
                    resp += f"\n\n✅ Корни: {', '.join(map(str, sols))}"
                else:
                    resp += "\n\n❌ Действительных корней не найдено."
                save_history(user_id, "photo_solve", eq_text, str(sols), 3)
                return resp
            except Exception as e:
                return f"❌ Не удалось корректно разобрать уравнение: {e}\nРаспознанный текст: {txt}"

        # Интеграл
        if '∫' in txt or 'int(' in txt.lower() or 'integr' in txt.lower():
            expr = txt
            try:
                steps = explain_integral_steps(expr)
                resp = "🔎 Распознанный текст:\n<code>{}</code>\n\n".format(expr)
                resp += "\n".join(steps)
                save_history(user_id, "photo_integral", expr, str(steps), 3)
                return resp
            except Exception as e:
                return f"❌ Ошибка при разборе интеграла: {e}\nРаспознанный текст: {txt}"

        # Производная
        if "d/dx" in txt or "d dx" in txt or "deriv" in txt.lower() or "prime" in txt.lower():
            expr = txt
            try:
                steps = explain_derivative_steps(expr)
                resp = "🔎 Распознанный текст:\n<code>{}</code>\n\n".format(expr)
                resp += "\n".join(steps)
                save_history(user_id, "photo_derivative", expr, str(steps), 3)
                return resp
            except Exception as e:
                return f"❌ Ошибка при разборе производной: {e}\nРаспознанный текст: {txt}"

        # Иначе — пытаемся вычислить как выражение
        expr = txt
        try:
            result, err = calculate_expression(expr)
            if result:
                resp = "🔎 Распознанный текст:\n<code>{}</code>\n\n".format(expr)
                resp += f"🧮 Результат: <b>{result}</b>"
                save_history(user_id, "photo_eval", expr, result, 2)
                return resp
            else:
                return "❌ Не удалось вычислить распознанное выражение.\nРаспознанный текст: " + txt
        except Exception as e:
            return f"❌ Ошибка при попытке вычислить распознанный текст: {e}\nРаспознанный текст: {txt}"

    except Exception as e:
        return f"❌ Внутренняя ошибка анализа: {e}"

@bot.message_handler(func=lambda m: m.text == "📷 Решить по фото")
def photo_hint_handler(message):
    ensure_user(message)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("⬅️ Назад")
    bot.send_message(message.chat.id,
                     "📷 Пришлите фото задачи (фотографируйте крупно и чётко). Я постараюсь распознать и решить её автоматически.\n\n"
                     "Поддерживаются: алгебраические выражения, уравнения (с '='), интегралы/производные (если понятны символы).",
                     reply_markup=kb)

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("temp.png", 'wb') as new_file:
            new_file.write(downloaded_file)

        extracted_text = extract_text_from_image("temp.png")
        if not extracted_text:
            bot.reply_to(message, "❌ Не удалось распознать текст на изображении. Попробуйте фото покрупнее или при лучшем освещении.")
            return

        lines = [line.strip() for line in extracted_text.split('\n') if line.strip()]
        response = ""
        for line in lines:
            result = calculate_expression(line)
            if result is not None:
                response += f"📄 {line} = {result}\n"
            else:
                response += f"📄 {line} ❌ Не удалось вычислить\n"

        bot.reply_to(message, response)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при обработке фото: {e}")
# ---------------------------
# Processors: equation / plot / math ops
# ---------------------------
def process_equation(message):
    ensure_user(message)
    txt = (message.text or "").strip()
    if not txt:
        bot.send_message(message.chat.id, "❌ Введите уравнение!")
        return
    try:
        eq = parse_equation(txt)
        steps, solutions = solve_equation_stepwise(eq)
        response = "🧮 <b>Решение уравнения</b>\n\n" + "\n".join(steps)
        if solutions:
            response += f"\n\n✅ <b>Корни:</b> {', '.join(map(str, solutions))}"
        bot.send_message(message.chat.id, response)
        save_history(message.from_user.id, "solve", txt, str(solutions), 2)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

def process_plot(message):
    ensure_user(message)
    try:
        args = (message.text or "").split()
        if len(args) < 3:
            bot.send_message(message.chat.id, "❌ Формат: функция xmin xmax (пример: sin(x)+x^2 -5 5)")
            return
        func_text = " ".join(args[:-2])
        xmin = float(args[-2])
        xmax = float(args[-1])
        if xmin >= xmax:
            bot.send_message(message.chat.id, "❌ xmin должен быть меньше xmax!")
            return
        out_path = os.path.join(IMG_DIR, f"plot_{message.from_user.id}_{int(time.time())}.png")
        if build_plot(func_text, xmin, xmax, out_path):
            with open(out_path, 'rb') as f:
                bot.send_photo(message.chat.id, f, caption=f"📈 График: y = {func_text}\nДиапазон: [{xmin}, {xmax}]")
            save_history(message.from_user.id, "plot", f"{func_text} {xmin} {xmax}", out_path, 2)
        else:
            bot.send_message(message.chat.id, "❌ Ошибка построения графика!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

def process_math_op(message, operation):
    ensure_user(message)
    expr_text = (message.text or "").strip()
    if not expr_text:
        bot.send_message(message.chat.id, "❌ Введите выражение!")
        return
    try:
        expr = safe_parse(expr_text)
        result = None
        if operation == "упростить":
            result = simplify(expr)
            response = f"📐 <b>Упрощение:</b>\n<code>{expr_text}</code>\n\n✅ <b>Результат:</b>\n<code>{result}</code>"
        elif operation == "разложить":
            result = factor(expr)
            response = f"🧩 <b>Разложение:</b>\n<code>{expr_text}</code>\n\n✅ <b>Результат:</b>\n<code>{result}</code>"
        elif operation == "производная":
            x = SYMBOLS['x']
            result = diff(expr, x)
            steps = explain_derivative_steps(expr_text)
            response = f"📊 <b>Производная:</b>\nd/dx(<code>{expr_text}</code>)\n\n" + "\n".join(steps)
        elif operation == "интеграл":
            x = SYMBOLS['x']
            result = integrate(expr, x)
            steps = explain_integral_steps(expr_text)
            response = f"∫ <b>Интеграл:</b>\n∫(<code>{expr_text}</code>) dx\n\n" + "\n".join(steps)
        bot.send_message(message.chat.id, response)
        save_history(message.from_user.id, operation, expr_text, str(result), 2)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

# ---------------------------
# Quiz logic
# ---------------------------
def start_quiz(message):
    ensure_user(message)
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, topic, question, right_answer, wrong1, wrong2, wrong3, explanation, difficulty, box FROM quiz_cards ORDER BY box ASC, RANDOM() LIMIT 1"
    )
    row = c.fetchone()
    conn.close()
    if not row:
        bot.send_message(message.chat.id, "❌ Нет доступных вопросов для тренировки")
        return
    qid, topic, question, right, w1, w2, w3, expl, diffc, box = row
    options = [right, w1, w2, w3]
    random.shuffle(options)
    kb = InlineKeyboardMarkup()
    for i, opt in enumerate(options):
        is_right = 1 if opt == right else 0
        encoded = quote_plus(opt)
        cb = f"quiz:{qid}:{i}:{is_right}:{encoded}"
        kb.add(InlineKeyboardButton(opt, callback_data=cb))
    bot.send_message(message.chat.id, f"🎮 <b>Тренировка</b> | Тема: <i>{topic}</i>\n\n{question}", reply_markup=kb)

def update_quiz_stats(tg_id: int, correct: bool):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT correct, total, streak, max_streak FROM quiz_stats WHERE tg_id = ?", (tg_id,))
    row = c.fetchone()
    if not row:
        stats = {"correct": 0, "total": 0, "streak": 0, "max_streak": 0}
    else:
        stats = {"correct": row[0] or 0, "total": row[1] or 0, "streak": row[2] or 0, "max_streak": row[3] or 0}
    stats["total"] += 1
    if correct:
        stats["correct"] += 1
        stats["streak"] += 1
        stats["max_streak"] = max(stats["max_streak"], stats["streak"])
    else:
        stats["streak"] = 0
    c.execute("SELECT id FROM quiz_stats WHERE tg_id = ?", (tg_id,))
    exists = c.fetchone()
    if exists:
        c.execute("UPDATE quiz_stats SET correct=?, total=?, streak=?, max_streak=?, updated_at=? WHERE tg_id=?",
                  (stats["correct"], stats["total"], stats["streak"], stats["max_streak"], datetime.now().isoformat(),
                   tg_id))
    else:
        c.execute("INSERT INTO quiz_stats (tg_id, correct, total, streak, max_streak, updated_at) VALUES (?,?,?,?,?,?)",
                  (tg_id, stats["correct"], stats["total"], stats["streak"], stats["max_streak"],
                   datetime.now().isoformat()))
    conn.commit()
    conn.close()
    if correct:
        add_xp(tg_id, 50)

def adjust_quiz_box(qid: int, correct: bool):
    conn = db()
    c = conn.cursor()
    if correct:
        c.execute("UPDATE quiz_cards SET box = box + 1 WHERE id = ?", (qid,))
    else:
        c.execute("UPDATE quiz_cards SET box = CASE WHEN box > 0 THEN box - 1 ELSE 0 END WHERE id = ?", (qid,))
    conn.commit()
    conn.close()

def get_quiz_card(qid: int):
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT id, topic, question, right_answer, wrong1, wrong2, wrong3, explanation, difficulty FROM quiz_cards WHERE id = ?",
        (qid,))
    row = c.fetchone()
    conn.close()
    return row

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("quiz:"))
def quiz_callback(call):
    try:
        parts = call.data.split(":", 4)
        if len(parts) != 5:
            bot.answer_callback_query(call.id, "Ошибка данных вопроса", show_alert=True)
            return
        _, qid_str, sel_str, is_right_str, encoded_text = parts
        qid = int(qid_str)
        is_correct = is_right_str == "1"
        chosen_text = unquote_plus(encoded_text)
    except Exception:
        bot.answer_callback_query(call.id, "Ошибка данных вопроса", show_alert=True)
        return

    card = get_quiz_card(qid)
    if not card:
        bot.answer_callback_query(call.id, "Вопрос не найден", show_alert=True)
        return

    qid_db, topic, question, right, w1, w2, w3, expl, diffc = card
    update_quiz_stats(call.from_user.id, is_correct)
    adjust_quiz_box(qid, is_correct)

    if is_correct:
        txt = f"🎉 <b>Правильно!</b>\n\n<b>Вопрос:</b> {question}\n<b>Ваш ответ:</b> {chosen_text}\n\n<i>Объяснение:</i> {expl}\n\n+50 XP"
        bot.answer_callback_query(call.id, "✅ Верно!", show_alert=False)
    else:
        txt = (f"❌ <b>Неправильно</b>\n\n<b>Вопрос:</b> {question}\n"
               f"<b>Ваш ответ:</b> {chosen_text}\n<b>Правильный ответ:</b> {right}\n\n<i>Объяснение:</i> {expl}")
        bot.answer_callback_query(call.id, "❌ Неверно", show_alert=False)

    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode="HTML")
    except Exception:
        bot.send_message(call.message.chat.id, txt)

    next_kb = InlineKeyboardMarkup()
    next_kb.add(InlineKeyboardButton("➡️ Следующий вопрос", callback_data="quiz_next"))
    bot.send_message(call.message.chat.id, "Готовы продолжить?", reply_markup=next_kb)

@bot.callback_query_handler(func=lambda call: call.data == "quiz_next")
def quiz_next(call):
    class FakeMsg:
        def __init__(self, chat_id, from_user):
            self.chat = type("c", (), {"id": chat_id})
            self.from_user = from_user
    msg = FakeMsg(call.message.chat.id, call.from_user)
    start_quiz(msg)

# ---------------------------
# Stats / achievements / history
# ---------------------------
def show_stats(message):
    ensure_user(message)
    level, xp, total_solved, active_days = get_user_stats(message.from_user.id)
    conn = db()
    c = conn.cursor()
    c.execute("SELECT correct, total, streak, max_streak FROM quiz_stats WHERE tg_id = ?", (message.from_user.id,))
    row = c.fetchone()
    conn.close()
    correct = total = streak = max_streak = 0
    if row:
        correct, total, streak, max_streak = [r or 0 for r in row]

    progress = xp % 1000
    progress_percent = int((progress / 1000) * 100)
    progress_bar = "🟩" * (progress_percent // 10) + "⬜" * (10 - (progress_percent // 10))

    stats_text = f"""
 📊 <b>Ваша статистика</b>
 🏆 Уровень: <b>{level}</b>
 ⭐ Опыт: <b>{xp}</b> XP {progress_bar} {progress}/1000  ({progress_percent}%)
 ✅ Решено задач: <b>{total_solved}</b>
 📅 Активных дней: <b>{active_days}</b>
 🎮 Квизы:
 • Точность: <b>{(0 if total == 0 else round(100 * correct / total))}%</b> ({correct}/{total})
 • Серия сейчас: <b>{streak}</b> | Максимум: <b>{max_streak}</b>
    """.strip()
    bot.send_message(message.chat.id, stats_text)

def show_achievements(message):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT name, description, icon FROM achievements WHERE tg_id = ? ORDER BY earned_at",
              (message.from_user.id,))
    achievements = c.fetchall()
    conn.close()
    if not achievements:
        bot.send_message(message.chat.id, "🎯 У вас пока нет достижений! Решайте задачи, чтобы получить их!")
        return
    achievements_text = "🌟 <b>Ваши достижения</b>\n\n"
    for name, desc, icon in achievements:
        achievements_text += f"{icon} <b>{name}</b> — {desc}\n"
    bot.send_message(message.chat.id, achievements_text)

def show_history(message):
    history = get_history(message.from_user.id, 10)
    if not history:
        bot.send_message(message.chat.id, "📝 История запросов пуста")
        return
    history_text = "📋 <b>Последние запросы:</b>\n\n"
    for i, (command, query, answer, timestamp) in enumerate(history, 1):
        try:
            time_str = datetime.fromisoformat(timestamp).strftime("%d.%m %H:%M")
        except Exception:
            time_str = timestamp
        ans_snippet = (answer or "")
        if len(ans_snippet) > 60:
            ans_snippet = ans_snippet[:60] + "..."
        history_text += f"{i}. {time_str} — {command}: {query}\n   ➡️ {ans_snippet}\n\n"
    bot.send_message(message.chat.id, history_text)

# ---------------------------
# Universal text handler
# ---------------------------
@bot.message_handler(func=lambda m: True, content_types=['text'])
def universal_handler(message):
    ensure_user(message)
    text = (message.text or "").strip()

    if calc_mode.get(message.from_user.id, False) and text in {"0","1","2","3","4","5","6","7","8","9",".","➗","✖️","➖","➕","C","()","√","=","⬅️ Назад"}:
        if text == "⬅️ Назад":
            calc_mode[message.from_user.id] = False
            bot.send_message(message.chat.id, "📋 <b>Главное меню</b>", reply_markup=main_keyboard())
            return
        if text == "C":
            calc_buffer[message.from_user.id] = ""
            bot.send_message(message.chat.id, "🧮 Буфер очищен", reply_markup=calc_keyboard())
            return
        if text == "=":
            res = calc_eval(message.from_user.id)
            bot.send_message(message.chat.id, f"🧮 <b>Результат:</b> {res}", reply_markup=calc_keyboard())
            save_history(message.from_user.id, "calc", calc_buffer.get(message.from_user.id, ""), str(res), 1)
            return
        calc_append(message.from_user.id, text)
        bot.send_message(message.chat.id, f"🔢 <code>{calc_buffer.get(message.from_user.id, '')}</code>", reply_markup=calc_keyboard())
        return

    menu_commands = {"🧮 Калькулятор", "📈 Графики", "🎯 Решить", "📐 Упростить",
                     "🧩 Разложить", "📊 Производная", "∫ Интеграл", "📚 Конспекты",
                     "🎮 Тренировка", "📊 Статистика", "🌟 Достижения", "⚙️ Настройки",
                     "ℹ️ Помощь", "⬅️ Назад", "⬅️ Назад в меню", "📋 История", "🧹 Очистить историю", "🌐 Weather Forecast", "📷 Решить по фото"}
    if text in menu_commands:
        return

    try:
        if not text:
            bot.send_message(message.chat.id, "🤔 <b>Не понял запрос</b>\nНажмите /help или используйте меню.")
            return

        if '=' in text:
            process_equation(message)
            return

        if any(op in text for op in ['+', '-', '*', '/', '^', 'sqrt', 'sin', 'cos', 'tan', 'log', 'exp']):
            result, info = calculate_expression(text)
            if result:
                response = f"🧮 <b>Результат:</b>\n<code>{text}</code> = <b>{result}</b>"
                bot.send_message(message.chat.id, response)
                save_history(message.from_user.id, "calc", text, result, 1)
            else:
                bot.send_message(message.chat.id, "❌ Не удалось вычислить выражение")
            return

        low = text.lower()
        if low == "привет":
            bot.send_message(message.chat.id, "Привет! 😊 Чем могу помочь? (Попробуй /help для списка возможностей)")
            return
        if low == "админ":
            bot.send_message(message.chat.id, f"👑 ID администратора: <b>{ADMIN_ID}</b>")
            return

        bot.send_message(message.chat.id,
                         "🤔 <b>Не понял запрос</b>\n\nПопробуйте:\n"
                         "• Математическое выражение: <code>2+2</code>\n"
                         "• Уравнение: <code>2x+3=11</code>\n"
                         "• Команду из меню\n\n"
                         "Или нажмите /help для справки")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка обработки: {str(e)}")
        traceback.print_exc()

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    print("🔧 Инициализация базы данных...")
    init_db()
    print("✅ База данных готова")
    print("🤖 MathMaster AI запускается...")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("Выход по Ctrl+C")
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
