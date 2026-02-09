from __future__ import annotations

import ast
import operator
import os
import re
import math
import json
import time
import random
import sqlite3
import threading
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import requests
import telebot
from telebot import types, apihelper


try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _RETRY_AVAILABLE = True
except Exception:
    HTTPAdapter = None  # type: ignore[assignment]
    Retry = None  # type: ignore[assignment]
    _RETRY_AVAILABLE = False

try:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        parse_expr,
        standard_transformations,
        implicit_multiplication,
        convert_xor,
        function_exponentiation,
    )

    SYMPY_AVAILABLE = True
except Exception:
    SYMPY_AVAILABLE = False
    sp = None  # type: ignore
    parse_expr = None  # type: ignore
    standard_transformations = None  # type: ignore
    implicit_multiplication = None  # type: ignore
    convert_xor = None  # type: ignore
    function_exponentiation = None  # type: ignore

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except Exception:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False
    plt = None  # type: ignore

try:
    from PIL import Image, ImageEnhance, ImageFilter

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False
    Image = None  # type: ignore
    ImageEnhance = None  # type: ignore
    ImageFilter = None  # type: ignore

try:
    import easyocr

    EASYOCR_AVAILABLE = True
except Exception:
    EASYOCR_AVAILABLE = False
    easyocr = None  # type: ignore

try:
    import pytesseract

    PYTESS_AVAILABLE = True
except Exception:
    PYTESS_AVAILABLE = False
    pytesseract = None  # type: ignore


# -------------------- Config --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "7955033715:AAHCitRiRD7nFTeX8YO-B1heGlneRAxuLto").strip()
DB_PATH = os.getenv("DB_PATH", "mathmaster.sqlite3").strip()
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").strip().rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "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").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

# Silence noisy LibreSSL warning if user accidentally has urllib3 v2 installed.
# (Correct fix is: pin urllib3<2 in requirements.)
warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL.*")



# -------------------- Utils --------------------
def html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "")


def today_utc_date() -> str:
    return utc_now().date().isoformat()


# -------------------- DB --------------------
class DB:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA foreign_keys=ON;")

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        tg_id INTEGER PRIMARY KEY,
                        username TEXT DEFAULT '',
                        first_name TEXT DEFAULT '',
                        last_name TEXT DEFAULT '',
                        level INTEGER NOT NULL DEFAULT 1,
                        xp INTEGER NOT NULL DEFAULT 0,
                        streak INTEGER NOT NULL DEFAULT 0,
                        last_streak_date TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        last_active TEXT NOT NULL
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tg_id INTEGER NOT NULL,
                        kind TEXT NOT NULL,
                        query TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (tg_id) REFERENCES users(tg_id) ON DELETE CASCADE
                    )
                    """
                )

                # Lessons (200+ micro lessons)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lessons (
                        id TEXT PRIMARY KEY,
                        exam TEXT NOT NULL,     -- school / oge / ege_base / ege_prof
                        topic TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        difficulty INTEGER NOT NULL DEFAULT 1,
                        ord INTEGER NOT NULL
                    )
                    """
                )

                # Skills (Duolingo-like)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS skills (
                        id TEXT PRIMARY KEY,
                        exam TEXT NOT NULL,      -- oge / ege_base / ege_prof
                        task_num INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        ord INTEGER NOT NULL
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_skill (
                        tg_id INTEGER NOT NULL,
                        skill_id TEXT NOT NULL,
                        level INTEGER NOT NULL DEFAULT 0,     -- 0..5
                        xp INTEGER NOT NULL DEFAULT 0,
                        correct INTEGER NOT NULL DEFAULT 0,
                        total INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (tg_id, skill_id),
                        FOREIGN KEY (tg_id) REFERENCES users(tg_id) ON DELETE CASCADE,
                        FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_review (
                        tg_id INTEGER NOT NULL,
                        skill_id TEXT NOT NULL,
                        due_at TEXT NOT NULL,
                        interval_days REAL NOT NULL DEFAULT 0,
                        ease REAL NOT NULL DEFAULT 2.3,
                        PRIMARY KEY (tg_id, skill_id),
                        FOREIGN KEY (tg_id) REFERENCES users(tg_id) ON DELETE CASCADE,
                        FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
                    )
                    """
                )

                conn.commit()
            finally:
                conn.close()

    def ensure_user(self, u: types.User) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT tg_id FROM users WHERE tg_id=?", (u.id,))
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        """
                        INSERT INTO users (tg_id, username, first_name, last_name, created_at, last_active)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            u.id,
                            u.username or "",
                            u.first_name or "",
                            u.last_name or "",
                            now,
                            now,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE users SET username=?, first_name=?, last_name=?, last_active=?
                        WHERE tg_id=?
                        """,
                        (
                            u.username or "",
                            u.first_name or "",
                            u.last_name or "",
                            now,
                            u.id,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    def add_history(self, tg_id: int, kind: str, query: str, answer: str) -> None:
        now = datetime.utcnow().isoformat()
        query = (query or "")[:500]
        answer = (answer or "")[:500]
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO history (tg_id, kind, query, answer, created_at) VALUES (?,?,?,?,?)",
                    (tg_id, kind, query, answer, now),
                )
                conn.commit()
            finally:
                conn.close()

    def get_history(self, tg_id: int, limit: int = 10) -> List[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT kind, query, answer, created_at
                FROM history WHERE tg_id=?
                ORDER BY id DESC LIMIT ?
                """,
                (tg_id, limit),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    def clear_history(self, tg_id: int) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM history WHERE tg_id=?", (tg_id,))
                conn.commit()
            finally:
                conn.close()

    def get_user(self, tg_id: int) -> Optional[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
            return cur.fetchone()
        finally:
            conn.close()

    def add_xp(self, tg_id: int, amount: int, streak_date: Optional[str] = None) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT xp, level, streak, last_streak_date FROM users WHERE tg_id=?", (tg_id,))
                row = cur.fetchone()
                if row is None:
                    return

                xp = int(row["xp"] or 0) + int(amount)
                level = max(1, xp // 1000 + 1)
                streak = int(row["streak"] or 0)
                last_date = str(row["last_streak_date"] or "")

                if streak_date:
                    if last_date == "":
                        streak = 1
                        last_date = streak_date
                    elif last_date == streak_date:
                        pass
                    else:
                        try:
                            prev = datetime.fromisoformat(last_date).date()
                            curd = datetime.fromisoformat(streak_date).date()
                            delta = (curd - prev).days
                            streak = streak + 1 if delta == 1 else 1
                        except Exception:
                            streak = 1
                        last_date = streak_date

                cur.execute(
                    "UPDATE users SET xp=?, level=?, streak=?, last_streak_date=? WHERE tg_id=?",
                    (xp, level, streak, last_date, tg_id),
                )
                conn.commit()
            finally:
                conn.close()

    # ----- lessons -----
    def upsert_lesson(self, lesson: Dict[str, Any]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO lessons (id, exam, topic, title, content, difficulty, ord)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        exam=excluded.exam,
                        topic=excluded.topic,
                        title=excluded.title,
                        content=excluded.content,
                        difficulty=excluded.difficulty,
                        ord=excluded.ord
                    """,
                    (
                        lesson["id"],
                        lesson["exam"],
                        lesson["topic"],
                        lesson["title"],
                        lesson["content"],
                        int(lesson.get("difficulty", 1)),
                        int(lesson.get("ord", 0)),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_lessons(self, exam: str, topic: Optional[str] = None, limit: int = 30) -> List[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            if topic:
                cur.execute(
                    """
                    SELECT id, topic, title, difficulty
                    FROM lessons WHERE exam=? AND topic=?
                    ORDER BY ord ASC LIMIT ?
                    """,
                    (exam, topic, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, topic, title, difficulty
                    FROM lessons WHERE exam=?
                    ORDER BY ord ASC LIMIT ?
                    """,
                    (exam, limit),
                )
            return list(cur.fetchall())
        finally:
            conn.close()

    def get_lesson(self, lesson_id: str) -> Optional[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,))
            return cur.fetchone()
        finally:
            conn.close()

    def count_lessons(self) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM lessons")
            return int(cur.fetchone()["c"])
        finally:
            conn.close()

    # ----- skills -----
    def upsert_skill(self, skill: Dict[str, Any]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO skills (id, exam, task_num, title, description, topic, ord)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        exam=excluded.exam,
                        task_num=excluded.task_num,
                        title=excluded.title,
                        description=excluded.description,
                        topic=excluded.topic,
                        ord=excluded.ord
                    """,
                    (
                        skill["id"],
                        skill["exam"],
                        int(skill["task_num"]),
                        skill["title"],
                        skill["description"],
                        skill["topic"],
                        int(skill["ord"]),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_skills(self, exam: str) -> List[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, exam, task_num, title, description, topic, ord
                FROM skills WHERE exam=?
                ORDER BY ord ASC
                """,
                (exam,),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    def get_user_skill_map(self, tg_id: int, exam: str) -> Dict[str, sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT us.skill_id, us.level, us.xp, us.correct, us.total
                FROM user_skill us
                JOIN skills s ON s.id = us.skill_id
                WHERE us.tg_id=? AND s.exam=?
                """,
                (tg_id, exam),
            )
            rows = list(cur.fetchall())
            return {str(r["skill_id"]): r for r in rows}
        finally:
            conn.close()

    def bump_user_skill(self, tg_id: int, skill_id: str, correct: bool, xp_delta: int) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT level, xp, correct, total FROM user_skill WHERE tg_id=? AND skill_id=?",
                    (tg_id, skill_id),
                )
                row = cur.fetchone()
                level = int(row["level"]) if row else 0
                xp = int(row["xp"]) if row else 0
                cor = int(row["correct"]) if row else 0
                tot = int(row["total"]) if row else 0
                tot += 1
                if correct:
                    cor += 1
                xp += int(xp_delta)
                new_level = min(5, max(level, xp // 120))
                cur.execute(
                    """
                    INSERT INTO user_skill (tg_id, skill_id, level, xp, correct, total, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tg_id, skill_id) DO UPDATE SET
                        level=excluded.level,
                        xp=excluded.xp,
                        correct=excluded.correct,
                        total=excluded.total,
                        updated_at=excluded.updated_at
                    """,
                    (tg_id, skill_id, new_level, xp, cor, tot, now),
                )
                conn.commit()
            finally:
                conn.close()

    # ----- review -----
    def count_due_reviews(self, tg_id: int) -> int:
        now = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_review WHERE tg_id=? AND due_at<=?", (tg_id, now))
            return int(cur.fetchone()["c"])
        finally:
            conn.close()

    def list_due_reviews(self, tg_id: int, limit: int = 10) -> List[sqlite3.Row]:
        now = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT r.skill_id, r.due_at, r.interval_days, r.ease, s.exam, s.task_num, s.title
                FROM user_review r
                JOIN skills s ON s.id = r.skill_id
                WHERE r.tg_id=? AND r.due_at<=?
                ORDER BY r.due_at ASC
                LIMIT ?
                """,
                (tg_id, now, limit),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    def get_review(self, tg_id: int, skill_id: str) -> Optional[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM user_review WHERE tg_id=? AND skill_id=?", (tg_id, skill_id))
            return cur.fetchone()
        finally:
            conn.close()

    def upsert_review(self, tg_id: int, skill_id: str, due_at: str, interval_days: float, ease: float) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO user_review (tg_id, skill_id, due_at, interval_days, ease)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(tg_id, skill_id) DO UPDATE SET
                        due_at=excluded.due_at,
                        interval_days=excluded.interval_days,
                        ease=excluded.ease
                    """,
                    (tg_id, skill_id, due_at, float(interval_days), float(ease)),
                )
                conn.commit()
            finally:
                conn.close()


# -------------------- Learning content (skills + lessons) --------------------
def build_micro_lessons() -> List[Dict[str, Any]]:
    """
    Генерирует 200+ коротких уроков (карточек) + теорию по заданиям ОГЭ/ЕГЭ.
    Важно: это оригинальный материал и тренажёр (без копирования вариантов экзамена).
    """
    base_cards: List[Tuple[str, str, str]] = [
        (
            "Алгебра",
            "Порядок действий",
            "<b>Сначала</b> скобки → степени/корни → умножение/деление → сложение/вычитание.\n"
            "<b>Пример:</b> 2+3·4 = 14.",
        ),
        (
            "Алгебра",
            "Линейные уравнения",
            "<b>Схема:</b> ax+b=c → ax=c-b → x=(c-b)/a.\n"
            "<b>Проверка:</b> подставьте x обратно.",
        ),
        (
            "Алгебра",
            "Квадратные уравнения",
            "<b>D</b>=b²-4ac.\n"
            "x=(-b±√D)/(2a).\n"
            "<b>Виет:</b> x₁+x₂=-b/a, x₁·x₂=c/a (если a≠0).",
        ),
        (
            "Алгебра",
            "Формулы сокращённого умножения",
            "(a±b)²=a²±2ab+b²; a²-b²=(a-b)(a+b);\n"
            "(a±b)³=a³±3a²b+3ab²±b³.",
        ),
        (
            "Алгебра",
            "Дроби",
            "a/b ± c/d = (ad±bc)/bd.\n"
            "<b>Важно:</b> сокращайте дробь и следите за ОДЗ (знаменатель ≠ 0).",
        ),
        (
            "Функции",
            "Линейная функция",
            "y=kx+b.\n"
            "k — наклон (если k>0, график растёт), b — пересечение с осью y.",
        ),
        (
            "Геометрия",
            "Пифагор",
            "В прямоугольном треугольнике c²=a²+b² (c — гипотенуза).",
        ),
        (
            "Геометрия",
            "Площади и длины",
            "Sпрям=a·b; Sтр=1/2·a·h; Sкруга=πr²;\n"
            "Lокр=2πr.",
        ),
        (
            "Тригонометрия",
            "Таблица значений",
            "sin(π/6)=1/2, cos(π/3)=1/2, sin(π/4)=cos(π/4)=√2/2.\n"
            "<b>Тождество:</b> sin²x+cos²x=1.",
        ),
        (
            "Вероятность",
            "Классическая вероятность",
            "P = m/n, где n — число равновероятных исходов, m — благоприятные.\n"
            "<b>Комбинаторика:</b> C(n,k)=n!/(k!(n-k)!).",
        ),
        (
            "Анализ",
            "Производная",
            "(x^n)'=n·x^(n-1), (sin x)'=cos x, (cos x)'=-sin x, (ln x)'=1/x.",
        ),
        (
            "Анализ",
            "Интеграл",
            "∫x^n dx = x^(n+1)/(n+1)+C; ∫sin x dx=-cos x+C; ∫cos x dx=sin x+C.",
        ),
        (
            "Статистика",
            "Среднее и медиана",
            "Среднее: (a₁+…+aₙ)/n.\n"
            "Медиана — середина упорядоченного набора.",
        ),
        (
            "Текстовые",
            "Скорость, время, расстояние",
            "s=v·t, v=s/t, t=s/v.\n"
            "<b>Совет:</b> приведи единицы к одним (часы/км).",
        ),
        (
            "Комбинаторика",
            "Подсчёт вариантов",
            "Перестановки: n!\n"
            "Размещения: A(n,k)=n!/(n-k)!\n"
            "Сочетания: C(n,k)=n!/(k!(n-k)!).",
        ),
    ]

    exams = ["school", "oge", "ege_base", "ege_prof"]
    topics = [
        "Алгебра",
        "Функции",
        "Геометрия",
        "Тригонометрия",
        "Вероятность",
        "Анализ",
        "Статистика",
        "Текстовые",
        "Комбинаторика",
        "Смешанное",
    ]

    lessons: List[Dict[str, Any]] = []
    ord_ = 0
    # 1) базовые карточки для каждого экзамена
    for exam in exams:
        for topic, title, body in base_cards:
            ord_ += 1
            lessons.append(
                {
                    "id": f"{exam}:base:{ord_}",
                    "exam": exam,
                    "topic": topic,
                    "title": title,
                    "content": f"<b>{title}</b>\n\n{body}\n\n💡 Решай 5–7 задач, чтобы закрепить.",
                    "difficulty": 1,
                    "ord": ord_,
                }
            )

    # 2) дополнительные микро‑уроки (генерация)
    # делаем 200+ за счёт комбинации (topic, sub, tips)
    tips = [
        "Следи за знаками и скобками.",
        "Проверяй ответ подстановкой.",
        "Упрощай до конца и сокращай дроби.",
        "Если есть проценты — переводи в дробь p/100.",
        "Рисунок/схема в геометрии часто ускоряет решение.",
        "В вероятности посчитай общее число исходов и благоприятные.",
        "В задачах на графики — сначала область определения и ключевые точки.",
    ]
    sub_algebra = ["Упрощение выражений", "Разложение на множители", "Системы уравнений", "Неравенства", "Прогрессии"]
    sub_geometry = ["Углы", "Треугольники", "Окружность", "Площадь", "Подобие"]
    sub_trig = ["Таблица значений", "Формулы приведения", "Тождества", "Уравнения"]
    sub_analysis = ["Пределы", "Производная", "Экстремумы", "Интеграл"]
    sub_stats = ["Среднее", "Медиана", "Мода", "Диаграммы"]
    sub_map = {
        "Алгебра": sub_algebra,
        "Геометрия": sub_geometry,
        "Тригонометрия": sub_trig,
        "Анализ": sub_analysis,
        "Статистика": sub_stats,
        "Функции": ["Линейная", "Квадратичная", "Модуль", "График", "Преобразования"],
        "Вероятность": ["Монета", "Кубик", "Сочетания", "Условная вероятность"],
        "Текстовые": ["Скорость/время", "Работа", "Смеси", "Проценты"],
        "Комбинаторика": ["Факториал", "Размещения", "Сочетания", "Перестановки"],
        "Смешанное": ["Повторение", "Комбо‑задачи", "Ловушки", "Стратегии"],
    }
    # Generate ~220 micro lessons
    for exam in exams:
        for topic in topics:
            for i, sub in enumerate(sub_map.get(topic, ["Основы"]), start=1):
                for j in range(1, 4):
                    ord_ += 1
                    tip = tips[(ord_ + i + j) % len(tips)]
                    lessons.append(
                        {
                            "id": f"{exam}:{topic}:{sub}:{j}",
                            "exam": exam,
                            "topic": topic,
                            "title": f"{sub} • шаг {j}",
                            "content": (
                                f"<b>{topic} • {sub}</b>\n\n"
                                f"Мини‑правило #{j}: {tip}\n\n"
                                "✅ После этого сделай 3 простых примера и 2 средних."
                            ),
                            "difficulty": 1 + (j == 3),
                            "ord": ord_,
                        }
                    )

    # 3) Карточки по заданиям (ОГЭ/ЕГЭ): теория + примеры + ошибки
    def _topic_theory(topic: str) -> str:
        if topic == "Алгебра":
            return "Формулы: D=b²-4ac; (a±b)²=a²±2ab+b²; a²-b²=(a-b)(a+b)."
        if topic == "Функции":
            return "Линейная: y=kx+b. Парабола: y=ax²+bx+c. Важно: область определения."
        if topic == "Геометрия":
            return "Пифагор: c²=a²+b². Площади: Sтр=1/2·a·h; Sкруга=πr²."
        if topic == "Тригонометрия":
            return "sin²x+cos²x=1; tan x = sin x / cos x. Выучи значения 0°,30°,45°,60°,90°."
        if topic == "Вероятность":
            return "P=m/n (равновероятно). Комбинаторика: C(n,k)=n!/(k!(n-k)!)."
        if topic == "Анализ":
            return "(x^n)'=n·x^(n-1); ∫x^n dx=x^(n+1)/(n+1)+C."
        if topic == "Статистика":
            return "Среднее: сумма/n. Медиана: середина отсортированного набора."
        if topic == "Текстовые":
            return "s=v·t; t=s/v; v=s/t. В процентах: p% = p/100."
        if topic == "Комбинаторика":
            return "n!, A(n,k)=n!/(n-k)!, C(n,k)=n!/(k!(n-k)!)."
        return "Повторяй базовые правила и тренируйся регулярно."

    def _topic_examples(topic: str) -> str:
        ex = {
            "Алгебра": ["Решите: 3x-7=8", "Найдите корни: x^2-5x+6=0", "Упростите: (x+1)^2-x^2-2x"],
            "Функции": ["Найдите y при x=2, y=3x-1", "Найдите f(−1), если f(x)=x^2+2x", "По графику найдите x, где y=0"],
            "Геометрия": ["Катеты 6 и 8 → гипотенуза?", "Площадь треугольника a=10, h=6", "Площадь круга r=3"],
            "Тригонометрия": ["sin(π/6) = ?", "cos(π/3) = ?", "Упростите: sin^2x+cos^2x"],
            "Вероятность": ["Бросок кубика: P(6)=?", "2 броска монеты: P(2 орла)=?", "Сколькими способами выбрать 2 из 5?"],
            "Анализ": ["Найдите (x^3)'", "Найдите ∫2x dx", "Найдите f'(2), если f=x^2+1"],
            "Статистика": ["Среднее чисел 2,3,7,8", "Медиана: 1,2,10,11,20", "По диаграмме найдите максимум"],
            "Текстовые": ["60 км за 2 ч → скорость?", "Работа: 3 ч и 6 ч вместе?", "Скидка 20% от 500 = ?"],
            "Комбинаторика": ["Сколько перестановок из 4?", "C(6,2)=?", "A(5,3)=?"],
            "Смешанное": ["Соберите план решения", "Проверьте ответ подстановкой", "Найдите ошибку в преобразованиях"],
        }
        items = ex.get(topic, ["Решите 3–5 задач по теме."])
        return "\n".join(["• %s" % i for i in items])

    def _topic_mistakes(topic: str) -> str:
        m = {
            "Алгебра": ["Потеряли знак при переносе.", "Не сократили дробь.", "Забыли ОДЗ."],
            "Функции": ["Перепутали k и b.", "Подставили не то значение x.", "Не учли ОДЗ."],
            "Геометрия": ["Перепутали катет/гипотенузу.", "Неверно выбрали формулу площади.", "Не сделали рисунок."],
            "Тригонометрия": ["Смешали градусы и радианы.", "Забыли sin²+cos²=1.", "Не учли периодичность."],
            "Вероятность": ["Считают исходы неверно.", "Забыли, что исходы равновероятны.", "Перепутали сочетания и размещения."],
            "Анализ": ["Ошибка в таблице производных.", "Не применили правило произведения.", "Забыли +C в интеграле."],
            "Статистика": ["Не отсортировали для медианы.", "Перепутали среднее и медиану.", "Ошиблись в сумме."],
            "Текстовые": ["Смешали единицы.", "Сразу считали в процентах без дроби.", "Потеряли смысл формулы."],
            "Комбинаторика": ["Путают C и A.", "Забывают про факториал.", "Считают с повторениями, когда нельзя."],
            "Смешанное": ["Слишком рано округлили.", "Не проверили ответ.", "Пропустили простой случай."],
        }
        items = m.get(topic, ["Проверяйте решения и делайте само‑проверку."])
        return "\n".join(["• %s" % i for i in items])

    for sk in build_skills_registry():
        exam = str(sk["exam"])
        num = int(sk["task_num"])
        topic = str(sk["topic"])
        title = str(sk["title"])
        desc = str(sk["description"])
        base_diff = 1 if exam == "school" else 2 if exam in ("oge", "ege_base") else 3
        if exam == "ege_prof" and num >= 15:
            base_diff = 4

        ord_ += 1
        lessons.append(
            {
                "id": f"{exam}:task{num:02d}:theory",
                "exam": exam,
                "topic": topic,
                "title": f"№{num} {title} • Теория",
                "content": (
                    f"<b>{_topic_theory(topic)}</b>\n\n"
                    f"<b>Что тренируем:</b> {html_escape(desc)}\n\n"
                    "✅ Нажмите «Практика» в разделе обучения, чтобы закрепить."
                ),
                "difficulty": base_diff,
                "ord": ord_,
            }
        )

        ord_ += 1
        lessons.append(
            {
                "id": f"{exam}:task{num:02d}:examples",
                "exam": exam,
                "topic": topic,
                "title": f"№{num} {title} • Примеры",
                "content": (
                    f"<b>Примеры по теме</b>\n\n{_topic_examples(topic)}\n\n"
                    "💡 Сначала решите 2 лёгких, затем 2 средних, затем 1 сложную."
                ),
                "difficulty": min(5, base_diff + 1),
                "ord": ord_,
            }
        )

        ord_ += 1
        lessons.append(
            {
                "id": f"{exam}:task{num:02d}:mistakes",
                "exam": exam,
                "topic": topic,
                "title": f"№{num} {title} • Ошибки",
                "content": (
                    "<b>Типовые ошибки</b>\n\n"
                    f"{_topic_mistakes(topic)}\n\n"
                    "✅ Перед ответом сделайте мини‑проверку: знаки, ОДЗ, единицы."
                ),
                "difficulty": base_diff,
                "ord": ord_,
            }
        )

    # Ensure at least 200
    return lessons


def build_skills_registry() -> List[Dict[str, Any]]:
    """
    Навыки (по номерам заданий). Это ядро Duolingo‑обучения.
    """
    skills: List[Dict[str, Any]] = []
    ord_ = 0

    def add(exam: str, task_num: int, title: str, desc: str, topic: str) -> None:
        nonlocal ord_
        ord_ += 1
        skills.append(
            {
                "id": f"{exam}_{task_num:02d}",
                "exam": exam,
                "task_num": task_num,
                "title": title,
                "description": desc,
                "topic": topic,
                "ord": ord_,
            }
        )

    # ОГЭ 1..20 (по темам, от простого к сложному)
    oge_map = [
        (1, "Числа и выражения", "Порядок действий, дроби, степени, корни.", "Алгебра"),
        (2, "Проценты и пропорции", "Проценты, скидки/наценки, доли, отношения.", "Алгебра"),
        (3, "Уравнения", "Линейные уравнения, уравнения с дробями.", "Алгебра"),
        (4, "Квадратные уравнения", "D, Виета, разложение на множители.", "Алгебра"),
        (5, "Системы и неравенства", "Системы 2×2, простые неравенства.", "Алгебра"),
        (6, "Функции и графики", "y=kx+b, парабола, чтение графика.", "Функции"),
        (7, "Текстовые задачи", "Скорость/время/работа/смеси/проценты.", "Текстовые"),
        (8, "Прогрессии", "Арифметическая прогрессия: a_n, S_n.", "Алгебра"),
        (9, "Статистика", "Среднее, медиана, мода, диаграммы.", "Статистика"),
        (10, "Вероятность", "Монеты, кубики, комбинации.", "Вероятность"),
        (11, "Треугольники", "Углы, Пифагор, подобие.", "Геометрия"),
        (12, "Окружность", "Углы в окружности, хорды, касательная.", "Геометрия"),
        (13, "Площади", "Площадь треугольника/параллелограмма/круга.", "Геометрия"),
        (14, "Координаты", "Расстояние, середина отрезка, наклон.", "Геометрия"),
        (15, "Тригонометрия", "sin/cos/tan: таблица значений, тождества.", "Тригонометрия"),
        (16, "Комбинаторика", "Факториал, размещения, сочетания.", "Комбинаторика"),
        (17, "Алгебраические дроби", "ОДЗ, сокращение, преобразования.", "Алгебра"),
        (18, "Модуль", "|x|, кусочные функции, графики.", "Функции"),
        (19, "Смешанные задачи", "Повышенный уровень: микс тем.", "Смешанное"),
        (20, "Итоговый микс", "Повторение всего курса ОГЭ.", "Смешанное"),
    ]
    for num, title, desc, topic in oge_map:
        add("oge", num, title, desc, topic)

    # ЕГЭ (База) 1..20
    ege_base_map = [
        (1, "Арифметика", "Дроби, проценты, степени, корни.", "Алгебра"),
        (2, "Преобразования", "Упрощение выражений, формулы.", "Алгебра"),
        (3, "Уравнения", "Линейные/квадратные/дробные.", "Алгебра"),
        (4, "Текстовые задачи", "Скорость/работа/смеси/проценты.", "Текстовые"),
        (5, "Функции", "Значения, графики, преобразования.", "Функции"),
        (6, "Планиметрия", "Площади/периметры, Пифагор.", "Геометрия"),
        (7, "Стереометрия", "Объёмы и площади поверхностей.", "Геометрия"),
        (8, "Вероятность", "Простые вероятности, события.", "Вероятность"),
        (9, "Статистика", "Среднее, диаграммы, таблицы.", "Статистика"),
        (10, "Тригонометрия", "Базовые значения и тождества.", "Тригонометрия"),
        (11, "Прогрессии", "Арифметическая/геометрическая.", "Алгебра"),
        (12, "Неравенства", "Линейные/квадратные.", "Алгебра"),
        (13, "Координаты", "Прямая, расстояния, графики.", "Геометрия"),
        (14, "Комбинаторика", "Подсчёт вариантов.", "Комбинаторика"),
        (15, "Логарифмы (база)", "Определение и свойства.", "Алгебра"),
        (16, "Смешанное 1", "Повторение: микс базовых тем.", "Смешанное"),
        (17, "Смешанное 2", "Повторение: микс базовых тем.", "Смешанное"),
        (18, "Смешанное 3", "Повторение: микс базовых тем.", "Смешанное"),
        (19, "Смешанное 4", "Повторение: микс базовых тем.", "Смешанное"),
        (20, "Смешанное 5", "Повторение: микс базовых тем.", "Смешанное"),
    ]
    for num, title, desc, topic in ege_base_map:
        add("ege_base", num, title, desc, topic)

    # ЕГЭ (Профиль) 1..19
    ege_prof_map = [
        (1, "Вычисления и преобразования", "Степени, корни, логарифмы, выражения.", "Алгебра"),
        (2, "Тригонометрия", "Формулы, значения, уравнения.", "Тригонометрия"),
        (3, "Функции и графики", "Свойства функций, графики.", "Функции"),
        (4, "Планиметрия", "Углы, площади, окружность, подобие.", "Геометрия"),
        (5, "Вероятность", "События, формулы, комбинаторика.", "Вероятность"),
        (6, "Стереометрия", "Объёмы, площади поверхностей.", "Геометрия"),
        (7, "Производная", "Производная и значение в точке.", "Анализ"),
        (8, "Наиб/наим на отрезке", "Экстремумы, исследования.", "Анализ"),
        (9, "Тригонометрические уравнения", "Решения на промежутке.", "Тригонометрия"),
        (10, "Логарифмы/показательные", "Уравнения и неравенства.", "Алгебра"),
        (11, "Планиметрия (сложнее)", "Доказательства/отношения.", "Геометрия"),
        (12, "Графики/параметры", "Преобразования графиков, анализ.", "Функции"),
        (13, "Уравнения (повышенные)", "Комбинированные уравнения.", "Алгебра"),
        (14, "Комбинаторика", "Подсчёт, вероятности, схемы.", "Комбинаторика"),
        (15, "Неравенства", "Рациональные/показательные/лог.", "Алгебра"),
        (16, "Планиметрия (развёрнуто)", "Сложные задачи по геометрии.", "Геометрия"),
        (17, "Параметр", "Уравнения/неравенства с параметром.", "Алгебра"),
        (18, "Экономика", "Кредиты, проценты, рост/убыль.", "Текстовые"),
        (19, "Числа и логика", "Делимость, остатки, оценки.", "Смешанное"),
    ]
    for num, title, desc, topic in ege_prof_map:
        add("ege_prof", num, title, desc, topic)

    return skills


# -------------------- Spaced repetition --------------------
@dataclass(frozen=True)
class ReviewState:
    interval_days: float
    ease: float
    due_at: str


def update_review(prev: Optional[ReviewState], grade: int) -> ReviewState:
    grade = max(0, min(5, int(grade)))
    now = utc_now()
    if prev is None:
        interval = 0.0
        ease = 2.3
    else:
        interval = float(prev.interval_days)
        ease = float(prev.ease)

    if grade < 3:
        interval = 0.5
    else:
        if interval < 0.9:
            interval = 1.0
        elif interval < 2.9:
            interval = 3.0
        else:
            interval = interval * ease
        ease = ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
        ease = max(1.3, min(3.0, ease))

    return ReviewState(interval_days=interval, ease=ease, due_at=iso(now + timedelta(days=interval)))


def grade_from_accuracy(correct: int, total: int) -> int:
    if total <= 0:
        return 0
    acc = correct / float(total)
    if acc >= 0.9:
        return 5
    if acc >= 0.75:
        return 4
    if acc >= 0.6:
        return 3
    if acc >= 0.4:
        return 2
    if acc > 0:
        return 1
    return 0


# -------------------- Safe Math Engine --------------------
_TRANSFORMS = None
if SYMPY_AVAILABLE:
    _TRANSFORMS = standard_transformations + (implicit_multiplication, convert_xor, function_exponentiation)


class MathEngine:
    def __init__(self) -> None:
        if not SYMPY_AVAILABLE:
            raise RuntimeError("sympy не установлен. Установите зависимости.")

        self._symbols = sp.symbols("x y z t a b c")  # type: ignore[attr-defined]
        self._locals: Dict[str, Any] = {str(s): s for s in self._symbols}
        self._locals.update(
            {
                "Integer": sp.Integer,
                "Rational": sp.Rational,
                "Float": sp.Float,
                "Symbol": sp.Symbol,
                "pi": sp.pi,
                "E": sp.E,
                "e": sp.E,
                "oo": sp.oo,
                "Abs": sp.Abs,
                "abs": sp.Abs,
                "sqrt": sp.sqrt,
                "sin": sp.sin,
                "cos": sp.cos,
                "tan": sp.tan,
                "asin": sp.asin,
                "acos": sp.acos,
                "atan": sp.atan,
                "sinh": sp.sinh,
                "cosh": sp.cosh,
                "tanh": sp.tanh,
                "exp": sp.exp,
                "log": sp.log,
                "ln": sp.log,
                "factorial": sp.factorial,
                "Matrix": sp.Matrix,
            }
        )

    def _format_number(self, val: Any) -> str:
        try:
            if isinstance(val, bool):
                return str(val)
            if isinstance(val, int):
                return str(val)
            if isinstance(val, float):
                v = round(val, 12)
                if float(v).is_integer():
                    return str(int(v))
                s = ("%0.12f" % v).rstrip("0").rstrip(".")
                return s or "0"
        except Exception:
            pass
        return str(val)

    def _ast_eval_numeric(self, expr: str) -> Any:
        """
        Безопасная оценка чисто числовых выражений (без переменных/функций).
        Нужна как быстрый и стабильный fallback, если sympy‑парсер капризничает.
        """

        allowed_bin = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        allowed_un = {ast.UAdd: lambda x: +x, ast.USub: operator.neg}

        tree = ast.parse(expr, mode="eval")

        def _eval(node: ast.AST) -> Any:
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.Num):  # py<3.8
                return node.n
            if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_un:
                return allowed_un[type(node.op)](_eval(node.operand))
            if isinstance(node, ast.BinOp) and type(node.op) in allowed_bin:
                left = _eval(node.left)
                right = _eval(node.right)
                if type(node.op) is ast.Pow:
                    # защита от супер‑степеней
                    try:
                        if abs(float(right)) > 60:
                            raise ValueError("Слишком большая степень")
                    except Exception:
                        raise ValueError("Слишком большая степень")
                return allowed_bin[type(node.op)](left, right)
            raise ValueError("Недопустимое выражение")

        return _eval(tree)

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        t = text.strip()
        # ru -> en
        rep = {"х": "x", "у": "y", "з": "z", "с": "c", "а": "a", "в": "b", "т": "t"}
        for a, b in rep.items():
            t = t.replace(a, b).replace(a.upper(), b.upper())
        # symbols
        sym = {"×": "*", "÷": "/", "∙": "*", "^": "**", "∞": "oo", "π": "pi"}
        for a, b in sym.items():
            t = t.replace(a, b)
        # decimal comma
        t = re.sub(r"(\d),(\d)", r"\1.\2", t)
        # y= / z=
        t = re.sub(r"^\s*[yz]\s*=\s*", "", t, flags=re.IGNORECASE)
        # √
        t = re.sub(r"√\s*\(", "sqrt(", t)
        t = re.sub(r"√\s*([0-9A-Za-z_]+)", r"sqrt(\1)", t)
        # factorial postfix "!"
        t = self._convert_factorials(t)
        return t

    def _convert_factorials(self, expr: str) -> str:
        s = expr
        it = 0
        while "!" in s and it < 50:
            it += 1
            idx = s.find("!")
            if idx <= 0:
                break
            j = idx - 1
            if s[j].isdigit() or s[j] == ".":
                k = j
                while k >= 0 and (s[k].isdigit() or s[k] == "."):
                    k -= 1
                op = s[k + 1 : idx]
                s = s[: k + 1] + "factorial(" + op + ")" + s[idx + 1 :]
                continue
            if s[j] == ")":
                depth = 0
                k = j
                while k >= 0:
                    if s[k] == ")":
                        depth += 1
                    elif s[k] == "(":
                        depth -= 1
                        if depth == 0:
                            break
                    k -= 1
                if k < 0:
                    break
                op = s[k : j + 1]
                s = s[:k] + "factorial" + op + s[idx + 1 :]
                continue
            if s[j].isalnum() or s[j] == "_":
                k = j
                while k >= 0 and (s[k].isalnum() or s[k] == "_"):
                    k -= 1
                op = s[k + 1 : idx]
                s = s[: k + 1] + "factorial(" + op + ")" + s[idx + 1 :]
                continue
            break
        return s

    def parse(self, text: str) -> Any:
        t = self.normalize(text)
        if len(t) > 400:
            raise ValueError("Слишком длинный ввод (лимит 400 символов).")
        try:
            return parse_expr(  # type: ignore[misc]
                t,
                local_dict=self._locals,
                global_dict={
                    "__builtins__": {},
                    "Integer": sp.Integer,
                    "Rational": sp.Rational,
                    "Float": sp.Float,
                    "Symbol": sp.Symbol,
                },
                transformations=_TRANSFORMS,
                evaluate=True,
            )
        except Exception:
            # Fallback: иногда parse_expr ругается на внутренние имена (Integer и т.п.).
            # sympify в связке с locals обычно «дожимает» выражение.
            return sp.sympify(t, locals=self._locals)  # type: ignore[attr-defined]

    def eval(self, text: str) -> Tuple[bool, str]:
        try:
            norm = self.normalize(text)
            # fast path: numeric only (no letters)
            if norm and re.search(r"[A-Za-z_]", norm) is None:
                try:
                    v0 = self._ast_eval_numeric(norm)
                    return True, self._format_number(v0)
                except Exception:
                    pass
            expr = self.parse(text)
            val = expr.evalf()
            if getattr(val, "is_Integer", False):
                return True, str(int(val))
            if getattr(val, "is_Rational", False):
                return True, str(val)
            try:
                f = float(val)
                return True, self._format_number(f)
            except Exception:
                return True, str(val)
        except Exception as e:
            return False, "❌ Ошибка вычисления: %s" % e

    def _short(self, s: Any, limit: int = 220) -> str:
        t = str(s)
        if len(t) <= limit:
            return t
        return t[: max(0, limit - 1)] + "…"

    def eval_full(self, text: str) -> Tuple[bool, str, str]:
        """
        Возвращает:
        - ok
        - HTML сообщение со шагами
        - короткий ответ (для истории)
        """
        try:
            norm = self.normalize(text)
            steps: List[str] = []
            if norm:
                steps.append("1) Нормализуем ввод: <code>%s</code>" % html_escape(self._short(norm, 260)))

            # fast numeric path (no letters)
            if norm and re.search(r"[A-Za-z_]", norm) is None:
                try:
                    v0 = self._ast_eval_numeric(norm)
                    ans = self._format_number(v0)
                    steps.append("2) Считаем как числовое выражение по правилам арифметики.")
                    msg = (
                        "<b>🧮 Вычисление (шаги)</b>\n\n"
                        "<b>Ввод:</b> <code>%s</code>\n\n"
                        "<b>Шаги:</b>\n%s\n\n"
                        "<b>Ответ:</b> <code>%s</code>"
                    ) % (html_escape(text), "\n".join(steps) if steps else "—", html_escape(ans))
                    return True, msg, ans
                except Exception:
                    pass

            expr = self.parse(text)
            try:
                simp = sp.simplify(expr)  # type: ignore[attr-defined]
            except Exception:
                simp = expr

            steps.append("2) Получаем выражение: <code>%s</code>" % html_escape(self._short(expr, 320)))
            if str(simp) != str(expr):
                steps.append("3) Упрощаем: <code>%s</code>" % html_escape(self._short(simp, 320)))

            # symbolic expression (has variables) -> return simplified form
            if getattr(simp, "free_symbols", None):
                ans = str(simp)
                steps.append("4) Есть переменные → возвращаем символический результат.")
                msg = (
                    "<b>🧮 Вычисление (шаги)</b>\n\n"
                    "<b>Ввод:</b> <code>%s</code>\n\n"
                    "<b>Шаги:</b>\n%s\n\n"
                    "<b>Ответ:</b> <code>%s</code>"
                ) % (html_escape(text), "\n".join(steps), html_escape(self._short(ans, 520)))
                return True, msg, ans[:200]

            val = simp.evalf()
            if getattr(val, "is_Integer", False):
                ans = str(int(val))
            elif getattr(val, "is_Rational", False):
                ans = str(val)
            else:
                try:
                    ans = self._format_number(float(val))
                except Exception:
                    ans = str(val)
            steps.append("4) Численный результат: <code>%s</code>" % html_escape(self._short(ans, 120)))

            msg = (
                "<b>🧮 Вычисление (шаги)</b>\n\n"
                "<b>Ввод:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n%s\n\n"
                "<b>Ответ:</b> <code>%s</code>"
            ) % (html_escape(text), "\n".join(steps), html_escape(ans))
            return True, msg, ans
        except Exception as e:
            return False, "❌ Ошибка вычисления: %s" % e, ""

    def solve_equation(self, text: str) -> Tuple[bool, str]:
        try:
            t = self.normalize(text)
            if "=" in t:
                left, right = t.split("=", 1)
                lhs = self.parse(left)
                rhs = self.parse(right)
                eq = sp.Eq(lhs, rhs)  # type: ignore[attr-defined]
            else:
                lhs = self.parse(t)
                rhs = sp.Integer(0)  # type: ignore[attr-defined]
                eq = sp.Eq(lhs, rhs)  # type: ignore[attr-defined]

            vars_ = sorted(list(eq.free_symbols), key=lambda s: str(s))
            var = None
            for cand in vars_:
                if str(cand) == "x":
                    var = cand
                    break
            if var is None:
                var = vars_[0] if vars_ else sp.Symbol("x")  # type: ignore[attr-defined]

            # ---- steps for polynomials (linear/quadratic) ----
            try:
                expr0 = sp.simplify(eq.lhs - eq.rhs)  # type: ignore[attr-defined]
            except Exception:
                expr0 = eq.lhs - eq.rhs  # type: ignore[operator]

            steps: List[str] = [
                "1) Переносим всё влево: <code>%s = 0</code>" % html_escape(self._short(expr0, 520)),
            ]

            poly = None
            deg = -1
            try:
                poly = sp.Poly(expr0, var)  # type: ignore[attr-defined]
                deg = int(poly.degree())
            except Exception:
                poly = None

            if poly is not None and deg == 1:
                a, b = poly.all_coeffs()
                steps.append(
                    "2) Линейное: <code>%s·%s + (%s) = 0</code>"
                    % (html_escape(self._short(a, 160)), html_escape(str(var)), html_escape(self._short(b, 160)))
                )
                if a == 0:
                    return True, (
                        "<b>🧮 Решение уравнения</b>\n\n"
                        "<b>Уравнение:</b> <code>%s</code>\n\n"
                        "<b>Шаги:</b>\n%s\n\n"
                        "<b>❌ Ошибка:</b> коэффициент при %s равен 0."
                    ) % (html_escape(text), "\n".join(steps), html_escape(str(var)))
                x_sol = sp.simplify(-b / a)  # type: ignore[attr-defined]
                steps.append(
                    "3) Делим на коэффициент при %s: <code>%s = -(%s)/(%s) = %s</code>"
                    % (
                        html_escape(str(var)),
                        html_escape(str(var)),
                        html_escape(self._short(b, 160)),
                        html_escape(self._short(a, 160)),
                        html_escape(self._short(x_sol, 220)),
                    )
                )
                return True, (
                    "<b>🧮 Решение уравнения (шаги)</b>\n\n"
                    "<b>Уравнение:</b> <code>%s</code>\n\n"
                    "<b>Шаги:</b>\n%s\n\n"
                    "<b>Ответ:</b> <code>%s = %s</code>"
                ) % (html_escape(text), "\n".join(steps), html_escape(str(var)), html_escape(self._short(x_sol, 260)))

            if poly is not None and deg == 2:
                a, b, c = poly.all_coeffs()
                steps.append(
                    "2) Квадратное: a=<code>%s</code>, b=<code>%s</code>, c=<code>%s</code>"
                    % (
                        html_escape(self._short(a, 160)),
                        html_escape(self._short(b, 160)),
                        html_escape(self._short(c, 160)),
                    )
                )
                D = sp.simplify(b * b - 4 * a * c)  # type: ignore[attr-defined]
                steps.append("3) Дискриминант: <code>D=b^2-4ac = %s</code>" % html_escape(self._short(D, 260)))

                try:
                    if getattr(D, "is_number", False) and float(D) < 0:
                        return True, (
                            "<b>🧮 Решение уравнения (шаги)</b>\n\n"
                            "<b>Уравнение:</b> <code>%s</code>\n\n"
                            "<b>Шаги:</b>\n%s\n\n"
                            "<b>Ответ:</b> <i>действительных корней нет</i>"
                        ) % (html_escape(text), "\n".join(steps))
                except Exception:
                    pass

                sqrtD = sp.sqrt(D)  # type: ignore[attr-defined]
                x1 = sp.simplify((-b + sqrtD) / (2 * a))  # type: ignore[attr-defined]
                x2 = sp.simplify((-b - sqrtD) / (2 * a))  # type: ignore[attr-defined]
                steps.append("4) Корни: <code>%s = (-b±√D)/(2a)</code>" % html_escape(str(var)))
                return True, (
                    "<b>🧮 Решение уравнения (шаги)</b>\n\n"
                    "<b>Уравнение:</b> <code>%s</code>\n\n"
                    "<b>Шаги:</b>\n%s\n\n"
                    "<b>Ответ:</b>\n"
                    "<code>%s1 = %s</code>\n"
                    "<code>%s2 = %s</code>"
                ) % (
                    html_escape(text),
                    "\n".join(steps),
                    html_escape(str(var)),
                    html_escape(self._short(x1, 320)),
                    html_escape(str(var)),
                    html_escape(self._short(x2, 320)),
                )

            # ---- general solve ----
            sols: List[Any] = []
            try:
                sols = list(sp.solve(eq, var))  # type: ignore[attr-defined]
            except Exception:
                sols = []
            if not sols:
                # Try solveset as fallback (often better for trig/log)
                try:
                    ss = sp.solveset(eq, var, domain=sp.S.Reals)  # type: ignore[attr-defined]
                    if ss == sp.S.EmptySet:  # type: ignore[attr-defined]
                        return True, (
                            "<b>🧮 Решение уравнения</b>\n\n"
                            "<b>Уравнение:</b> <code>%s</code>\n\n"
                            "<b>Шаги:</b>\n%s\n\n"
                            "<b>Решений не найдено.</b>"
                        ) % (html_escape(text), "\n".join(steps))
                    if isinstance(ss, sp.FiniteSet):  # type: ignore[attr-defined]
                        sols = list(ss)
                    else:
                        return True, (
                            "<b>🧮 Решение уравнения</b>\n\n"
                            "<b>Уравнение:</b> <code>%s</code>\n\n"
                            "<b>Шаги:</b>\n%s\n\n"
                            "<b>✅ Решение (множество):</b>\n<code>%s</code>"
                        ) % (html_escape(text), "\n".join(steps), html_escape(self._short(ss, 900)))
                except Exception:
                    return True, (
                        "<b>🧮 Решение уравнения</b>\n\n"
                        "<b>Уравнение:</b> <code>%s</code>\n\n"
                        "<b>Шаги:</b>\n%s\n\n"
                        "<b>Решений не найдено.</b>"
                    ) % (html_escape(text), "\n".join(steps))

            lines = [
                "<b>🧮 Решение уравнения</b>\n\n<b>Уравнение:</b> <code>%s</code>" % html_escape(text),
                "",
                "<b>Шаги:</b>",
                "\n".join(steps),
                "",
                "<b>✅ Решения:</b>",
            ]
            multi = len(sols) > 1
            for i, s in enumerate(sols, start=1):
                try:
                    s = sp.simplify(s)  # type: ignore[attr-defined]
                except Exception:
                    pass
                name = ("%s%d" % (str(var), i)) if multi else str(var)
                lines.append("<code>%s = %s</code>" % (html_escape(name), html_escape(self._short(s, 520))))
            return True, "\n".join(lines)
        except Exception as e:
            return False, "❌ Ошибка решения: %s" % e

    def derivative(self, func: str) -> Tuple[bool, str]:
        try:
            x = sp.Symbol("x")  # type: ignore[attr-defined]
            f = self.parse(func)
            d0 = sp.diff(f, x)  # type: ignore[attr-defined]
            d = sp.simplify(d0)  # type: ignore[attr-defined]
            steps = [
                "1) Разбираем: <code>f(x) = %s</code>" % html_escape(self._short(f, 360)),
                "2) Дифференцируем по x: <code>f'(x) = %s</code>" % html_escape(self._short(d0, 360)),
            ]
            if str(d) != str(d0):
                steps.append("3) Упрощаем: <code>f'(x) = %s</code>" % html_escape(self._short(d, 360)))
            msg = (
                "<b>📊 Производная (шаги)</b>\n\n"
                "<b>Ввод:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n%s\n\n"
                "<b>Ответ:</b> <code>%s</code>"
            ) % (html_escape(func), "\n".join(steps), html_escape(self._short(d, 520)))
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка производной: %s" % e

    def integral(self, func: str) -> Tuple[bool, str]:
        try:
            x = sp.Symbol("x")  # type: ignore[attr-defined]
            f = self.parse(func)
            itg0 = sp.integrate(f, x)  # type: ignore[attr-defined]
            itg = sp.simplify(itg0)  # type: ignore[attr-defined]
            steps = [
                "1) Разбираем: <code>f(x) = %s</code>" % html_escape(self._short(f, 360)),
                "2) Интегрируем по x: <code>F(x) = %s</code>" % html_escape(self._short(itg0, 360)),
            ]
            if str(itg) != str(itg0):
                steps.append("3) Упрощаем: <code>F(x) = %s</code>" % html_escape(self._short(itg, 360)))
            msg = (
                "<b>∫ Интеграл (шаги)</b>\n\n"
                "<b>Ввод:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n%s\n\n"
                "<b>Ответ:</b> <code>%s</code> + C"
            ) % (html_escape(func), "\n".join(steps), html_escape(self._short(itg, 520)))
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка интеграла: %s" % e

    def simplify_expr(self, expr: str) -> Tuple[bool, str]:
        try:
            e = self.parse(expr)
            s = sp.simplify(e)  # type: ignore[attr-defined]
            steps = [
                "1) Разбираем: <code>%s</code>" % html_escape(self._short(e, 420)),
                "2) Применяем упрощение (SymPy <code>simplify</code>).",
            ]
            msg = (
                "<b>📐 Упрощение (шаги)</b>\n\n"
                "<b>Ввод:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n%s\n\n"
                "<b>Ответ:</b> <code>%s</code>"
            ) % (html_escape(expr), "\n".join(steps), html_escape(self._short(s, 900)))
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка упрощения: %s" % e

    def factor_expr(self, expr: str) -> Tuple[bool, str]:
        try:
            e = self.parse(expr)
            f = sp.factor(e)  # type: ignore[attr-defined]
            steps = [
                "1) Разбираем: <code>%s</code>" % html_escape(self._short(e, 420)),
                "2) Разложение на множители (SymPy <code>factor</code>).",
            ]
            msg = (
                "<b>🧩 Разложение (шаги)</b>\n\n"
                "<b>Ввод:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n%s\n\n"
                "<b>Ответ:</b> <code>%s</code>"
            ) % (html_escape(expr), "\n".join(steps), html_escape(self._short(f, 900)))
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка разложения: %s" % e

    def limit_expr(self, raw: str) -> Tuple[bool, str]:
        try:
            # formats: "sin(x)/x, x->0" or "sin(x)/x x->0"
            s = raw.strip()
            parts = re.split(r",\s*|\s+(?=x\s*[-–→>])", s, maxsplit=1)
            func_part = parts[0].strip()
            point_part = parts[1].strip() if len(parts) > 1 else "x->0"
            point_part = point_part.replace("→", "->").replace("–", "-")
            m = re.search(r"x\s*->\s*([^\s]+)", point_part)
            point_str = m.group(1) if m else "0"
            x = sp.Symbol("x")  # type: ignore[attr-defined]
            f = self.parse(func_part)
            if point_str in ("oo", "inf"):
                p = sp.oo  # type: ignore[attr-defined]
            elif point_str in ("-oo", "-inf"):
                p = -sp.oo  # type: ignore[attr-defined]
            else:
                p = self.parse(point_str)
            res = sp.limit(f, x, p)  # type: ignore[attr-defined]
            steps = [
                "1) Функция: <code>%s</code>" % html_escape(self._short(f, 420)),
                "2) Точка: <code>x → %s</code>" % html_escape(self._short(point_str, 60)),
                "3) Считаем предел (SymPy <code>limit</code>).",
            ]
            msg = (
                "<b>📈 Предел (шаги)</b>\n\n"
                "<b>Ввод:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n%s\n\n"
                "<b>Ответ:</b> <code>%s</code>"
            ) % (html_escape(raw), "\n".join(steps), html_escape(self._short(res, 900)))
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка предела: %s" % e

    # ----- matrices -----
    def matrix_det(self, matrix_text: str) -> Tuple[bool, str]:
        try:
            mat = self._parse_matrix(matrix_text)
            d = mat.det()
            msg = (
                "<b>🧮 Определитель (шаги)</b>\n\n"
                "<b>Матрица:</b>\n<code>%s</code>\n\n"
                "<b>Шаги:</b>\n1) Разбираем матрицу.\n2) Считаем det (SymPy <code>det</code>).\n\n"
                "<b>Ответ:</b> <code>%s</code>"
            ) % (html_escape(self._short(mat, 900)), html_escape(self._short(d, 200)))
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка матрицы: %s" % e

    def matrix_inv(self, matrix_text: str) -> Tuple[bool, str]:
        try:
            mat = self._parse_matrix(matrix_text)
            inv = mat.inv()
            msg = (
                "<b>🧮 Обратная матрица (шаги)</b>\n\n"
                "<b>Матрица:</b>\n<code>%s</code>\n\n"
                "<b>Шаги:</b>\n1) Проверяем обратимость (det ≠ 0).\n2) Считаем A⁻¹ (SymPy <code>inv</code>).\n\n"
                "<b>Ответ:</b>\n<code>%s</code>"
            ) % (html_escape(self._short(mat, 900)), html_escape(self._short(inv, 900)))
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка матрицы: %s" % e

    def matrix_mul(self, a_text: str, b_text: str) -> Tuple[bool, str]:
        try:
            A = self._parse_matrix(a_text)
            B = self._parse_matrix(b_text)
            C = A * B
            msg = (
                "<b>🧮 Умножение матриц (шаги)</b>\n\n"
                "<b>A:</b>\n<code>%s</code>\n\n"
                "<b>B:</b>\n<code>%s</code>\n\n"
                "<b>Шаги:</b>\n1) Проверяем размеры (A: m×n, B: n×k).\n2) Перемножаем (SymPy).\n\n"
                "<b>Ответ (A·B):</b>\n<code>%s</code>"
            ) % (
                html_escape(self._short(A, 700)),
                html_escape(self._short(B, 700)),
                html_escape(self._short(C, 900)),
            )
            return True, msg
        except Exception as e:
            return False, "❌ Ошибка матриц: %s" % e

    def _parse_matrix(self, text: str) -> Any:
        # Accept formats:
        # 1) [[1,2],[3,4]]
        # 2) 1 2; 3 4
        t = text.strip()
        if t.startswith("[["):
            data = json.loads(t)
            return sp.Matrix(data)  # type: ignore[attr-defined]
        # "1 2; 3 4"
        rows = [r.strip() for r in t.split(";") if r.strip()]
        data2 = []
        for r in rows:
            parts = [p for p in re.split(r"[,\s]+", r.strip()) if p]
            data2.append([self.parse(p) for p in parts])
        return sp.Matrix(data2)  # type: ignore[attr-defined]

    # ----- plots -----
    def plot_2d(self, func: str, x_min: float = -10, x_max: float = 10) -> Optional[BytesIO]:
        if not (MATPLOTLIB_AVAILABLE and NUMPY_AVAILABLE):
            raise RuntimeError("Для графиков нужны зависимости: numpy + matplotlib.")
        x = sp.Symbol("x")  # type: ignore[attr-defined]
        expr = self.parse(func)
        f = sp.lambdify(x, expr, "numpy")  # type: ignore[attr-defined]
        xs = np.linspace(float(x_min), float(x_max), 600)  # type: ignore[union-attr]

        def coerce_1d(vals: Any) -> Any:
            try:
                arr = np.asarray(vals)  # type: ignore[union-attr]
                if arr.shape == ():
                    arr = np.full_like(xs, float(arr))  # type: ignore[union-attr]
                if getattr(arr, "dtype", None) == object:
                    out = []
                    for v in list(arr):
                        try:
                            out.append(float(sp.N(v)))  # type: ignore[attr-defined]
                        except Exception:
                            out.append(float("nan"))
                    arr = np.array(out, dtype=float)  # type: ignore[union-attr]
                if np.iscomplexobj(arr):  # type: ignore[union-attr]
                    imag = np.abs(np.imag(arr))  # type: ignore[union-attr]
                    arr = np.real(arr)  # type: ignore[union-attr]
                    arr = arr.astype(float, copy=False)  # type: ignore[union-attr]
                    arr[imag > 1e-6] = np.nan  # type: ignore[union-attr]
                else:
                    arr = arr.astype(float, copy=False)  # type: ignore[union-attr]
                arr = np.where(np.isfinite(arr), arr, np.nan)  # type: ignore[union-attr]
                return arr
            except Exception:
                out2 = []
                for xv in xs:
                    try:
                        yv = expr.subs(x, float(xv)).evalf()
                        out2.append(float(yv))
                    except Exception:
                        out2.append(float("nan"))
                return np.array(out2, dtype=float)  # type: ignore[union-attr]

        with np.errstate(all="ignore"):  # type: ignore[union-attr]
            try:
                ys = f(xs)
            except Exception:
                ys = None
        ys_arr = coerce_1d(ys)
        if np.all(np.isnan(ys_arr)):  # type: ignore[union-attr]
            raise RuntimeError("Не удалось вычислить значения (возможно, вне области определения).")

        plt.figure(figsize=(10, 6))  # type: ignore[union-attr]
        plt.plot(xs, ys_arr, linewidth=2, label="y=%s" % func)  # type: ignore[union-attr]
        plt.axhline(y=0, color="k", linewidth=0.7)  # type: ignore[union-attr]
        plt.axvline(x=0, color="k", linewidth=0.7)  # type: ignore[union-attr]
        plt.grid(True, alpha=0.25)  # type: ignore[union-attr]
        plt.legend()  # type: ignore[union-attr]
        plt.tight_layout()  # type: ignore[union-attr]
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=120)  # type: ignore[union-attr]
        plt.close()  # type: ignore[union-attr]
        buf.seek(0)
        try:
            buf.name = "plot.png"  # type: ignore[attr-defined]
        except Exception:
            pass
        return buf

    def plot_multi_2d(self, funcs: List[str], x_min: float = -10, x_max: float = 10) -> Optional[BytesIO]:
        if not (MATPLOTLIB_AVAILABLE and NUMPY_AVAILABLE):
            raise RuntimeError("Для графиков нужны зависимости: numpy + matplotlib.")
        x = sp.Symbol("x")  # type: ignore[attr-defined]
        xs = np.linspace(float(x_min), float(x_max), 600)  # type: ignore[union-attr]

        def coerce_1d(vals: Any, expr: Any) -> Any:
            try:
                arr = np.asarray(vals)  # type: ignore[union-attr]
                if arr.shape == ():
                    arr = np.full_like(xs, float(arr))  # type: ignore[union-attr]
                if getattr(arr, "dtype", None) == object:
                    out = []
                    for v in list(arr):
                        try:
                            out.append(float(sp.N(v)))  # type: ignore[attr-defined]
                        except Exception:
                            out.append(float("nan"))
                    arr = np.array(out, dtype=float)  # type: ignore[union-attr]
                if np.iscomplexobj(arr):  # type: ignore[union-attr]
                    imag = np.abs(np.imag(arr))  # type: ignore[union-attr]
                    arr = np.real(arr)  # type: ignore[union-attr]
                    arr = arr.astype(float, copy=False)  # type: ignore[union-attr]
                    arr[imag > 1e-6] = np.nan  # type: ignore[union-attr]
                else:
                    arr = arr.astype(float, copy=False)  # type: ignore[union-attr]
                arr = np.where(np.isfinite(arr), arr, np.nan)  # type: ignore[union-attr]
                return arr
            except Exception:
                out2 = []
                for xv in xs:
                    try:
                        yv = expr.subs(x, float(xv)).evalf()
                        out2.append(float(yv))
                    except Exception:
                        out2.append(float("nan"))
                return np.array(out2, dtype=float)  # type: ignore[union-attr]

        plt.figure(figsize=(10, 6))  # type: ignore[union-attr]
        plotted = 0
        for func in funcs[:6]:
            expr = self.parse(func)
            f = sp.lambdify(x, expr, "numpy")  # type: ignore[attr-defined]
            with np.errstate(all="ignore"):  # type: ignore[union-attr]
                try:
                    ys = f(xs)
                except Exception:
                    ys = None
            ys_arr = coerce_1d(ys, expr)
            if np.all(np.isnan(ys_arr)):  # type: ignore[union-attr]
                continue
            plt.plot(xs, ys_arr, linewidth=2, label="y=%s" % func)  # type: ignore[union-attr]
            plotted += 1

        if plotted == 0:
            try:
                plt.close()  # type: ignore[union-attr]
            except Exception:
                pass
            raise RuntimeError("Не удалось построить ни один график (возможно, ошибки в формулах/ОДЗ).")

        plt.axhline(y=0, color="k", linewidth=0.7)  # type: ignore[union-attr]
        plt.axvline(x=0, color="k", linewidth=0.7)  # type: ignore[union-attr]
        plt.grid(True, alpha=0.25)  # type: ignore[union-attr]
        plt.legend()  # type: ignore[union-attr]
        plt.tight_layout()  # type: ignore[union-attr]
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=120)  # type: ignore[union-attr]
        plt.close()  # type: ignore[union-attr]
        buf.seek(0)
        try:
            buf.name = "plot_multi.png"  # type: ignore[attr-defined]
        except Exception:
            pass
        return buf

    def plot_3d(self, func: str, x_min: float = -5, x_max: float = 5, y_min: float = -5, y_max: float = 5) -> Optional[BytesIO]:
        if not (MATPLOTLIB_AVAILABLE and NUMPY_AVAILABLE):
            raise RuntimeError("Для графиков нужны зависимости: numpy + matplotlib.")
        x, y = sp.symbols("x y")  # type: ignore[attr-defined]
        expr = self.parse(func)
        f = sp.lambdify((x, y), expr, "numpy")  # type: ignore[attr-defined]

        xs = np.linspace(float(x_min), float(x_max), 60)  # type: ignore[union-attr]
        ys = np.linspace(float(y_min), float(y_max), 60)  # type: ignore[union-attr]
        X, Y = np.meshgrid(xs, ys)  # type: ignore[union-attr]

        def coerce_2d(vals: Any) -> Any:
            try:
                arr = np.asarray(vals)  # type: ignore[union-attr]
                if np.iscomplexobj(arr):  # type: ignore[union-attr]
                    imag = np.abs(np.imag(arr))  # type: ignore[union-attr]
                    arr = np.real(arr)  # type: ignore[union-attr]
                    arr = arr.astype(float, copy=False)  # type: ignore[union-attr]
                    arr[imag > 1e-6] = np.nan  # type: ignore[union-attr]
                else:
                    if getattr(arr, "dtype", None) == object:
                        out = np.empty_like(arr, dtype=float)  # type: ignore[union-attr]
                        it = np.nditer(arr, flags=["multi_index", "refs_ok"])  # type: ignore[union-attr]
                        for v in it:
                            try:
                                out[it.multi_index] = float(sp.N(v.item()))  # type: ignore[attr-defined]
                            except Exception:
                                out[it.multi_index] = float("nan")
                        arr = out
                    else:
                        arr = arr.astype(float, copy=False)  # type: ignore[union-attr]
                arr = np.where(np.isfinite(arr), arr, np.nan)  # type: ignore[union-attr]
                return arr
            except Exception:
                # pointwise fallback on smaller grid
                xs2 = np.linspace(float(x_min), float(x_max), 35)  # type: ignore[union-attr]
                ys2 = np.linspace(float(y_min), float(y_max), 35)  # type: ignore[union-attr]
                X2, Y2 = np.meshgrid(xs2, ys2)  # type: ignore[union-attr]
                Z2 = np.empty_like(X2, dtype=float)  # type: ignore[union-attr]
                for i in range(X2.shape[0]):
                    for j in range(X2.shape[1]):
                        try:
                            zv = expr.subs({x: float(X2[i, j]), y: float(Y2[i, j])}).evalf()
                            Z2[i, j] = float(zv)
                        except Exception:
                            Z2[i, j] = float("nan")
                return X2, Y2, Z2

        with np.errstate(all="ignore"):  # type: ignore[union-attr]
            try:
                Z = f(X, Y)
                Zc = coerce_2d(Z)
                Xc, Yc = X, Y
            except Exception:
                Xc, Yc, Zc = coerce_2d(None)

        if isinstance(Zc, tuple):
            # fallback returned triple
            Xc, Yc, Zc = Zc

        if np.all(np.isnan(Zc)):  # type: ignore[union-attr]
            raise RuntimeError("Не удалось вычислить поверхность (возможно, вне области определения).")

        fig = plt.figure(figsize=(11, 7))  # type: ignore[union-attr]
        ax = fig.add_subplot(111, projection="3d")  # type: ignore[attr-defined]
        ax.plot_surface(Xc, Yc, Zc, cmap="viridis", alpha=0.85)
        ax.set_title("z = %s" % func)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_zlabel("z")
        plt.tight_layout()  # type: ignore[union-attr]
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=120)  # type: ignore[union-attr]
        plt.close()  # type: ignore[union-attr]
        buf.seek(0)
        try:
            buf.name = "plot3d.png"  # type: ignore[attr-defined]
        except Exception:
            pass
        return buf


# -------------------- AI Provider --------------------
@dataclass(frozen=True)
class Provider:
    name: str
    kind: str  # openai/deepseek
    base_url: str
    api_key: str
    model: str
    priority: int


class AIProvider:
    def __init__(self) -> None:
        self.offline = OFFLINE_MODE
        self.providers: List[Provider] = []
        if DEEPSEEK_API_KEY:
            self.providers.append(Provider("DeepSeek", "deepseek", DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, 1))
        if OPENAI_API_KEY:
            self.providers.append(Provider("OpenAI", "openai", OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, 2))
        self.providers.sort(key=lambda p: p.priority)

    def ask(self, prompt: str) -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return "Пустой вопрос. Напишите, что нужно решить/объяснить."
        if self.offline or not self.providers:
            return self._local(prompt)

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": "Ты — преподаватель математики. Отвечай на русском, структурированно: шаги решения и ответ. Не выдумывай факты.",
            },
            {"role": "user", "content": prompt},
        ]

        errors: List[str] = []
        for p in self.providers:
            out, err = self._call(p, messages)
            if out and len(out.strip()) > 5:
                return out.strip()
            if err:
                errors.append("%s: %s" % (p.name, err))

        base = self._local(prompt)
        if errors:
            base += "\n\n❌ AI не ответил:\n" + "\n".join(["• %s" % e for e in errors[:3]])

        # Подсказка для частой проблемы на macOS: LibreSSL + urllib3 v2
        try:
            import ssl as _ssl
            import urllib3 as _urllib3  # type: ignore

            if str(getattr(_urllib3, "__version__", "")).startswith("2") and "LibreSSL" in str(getattr(_ssl, "OPENSSL_VERSION", "")):
                base += "\n\n⚠️ Похоже, у вас LibreSSL и urllib3 v2. Часто помогает: pip install \"urllib3<2\"."
        except Exception:
            pass

        return base

    def _call(self, p: Provider, messages: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
        url = "%s/v1/chat/completions" % p.base_url
        headers = {"Authorization": "Bearer %s" % p.api_key, "Content-Type": "application/json"}
        payload = {"model": p.model, "messages": messages, "temperature": 0.4, "max_tokens": 900}
        if p.kind == "deepseek":
            payload["stream"] = False
        last_err: Optional[str] = None
        for attempt in range(2):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=(12, 60))
                if r.status_code != 200:
                    if r.status_code in (401, 403):
                        last_err = "доступ запрещён (проверьте API‑ключ)"
                    elif r.status_code == 429:
                        last_err = "слишком много запросов (429)"
                    else:
                        last_err = "HTTP %d" % int(r.status_code)
                    # retry once for 429/5xx
                    if attempt == 0 and r.status_code in (429, 500, 502, 503, 504):
                        time.sleep(1.2)
                        continue
                    return None, last_err

                try:
                    data = r.json()
                except Exception:
                    return None, "не удалось разобрать ответ (JSON)"

                try:
                    content = data["choices"][0]["message"]["content"]
                    return content, None
                except Exception:
                    return None, "неожиданный формат ответа"

            except requests.exceptions.SSLError:
                last_err = "ошибка SSL"
            except requests.exceptions.Timeout:
                last_err = "таймаут сети"
            except requests.exceptions.ConnectionError:
                last_err = "ошибка соединения"
            except requests.exceptions.RequestException:
                last_err = "ошибка запроса"

            if attempt == 0:
                time.sleep(1.0)

        return None, last_err or "неизвестная ошибка"

    def _local(self, prompt: str) -> str:
        pl = prompt.lower()
        if "производн" in pl:
            return "Производная: (x^n)'=n·x^(n-1), (sin x)'=cos x, (ln x)'=1/x. Пришли функцию — посчитаю."
        if "интеграл" in pl:
            return "Интеграл: ∫x^n dx = x^(n+1)/(n+1)+C; ∫sin x dx=-cos x + C. Пришли функцию — посчитаю."
        if "пифагор" in pl:
            return "Пифагор: c²=a²+b² (c — гипотенуза)."
        return "AI сейчас недоступен. Могу решить уравнение/производную/интеграл через меню или просто пришли пример."


# -------------------- OCR --------------------
@dataclass(frozen=True)
class OCRResult:
    ok: bool
    text: str
    engine: str


class OCR:
    def __init__(self) -> None:
        self._easy_reader = None
        self._tesseract_ready = False
        if PYTESS_AVAILABLE:
            try:
                # Проверяем, что бинарник tesseract реально доступен.
                pytesseract.get_tesseract_version()  # type: ignore[union-attr]
                self._tesseract_ready = True
            except Exception:
                self._tesseract_ready = False

    def available(self) -> bool:
        return PIL_AVAILABLE and (EASYOCR_AVAILABLE or self._tesseract_ready)

    def extract(self, image_bytes: bytes, handwritten: bool = False) -> OCRResult:
        if not PIL_AVAILABLE:
            return OCRResult(False, "pillow не установлен.", "none")
        img = self._preprocess(image_bytes, handwritten=handwritten)
        if img is None:
            return OCRResult(False, "Не удалось обработать изображение.", "none")

        # prefer easyocr for handwritten
        if EASYOCR_AVAILABLE and (handwritten or not PYTESS_AVAILABLE):
            txt = self._easyocr(img)
            if txt:
                return OCRResult(True, self._clean(txt), "easyocr")

        if self._tesseract_ready:
            txt = self._tesseract(img)
            if txt:
                return OCRResult(True, self._clean(txt), "tesseract")

        if EASYOCR_AVAILABLE:
            txt = self._easyocr(img)
            if txt:
                return OCRResult(True, self._clean(txt), "easyocr")

        if PYTESS_AVAILABLE and not self._tesseract_ready:
            return OCRResult(
                False,
                "pytesseract установлен, но tesseract не найден. Установите tesseract (macOS: brew install tesseract).",
                "none",
            )
        return OCRResult(False, "OCR не настроен (установите easyocr или pytesseract + tesseract).", "none")

    def _preprocess(self, image_bytes: bytes, handwritten: bool) -> Optional[Any]:
        try:
            img = Image.open(BytesIO(image_bytes))  # type: ignore[union-attr]
            img = img.convert("L")
            enhancer = ImageEnhance.Contrast(img)  # type: ignore[union-attr]
            img = enhancer.enhance(2.0 if handwritten else 1.6)
            img = img.filter(ImageFilter.SHARPEN)  # type: ignore[union-attr]
            threshold = 170 if handwritten else 185
            img = img.point(lambda x: 0 if x < threshold else 255, mode="1")
            return img
        except Exception:
            return None

    def _easyocr(self, img: Any) -> Optional[str]:
        try:
            if self._easy_reader is None:
                self._easy_reader = easyocr.Reader(["ru", "en"], gpu=False)  # type: ignore[union-attr]
            import numpy as _np  # local import

            arr = _np.array(img)
            parts = self._easy_reader.readtext(arr, detail=0, paragraph=True)
            if not parts:
                return None
            return " ".join([str(p).strip() for p in parts if str(p).strip()])
        except Exception:
            return None

    def _tesseract(self, img: Any) -> Optional[str]:
        try:
            txt = pytesseract.image_to_string(img, config="--oem 3 --psm 6 -l rus+eng")  # type: ignore[union-attr]
            txt = (txt or "").strip()
            return txt or None
        except Exception:
            return None

    def _clean(self, text: str) -> str:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        t = " ".join(lines)
        rep = {
            "—": "-",
            "–": "-",
            "−": "-",
            "×": "*",
            "÷": "/",
            "∙": "*",
            "х": "x",
            "Х": "x",
            "у": "y",
            "У": "y",
            "π": "pi",
            "∞": "oo",
            ",": ".",
        }
        for a, b in rep.items():
            t = t.replace(a, b)
        # Частые OCR-подмены в числах: O/о -> 0, l/I -> 1 (только рядом с цифрами)
        t = re.sub(r"(?<=\d)[OoОо](?=\d)", "0", t)
        t = re.sub(r"(?<=\d)[lIІі](?=\d)", "1", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t


# -------------------- Practice session store --------------------
@dataclass
class PracticeTask:
    prompt: str
    options: List[str]
    correct_index: int
    answer_text: str
    explanation: str


@dataclass
class PracticeSession:
    session_id: str
    tg_id: int
    skill_id: str
    exam: str
    task_num: int
    title: str
    tasks: List[PracticeTask]
    index: int = 0
    correct: int = 0
    finished: bool = False

    def current(self) -> Optional[PracticeTask]:
        if self.finished or self.index >= len(self.tasks):
            return None
        return self.tasks[self.index]

    def advance(self) -> None:
        self.index += 1
        if self.index >= len(self.tasks):
            self.finished = True


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[int, PracticeSession] = {}

    def set(self, tg_id: int, session: PracticeSession) -> None:
        with self._lock:
            self._sessions[tg_id] = session

    def get(self, tg_id: int) -> Optional[PracticeSession]:
        with self._lock:
            return self._sessions.get(tg_id)

    def clear(self, tg_id: int) -> None:
        with self._lock:
            self._sessions.pop(tg_id, None)


def new_session_id() -> str:
    # short callback-friendly
    return ("%06x" % random.randint(0, 0xFFFFFF))


# -------------------- Task generators (OGE/EGE) --------------------
def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a)


def _fmt_frac(num: int, den: int) -> str:
    if den == 0:
        return "∞"
    if num % den == 0:
        return str(num // den)
    if den < 0:
        num, den = -num, -den
    g = _gcd(abs(num), abs(den))
    num //= g
    den //= g
    return "%d/%d" % (num, den)


def gen_task_for_skill(rng: random.Random, exam: str, task_num: int, topic: str = "Смешанное", difficulty: int = 1) -> PracticeTask:
    """
    Генератор заданий для тренировки (multiple choice).
    Делаем оригинальные задачи по навыкам ОГЭ/ЕГЭ, от простых к сложным.
    """
    try:
        difficulty = max(1, min(5, int(difficulty or 1)))
    except Exception:
        difficulty = 1
    topic = (topic or "Смешанное").strip()

    def _pick_options(correct: str, wrong: List[str]) -> Tuple[List[str], int]:
        ws: List[str] = []
        for w in [correct] + wrong:
            w = str(w)
            if w not in ws:
                ws.append(w)
        # ensure 4 options
        while len(ws) < 4:
            cand = str(int(rng.randint(-20, 60)))
            if cand not in ws:
                ws.append(cand)
        opts = ws[:4]
        rng.shuffle(opts)
        return opts, opts.index(correct)

    def _frac_task() -> PracticeTask:
        den1 = rng.choice([2, 3, 4, 5, 6, 8, 10, 12, 15])
        den2 = rng.choice([2, 3, 4, 5, 6, 8, 10, 12, 15])
        num1 = rng.randint(1, den1 - 1)
        num2 = rng.randint(1, den2 - 1)
        op = rng.choice(["+", "-"] if difficulty <= 2 else ["+", "-", "*", "/"])
        if op == "+":
            num = num1 * den2 + num2 * den1
            den = den1 * den2
        elif op == "-":
            num = num1 * den2 - num2 * den1
            den = den1 * den2
        elif op == "*":
            num = num1 * num2
            den = den1 * den2
        else:
            # division
            num = num1 * den2
            den = den1 * num2
        correct = _fmt_frac(num, den)
        wrong = [
            _fmt_frac(num1 + num2, den1 + den2),
            _fmt_frac(num + 1, den),
            _fmt_frac(num - 1, den),
            str(num),
        ]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(
            prompt="Вычислите: <code>%d/%d %s %d/%d</code>" % (num1, den1, op, num2, den2),
            options=opts,
            correct_index=idx,
            answer_text=correct,
            explanation="Работаем с дробями: общий знаменатель (или умножение/деление) и сокращение.",
        )

    def _percent_task() -> PracticeTask:
        base = rng.randrange(50, 2001, 10 if difficulty <= 2 else 5)
        pct = rng.choice([5, 10, 12, 15, 20, 25, 30, 40, 50])
        kind = rng.choice(["find", "increase", "decrease"] if difficulty <= 3 else ["find", "increase", "decrease", "reverse"])
        if kind == "find":
            val = base * pct / 100.0
            prompt = "Найдите <b>%d%%</b> от числа <b>%d</b>." % (pct, base)
            expl = "%d%% = %d/100. Умножаем: %d·%d/100." % (pct, pct, base, pct)
        elif kind == "increase":
            val = base * (1 + pct / 100.0)
            prompt = "Увеличьте число <b>%d</b> на <b>%d%%</b>." % (base, pct)
            expl = "%d·(1+%d/100)." % (base, pct)
        elif kind == "decrease":
            val = base * (1 - pct / 100.0)
            prompt = "Уменьшите число <b>%d</b> на <b>%d%%</b>." % (base, pct)
            expl = "%d·(1-%d/100)." % (base, pct)
        else:
            # reverse: final after change -> original
            base0 = base
            final = int(round(base0 * (1 + pct / 100.0)))
            val = base0
            prompt = "После увеличения на <b>%d%%</b> число стало <b>%d</b>. Найдите исходное число." % (pct, final)
            expl = "Исходное x: x·(1+%d/100)=%d → x=%d/(1+%d/100)." % (pct, final, final, pct)
        correct = str(int(val) if float(val).is_integer() else round(val, 2)).rstrip("0").rstrip(".")
        wrong = [str(base + pct), str(base - pct), str(int(float(correct)) + 10), str(int(float(correct)) - 10)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation=expl)

    def _linear_eq_task() -> PracticeTask:
        if difficulty <= 2:
            x0 = rng.randint(-9, 9)
            a = rng.choice([i for i in range(-8, 9) if i not in (0, 1, -1)])
            b = rng.randint(-20, 20)
            c = a * x0 + b
            prompt = "Решите: <code>%dx + (%d) = %d</code>" % (a, b, c)
            correct = str(x0)
            wrong = [str(x0 + 1), str(x0 - 1), str(-x0), str(x0 * 2)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Переносим свободный член и делим на коэффициент при x.")

        # equation with fractions / parentheses
        x0 = rng.randint(-8, 8)
        p = rng.choice([2, 3, 4, 5, 6])
        q = rng.randint(-10, 10)
        r = rng.randint(-10, 10)
        # (x+q)/p = r  => x = pr - q
        left = " (x+%d)/%d " % (q, p)
        prompt = "Решите: <code>(x+%d)/%d = %d</code>" % (q, p, r)
        correct = str(p * r - q)
        wrong = [str(p * r + q), str(r - q), str(p * r), str(-int(correct))]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Умножаем обе части на знаменатель и переносим.")

    def _quadratic_task() -> PracticeTask:
        r1 = rng.choice([i for i in range(-7, 8) if i not in (0,)])
        r2 = rng.choice([i for i in range(-7, 8) if i not in (0, r1)])
        a = 1 if difficulty <= 3 else rng.choice([1, 2, 3])
        b = -a * (r1 + r2)
        c = a * r1 * r2
        ask = rng.choice(["minroot", "sum", "prod"] if difficulty >= 4 else ["minroot"])
        if ask == "sum":
            prompt = "Для уравнения <code>%dx^2 + (%d)x + (%d)=0</code> найдите сумму корней." % (a, b, c)
            correct = str(r1 + r2)
            expl = "По Виету: x1+x2 = -b/a."
        elif ask == "prod":
            prompt = "Для уравнения <code>%dx^2 + (%d)x + (%d)=0</code> найдите произведение корней." % (a, b, c)
            correct = str(r1 * r2)
            expl = "По Виету: x1·x2 = c/a."
        else:
            prompt = "Решите: <code>%dx^2 + (%d)x + (%d) = 0</code>. Найдите меньший корень." % (a, b, c)
            correct = str(min(r1, r2))
            expl = "Можно разложить на множители или использовать Виета."
        wrong = [str(max(r1, r2)), str(r1 + r2), str(r1 * r2), str(int(correct) + 1)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation=expl)

    def _system_task() -> PracticeTask:
        # 2x2 linear system with integer solution
        x0 = rng.randint(-6, 6)
        y0 = rng.randint(-6, 6)
        a1, b1 = rng.choice([(1, 2), (2, 1), (1, -1), (2, -1), (3, 1)])
        a2, b2 = rng.choice([(1, 1), (2, 3), (3, 2), (1, -2), (-1, 2)])
        # ensure non-zero determinant
        if a1 * b2 - a2 * b1 == 0:
            a2, b2 = 2, -1
        c1 = a1 * x0 + b1 * y0
        c2 = a2 * x0 + b2 * y0
        ask = rng.choice(["x", "y", "sum"] if difficulty >= 4 else ["x", "sum"])
        if ask == "y":
            prompt = "Решите систему и найдите y:\n<code>%dx + %dy = %d</code>\n<code>%dx + %dy = %d</code>" % (a1, b1, c1, a2, b2, c2)
            correct = str(y0)
        elif ask == "x":
            prompt = "Решите систему и найдите x:\n<code>%dx + %dy = %d</code>\n<code>%dx + %dy = %d</code>" % (a1, b1, c1, a2, b2, c2)
            correct = str(x0)
        else:
            prompt = "Решите систему и найдите x+y:\n<code>%dx + %dy = %d</code>\n<code>%dx + %dy = %d</code>" % (a1, b1, c1, a2, b2, c2)
            correct = str(x0 + y0)
        wrong = [str(x0 - y0), str(y0 - x0), str(x0), str(y0)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Используйте подстановку или сложение (метод Гаусса).")

    def _inequality_task() -> PracticeTask:
        x0 = rng.randint(-5, 6)
        a = rng.choice([2, 3, 4, -2, -3])
        b = rng.randint(-10, 10)
        # choose inequality so that x0 is smallest integer solution for a*x + b > c
        c = a * x0 + b - 1
        prompt = "Найдите наименьшее целое x, при котором <code>%dx + (%d) &gt; %d</code>" % (a, b, c)
        correct = str(x0)
        wrong = [str(x0 - 1), str(x0 + 1), str(-x0), "0"]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Решаем неравенство и выбираем минимальное целое решение.")

    def _func_task() -> PracticeTask:
        if difficulty <= 2:
            k = rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])
            b = rng.randint(-8, 8)
            x = rng.randint(-3, 4)
            y = k * x + b
            prompt = "Для функции <code>y=%dx+(%d)</code> найдите y при x=%d." % (k, b, x)
            correct = str(y)
            wrong = [str(y + 1), str(y - 1), str(-y), str(k + b)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Подставляем x в формулу y=kx+b.")
        # slope from two points
        x1 = rng.randint(-3, 2)
        x2 = x1 + rng.randint(1, 4)
        k = rng.choice([-3, -2, -1, 1, 2, 3])
        b = rng.randint(-5, 5)
        y1 = k * x1 + b
        y2 = k * x2 + b
        prompt = "Через точки (%d,%d) и (%d,%d) проходит прямая. Найдите её угловой коэффициент k." % (x1, y1, x2, y2)
        correct = str(k)
        wrong = [str(-k), str(k + 1), str(k - 1), str(b)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="k=(y2-y1)/(x2-x1).")

    def _progression_task() -> PracticeTask:
        a1 = rng.randint(-10, 10)
        d = rng.choice([1, 2, 3, -1, -2])
        n = rng.randint(5, 20)
        an = a1 + (n - 1) * d
        ask_sum = difficulty >= 4 and rng.random() < 0.5
        if ask_sum:
            sn = n * (2 * a1 + (n - 1) * d) // 2 if (n * (2 * a1 + (n - 1) * d)) % 2 == 0 else n * (2 * a1 + (n - 1) * d) / 2
            prompt = "Арифм. прогрессия: a1=%d, d=%d. Найдите S%d." % (a1, d, n)
            correct = str(int(sn) if float(sn).is_integer() else sn)
            expl = "S_n = n/2·(2a1+(n-1)d)."
        else:
            prompt = "Арифм. прогрессия: a1=%d, d=%d. Найдите a%d." % (a1, d, n)
            correct = str(an)
            expl = "a_n = a1 + (n-1)d."
        wrong = [str(an + d), str(an - d), str(a1 + d), str(-an)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation=expl)

    def _stats_task() -> PracticeTask:
        arr = [rng.randint(0, 20) for _ in range(rng.choice([5, 5, 7, 9]))]
        if difficulty <= 2 or rng.random() < 0.5:
            s = sum(arr)
            mean = s / len(arr)
            correct = str(int(mean) if float(mean).is_integer() else round(mean, 2)).rstrip("0").rstrip(".")
            prompt = "Найдите среднее арифметическое чисел: %s" % (", ".join(map(str, arr)))
            expl = "Сумма делится на количество."
        else:
            brr = sorted(arr)
            mid = len(brr) // 2
            med = brr[mid]
            correct = str(med)
            prompt = "Найдите медиану набора: %s" % (", ".join(map(str, arr)))
            expl = "Отсортируйте и возьмите средний элемент."
        wrong = [str(int(correct) + 1), str(int(correct) - 1), str(arr[0]), str(arr[-1])]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation=expl)

    def _geom_task() -> PracticeTask:
        kind = rng.choice(["pif", "area_tr", "circle"] if difficulty <= 3 else ["pif", "area_tr", "circle", "similar"])
        if kind == "pif":
            a, b, c = rng.choice([(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17)])
            prompt = "В прямоугольном треугольнике катеты %d и %d. Найдите гипотенузу." % (a, b)
            correct = str(c)
            wrong = [str(a + b), str(abs(a - b)), str(c + 1), str(c - 1)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="По Пифагору: c=√(a²+b²).")
        if kind == "area_tr":
            a = rng.randint(4, 20)
            h = rng.randint(3, 15)
            s = a * h / 2
            correct = str(int(s) if float(s).is_integer() else s)
            wrong = [str(a * h), str(a + h), str(int(float(correct)) + 1), str(int(float(correct)) - 1)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt="Найдите площадь треугольника: основание %d, высота %d." % (a, h), options=opts, correct_index=idx, answer_text=correct, explanation="S=1/2·a·h.")
        if kind == "circle":
            r = rng.randint(2, 10)
            correct = "%d*pi" % (r * r)
            wrong = ["%d*pi" % (2 * r), "%d*pi" % (r), "%d*pi" % (r * r + 1), "%d*pi" % (r * r - 1)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt="Найдите площадь круга радиуса %d (в виде k*pi)." % r, options=opts, correct_index=idx, answer_text=correct, explanation="S=πr².")
        # similar triangles ratio
        k = rng.choice([2, 3, 4, 5])
        a = rng.randint(3, 12)
        b = a * k
        prompt = "Два подобных треугольника. Если сторона первого %d, соответствующая сторона второго %d, найдите коэффициент подобия." % (a, b)
        correct = str(k)
        wrong = [str(1 / k), str(k + 1), str(k - 1), "1"]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="k = b/a.")

    def _trig_task() -> PracticeTask:
        angles = [
            ("0", "0", "1"),
            ("pi/6", "1/2", "sqrt(3)/2"),
            ("pi/4", "sqrt(2)/2", "sqrt(2)/2"),
            ("pi/3", "sqrt(3)/2", "1/2"),
            ("pi/2", "1", "0"),
        ]
        ang, sinv, cosv = rng.choice(angles)
        kind = rng.choice(["sin", "cos"] if difficulty <= 3 else ["sin", "cos", "id"])
        if kind == "id":
            prompt = "Упростите: <code>sin(x)^2 + cos(x)^2</code>"
            correct = "1"
            wrong = ["0", "sin(x)", "cos(x)"]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Основное тождество: sin²x+cos²x=1.")
        if kind == "sin":
            prompt = "Найдите <code>sin(%s)</code>" % ang
            correct = sinv
            wrong = [cosv, "0", "1", "-1/2"]
        else:
            prompt = "Найдите <code>cos(%s)</code>" % ang
            correct = cosv
            wrong = [sinv, "0", "1", "-1/2"]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Используйте таблицу значений для стандартных углов.")

    def _prob_task() -> PracticeTask:
        kind = rng.choice(["dice", "coin"] if difficulty <= 3 else ["dice", "coin", "comb"])
        if kind == "dice":
            target = rng.randint(1, 6)
            prompt = "Кубик бросили один раз. Найдите вероятность выпадения %d." % target
            correct = "1/6"
            wrong = ["1/3", "1/2", "1"]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="6 равновероятных исходов.")
        if kind == "coin":
            n = rng.choice([2, 3, 4, 5] if difficulty >= 4 else [2, 3, 4])
            k = rng.randint(0, n)
            comb = math.comb(n, k)
            den = 2 ** n
            correct = _fmt_frac(comb, den)
            wrong = [_fmt_frac(k, n) if n else "0", _fmt_frac(comb + 1, den), _fmt_frac(comb, den // 2 if den > 1 else den), "0"]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(
                prompt="Монету подбросили %d раза. P(орёл ровно %d раз)?" % (n, k),
                options=opts,
                correct_index=idx,
                answer_text=correct,
                explanation="Всего исходов 2^n, благоприятных C(n,k).",
            )
        # combinatorics count
        n = rng.randint(5, 10)
        k = rng.randint(2, min(5, n - 1))
        correct = str(math.comb(n, k))
        wrong = [str(n ** k), str(math.perm(n, k) if hasattr(math, "perm") else math.factorial(n) // math.factorial(n - k)), str(int(correct) + 1)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt="Сколькими способами можно выбрать %d учеников из %d?" % (k, n), options=opts, correct_index=idx, answer_text=correct, explanation="Это сочетания: C(n,k).")

    def _comb_task() -> PracticeTask:
        kind = rng.choice(["perm", "comb", "arr"])
        if kind == "perm":
            n = rng.randint(4, 8)
            correct = str(math.factorial(n))
            wrong = [str(math.factorial(n - 1)), str(n * (n - 1)), str(int(correct) + 1)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt="Сколько перестановок из %d элементов?" % n, options=opts, correct_index=idx, answer_text=correct, explanation="Перестановки: n!.")  # type: ignore[return-value]
        if kind == "comb":
            n = rng.randint(6, 12)
            k = rng.randint(2, 5)
            correct = str(math.comb(n, k))
            wrong = [str(n * k), str(n + k), str(int(correct) + 1)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt="Вычислите C(%d,%d)." % (n, k), options=opts, correct_index=idx, answer_text=correct, explanation="C(n,k)=n!/(k!(n-k)!).")
        n = rng.randint(6, 12)
        k = rng.randint(2, 5)
        correct = str(math.factorial(n) // math.factorial(n - k))
        wrong = [str(math.comb(n, k)), str(n ** k), str(int(correct) + 1)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt="Вычислите A(%d,%d)." % (n, k), options=opts, correct_index=idx, answer_text=correct, explanation="A(n,k)=n!/(n-k)!.")

    def _abs_task() -> PracticeTask:
        a = rng.randint(-6, 6)
        b = rng.randint(1, 9)
        x1 = a - b
        x2 = a + b
        prompt = "Решите: <code>|x-(%d)| = %d</code>. Найдите меньший корень." % (a, b)
        correct = str(min(x1, x2))
        wrong = [str(max(x1, x2)), str(a), str(b), str(int(correct) + 1)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="|x-a|=b → x=a±b.")

    def _log_task() -> PracticeTask:
        # log2(x-a)=k
        a = rng.randint(0, 5)
        k = rng.randint(1, 5)
        x = a + (2 ** k)
        prompt = "Решите: <code>log(x-%d, 2) = %d</code>." % (a, k)
        correct = str(x)
        wrong = [str(a + k), str(2 ** k), str(x + 1), str(x - 1)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="log_2(x-a)=k → x-a=2^k → x=a+2^k.")

    def _analysis_task() -> PracticeTask:
        # derivative at point or simple integral
        if rng.random() < 0.6:
            a = rng.randint(1, 5)
            b = rng.randint(-5, 6)
            c = rng.randint(-5, 6)
            x0 = rng.randint(-2, 3)
            # f = ax^3 + bx^2 + cx
            val = 3 * a * x0 * x0 + 2 * b * x0 + c
            prompt = "Найдите f'(x) в точке x=%d, если f(x)=%dx^3+%dx^2+(%d)x" % (x0, a, b, c)
            correct = str(val)
            wrong = [str(val + 1), str(val - 1), str(-val), "0"]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="f'(x)=3ax²+2bx+c.")
        m = rng.randint(2, 5)
        n = rng.randint(0, 6)
        # ∫ m*x^n dx = m*x^(n+1)/(n+1)
        num = m
        den = n + 1
        coeff = _fmt_frac(num, den)
        correct = "%s*x^%d + C" % (coeff, n + 1)
        wrong = ["%s*x^%d" % (coeff, n + 1), "%d*x^%d + C" % (m, n), "x^%d + C" % (n + 1)]
        opts, idx = _pick_options(correct, wrong)
        return PracticeTask(prompt="Найдите ∫ <code>%d*x^%d</code> dx." % (m, n), options=opts, correct_index=idx, answer_text=correct, explanation="∫x^n dx = x^(n+1)/(n+1) + C.")

    # ---- exam/task routing ----
    if exam == "oge":
        if task_num == 1:
            return _frac_task()
        if task_num == 2:
            return _percent_task()
        if task_num == 3:
            return _linear_eq_task()
        if task_num == 4:
            return _quadratic_task()
        if task_num == 5:
            return _system_task() if difficulty >= 3 else _inequality_task()
        if task_num == 6:
            return _func_task()
        if task_num == 7:
            # text tasks: speed/work/simple percent
            if rng.random() < 0.5:
                v = rng.randint(30, 90)
                t = rng.choice([1, 2, 3, 4])
                s = v * t
                prompt = "Автомобиль ехал %d ч со скоростью %d км/ч. Сколько км проехал?" % (t, v)
                correct = str(s)
                wrong = [str(s + v), str(s - v), str(v), str(t)]
                opts, idx = _pick_options(correct, wrong)
                return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="s=v·t.")
            # work
            a = rng.choice([2, 3, 4, 5, 6])
            b = rng.choice([3, 4, 6, 8, 9, 12])
            # together time = 1/(1/a+1/b)
            t = 1.0 / (1.0 / a + 1.0 / b)
            correct = str(int(t) if float(t).is_integer() else round(t, 2)).rstrip("0").rstrip(".")
            wrong = [str(a), str(b), str(int(float(correct)) + 1), str(int(float(correct)) - 1)]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt="Один рабочий делает работу за %d ч, другой за %d ч. За сколько часов сделают вместе?" % (a, b), options=opts, correct_index=idx, answer_text=correct, explanation="Складываем производительности: 1/a+1/b.")
        if task_num == 8:
            return _progression_task()
        if task_num == 9:
            return _stats_task()
        if task_num == 10:
            return _prob_task()
        if task_num in (11, 12, 13, 14):
            return _geom_task()
        if task_num == 15:
            return _trig_task()
        if task_num == 16:
            return _comb_task()
        if task_num == 17:
            # algebraic fractions / simplify
            a = rng.randint(2, 8)
            b = rng.randint(1, 6)
            prompt = "Упростите: <code>(%dx)/(%dx)</code>" % (a * b, a)
            correct = str(b)
            wrong = [str(a), str(a * b), "1"]
            opts, idx = _pick_options(correct, wrong)
            return PracticeTask(prompt=prompt, options=opts, correct_index=idx, answer_text=correct, explanation="Сокращаем общий множитель в числителе и знаменателе.")
        if task_num == 18:
            return _abs_task()
        # 19-20 mixed
        topic = rng.choice(["Алгебра", "Функции", "Геометрия", "Тригонометрия", "Вероятность", "Статистика", "Текстовые", "Комбинаторика"])
        return gen_task_for_skill(rng, exam, 0, topic=topic, difficulty=difficulty)

    if exam == "ege_base":
        # use topic mostly
        if topic == "Алгебра":
            return rng.choice([_frac_task, _percent_task, _linear_eq_task, _quadratic_task, _inequality_task])()
        if topic == "Функции":
            return _func_task()
        if topic == "Геометрия":
            return _geom_task()
        if topic == "Тригонометрия":
            return _trig_task()
        if topic == "Вероятность":
            return _prob_task()
        if topic == "Статистика":
            return _stats_task()
        if topic == "Текстовые":
            return gen_task_for_skill(rng, "oge", 7, topic=topic, difficulty=difficulty)
        if topic == "Комбинаторика":
            return _comb_task()
        return rng.choice([_frac_task, _percent_task, _func_task, _geom_task, _prob_task, _stats_task])()

    if exam == "ege_prof":
        if task_num in (7, 8):
            # keep strong analysis tasks
            if task_num == 8:
                # min/max quadratic on segment
                a = rng.choice([-2, -1, 1, 2])
                b = rng.randint(-8, 8)
                c = rng.randint(-10, 10)
                left = rng.randint(-3, 0)
                right = rng.randint(1, 4)
                x0 = -b / (2.0 * a)
                cand = [left, right]
                if left <= x0 <= right:
                    cand.append(x0)
                vals = [(x, a * x * x + b * x + c) for x in cand]
                fbest = max(vals, key=lambda t: t[1])[1]
                correct = str(int(fbest) if float(fbest).is_integer() else round(fbest, 3))
                wrong = [str(int(float(correct)) + 1), str(int(float(correct)) - 1), "0", str(int(float(correct)) + 2)]
                opts, idx = _pick_options(correct, wrong)
                return PracticeTask(prompt="Найдите наибольшее значение f(x)=%dx^2+(%d)x+(%d) на [%d;%d]" % (a, b, c, left, right), options=opts, correct_index=idx, answer_text=correct, explanation="Проверяем концы и вершину, если она внутри.")
            return _analysis_task()
        if task_num in (2, 9):
            return _trig_task()
        if task_num in (10,):
            return _log_task()
        if task_num in (14,):
            return _comb_task()
        if topic == "Анализ":
            return _analysis_task()
        if topic == "Алгебра":
            return rng.choice([_linear_eq_task, _quadratic_task, _inequality_task, _log_task])()
        if topic == "Геометрия":
            return _geom_task()
        if topic == "Функции":
            return _func_task()
        if topic == "Вероятность":
            return _prob_task()
        if topic == "Комбинаторика":
            return _comb_task()
        if topic == "Текстовые":
            return gen_task_for_skill(rng, "oge", 7, topic=topic, difficulty=difficulty)
        return rng.choice([_analysis_task, _geom_task, _prob_task, _func_task, _log_task])()

    # default mixed (school)
    pick = {
        "Алгебра": [_frac_task, _linear_eq_task, _quadratic_task],
        "Функции": [_func_task],
        "Геометрия": [_geom_task],
        "Тригонометрия": [_trig_task],
        "Вероятность": [_prob_task],
        "Анализ": [_analysis_task],
        "Статистика": [_stats_task],
        "Текстовые": [lambda: gen_task_for_skill(rng, "oge", 7, topic="Текстовые", difficulty=difficulty)],
        "Комбинаторика": [_comb_task],
        "Смешанное": [_frac_task, _percent_task, _func_task, _geom_task, _prob_task, _stats_task],
    }
    return rng.choice(pick.get(topic, pick["Смешанное"]))()


# -------------------- Telegram Bot --------------------
if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не задан.")

db = DB(DB_PATH)
db.init()

# Seed lessons/skills (idempotent upsert)
for i, lesson in enumerate(build_micro_lessons(), start=1):
    db.upsert_lesson(lesson)
for skill in build_skills_registry():
    db.upsert_skill(skill)

engine = MathEngine() if SYMPY_AVAILABLE else None
ai = AIProvider()
ocr = OCR()
sessions = SessionStore()

def _configure_telegram_http() -> None:
    # Network tuning for Telegram API (reduces timeout errors)
    try:
        apihelper.RETRY_ON_ERROR = True
        apihelper.MAX_RETRIES = 20
        apihelper.CONNECT_TIMEOUT = 30
        apihelper.READ_TIMEOUT = 240
    except Exception:
        pass

    # requests.Session with retries/backoff
    if not _RETRY_AVAILABLE:
        return
    try:
        s = requests.Session()
        retry_kwargs = dict(
            total=10,
            connect=10,
            read=10,
            status=10,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            raise_on_status=False,
        )
        try:
            retry = Retry(**retry_kwargs, allowed_methods=frozenset(["GET", "POST"]))  # type: ignore[misc]
        except TypeError:
            retry = Retry(**retry_kwargs, method_whitelist=frozenset(["GET", "POST"]))  # type: ignore[misc]
        adapter = HTTPAdapter(max_retries=retry)  # type: ignore[misc]
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        apihelper.SESSION = s
    except Exception:
        pass


def _patch_bot_api(b: telebot.TeleBot) -> None:
    """
    Telebot выбрасывает requests.exceptions.ReadTimeout в хэндлерах.
    Это может «ронять» polling. Патчим ключевые методы, чтобы делать ретраи
    и не падать из‑за сетевых проблем.
    """

    def _safe_call(fn, *args, **kwargs):
        fn_name = getattr(fn, "__name__", "api_call")
        for attempt in range(5):
            try:
                return fn(*args, **kwargs)
            except requests.exceptions.ReadTimeout:
                if attempt >= 4:
                    print("⚠️ telegram timeout:", fn_name)
                    return None
                time.sleep(1.0 + 0.8 * attempt)
            except requests.exceptions.ConnectionError:
                if attempt >= 4:
                    print("⚠️ telegram connection error:", fn_name)
                    return None
                time.sleep(1.0 + 0.8 * attempt)
            except requests.exceptions.RequestException:
                if attempt >= 4:
                    print("⚠️ telegram request error:", fn_name)
                    return None
                time.sleep(1.0 + 0.8 * attempt)
            except apihelper.ApiTelegramException as e:  # type: ignore[attr-defined]
                msg = str(e).lower()
                if "too many requests" in msg or "429" in msg:
                    wait_s = 3
                    try:
                        wait_s = int(getattr(e, "result_json", {}).get("parameters", {}).get("retry_after", wait_s))
                    except Exception:
                        pass
                    time.sleep(wait_s + 1)
                    continue
                if "message is not modified" in msg or "query is too old" in msg:
                    return None
                if "can't parse" in msg or "unsupported start tag" in msg or "can't parse entities" in msg:
                    # fallback: try without parse_mode
                    try:
                        kw2 = dict(kwargs)
                        kw2.pop("parse_mode", None)
                        return fn(*args, **kw2)
                    except Exception:
                        pass
                print("⚠️ telegram api error:", fn_name, str(e))
                return None
            except Exception:
                print("⚠️ telegram unknown error:", fn_name)
                return None
        return None

    # Monkeypatch a few frequently failing API calls
    _send_message = b.send_message
    _send_photo = b.send_photo
    _edit_text = b.edit_message_text
    _answer_cb = b.answer_callback_query
    _delete_msg = getattr(b, "delete_message", None)
    _chat_action = getattr(b, "send_chat_action", None)

    def send_message(*args, **kwargs):
        return _safe_call(_send_message, *args, **kwargs)

    def send_photo(*args, **kwargs):
        # pyTelegramBotAPI иногда требует name у file-like объекта (BytesIO).
        photo = None
        try:
            if len(args) >= 2:
                photo = args[1]
            photo = kwargs.get("photo", photo)
        except Exception:
            photo = None

        try:
            if isinstance(photo, BytesIO):
                try:
                    photo.seek(0)
                except Exception:
                    pass
                if not getattr(photo, "name", None):
                    try:
                        photo.name = "photo.png"  # type: ignore[attr-defined]
                    except Exception:
                        pass
        except Exception:
            pass

        return _safe_call(_send_photo, *args, **kwargs)

    def edit_message_text(*args, **kwargs):
        return _safe_call(_edit_text, *args, **kwargs)

    def answer_callback_query(*args, **kwargs):
        return _safe_call(_answer_cb, *args, **kwargs)

    b.send_message = send_message  # type: ignore[assignment]
    b.send_photo = send_photo  # type: ignore[assignment]
    b.edit_message_text = edit_message_text  # type: ignore[assignment]
    b.answer_callback_query = answer_callback_query  # type: ignore[assignment]

    if _delete_msg is not None:
        def delete_message(*args, **kwargs):
            return _safe_call(_delete_msg, *args, **kwargs)

        b.delete_message = delete_message  # type: ignore[assignment]

    if _chat_action is not None:
        def send_chat_action(*args, **kwargs):
            return _safe_call(_chat_action, *args, **kwargs)

        b.send_chat_action = send_chat_action  # type: ignore[assignment]


_configure_telegram_http()
# Важно: не задаём parse_mode по умолчанию, чтобы при ошибках HTML можно было легко «падать» в plain‑text.
bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=4, skip_pending=True)
_patch_bot_api(bot)


# ---- UI keyboards ----
def kb_main() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.row("📚 Обучение", "🎮 Тренировка", "📊 Статистика")
    kb.row("🧮 Калькулятор", "🎯 Решить", "📈 Графики")
    kb.row("🧮 Матрицы", "📷 Фото", "🤖 AI")
    kb.row("📚 Уроки", "⚙️ Настройки", "ℹ️ Помощь")
    return kb


def kb_calc() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=5)
    kb.row("7", "8", "9", "/", "C")
    kb.row("4", "5", "6", "*", "⌫")
    kb.row("1", "2", "3", "-", "=")
    kb.row("0", ".", "(", ")", "+")
    kb.row("sin", "cos", "tan", "sqrt(", "^")
    kb.row("pi", "e", "ln(", "log(", "!")
    kb.row("🔙 Меню")
    return kb


def ikb_math_ops() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🧮 Уравнение", callback_data="op:eq"),
        types.InlineKeyboardButton("📊 Производная", callback_data="op:der"),
    )
    kb.add(
        types.InlineKeyboardButton("∫ Интеграл", callback_data="op:int"),
        types.InlineKeyboardButton("📐 Упростить", callback_data="op:simp"),
    )
    kb.add(
        types.InlineKeyboardButton("🧩 Разложить", callback_data="op:fact"),
        types.InlineKeyboardButton("📈 Предел", callback_data="op:lim"),
    )
    return kb


def ikb_graph_ops() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📈 2D", callback_data="graph:2d"),
        types.InlineKeyboardButton("📊 Несколько 2D", callback_data="graph:multi"),
    )
    kb.add(types.InlineKeyboardButton("🌐 3D", callback_data="graph:3d"))
    return kb


def ikb_matrix_ops() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("det(A)", callback_data="mat:det"),
        types.InlineKeyboardButton("A^-1", callback_data="mat:inv"),
    )
    kb.add(types.InlineKeyboardButton("A*B", callback_data="mat:mul"))
    return kb


def ikb_learning_home(tg_id: int) -> types.InlineKeyboardMarkup:
    due = db.count_due_reviews(tg_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🟦 ОГЭ", callback_data="learn:oge:0"),
        types.InlineKeyboardButton("🟩 ЕГЭ (База)", callback_data="learn:ege_base:0"),
    )
    kb.add(
        types.InlineKeyboardButton("🟥 ЕГЭ (Профиль)", callback_data="learn:ege_prof:0"),
        types.InlineKeyboardButton("🔁 Повторение (%d)" % due, callback_data="review:start"),
    )
    return kb


def ikb_skills(exam: str, tg_id: int, page: int) -> types.InlineKeyboardMarkup:
    all_sk = db.list_skills(exam)
    prog = db.get_user_skill_map(tg_id, exam)
    per_page = 12
    start = page * per_page
    chunk = all_sk[start : start + per_page]

    kb = types.InlineKeyboardMarkup(row_width=3)
    buttons: List[types.InlineKeyboardButton] = []
    for s in chunk:
        sid = str(s["id"])
        num = int(s["task_num"])
        row = prog.get(sid)
        lvl = int(row["level"]) if row else 0
        label = "№%d %s" % (num, ("⭐" * min(5, lvl) if lvl > 0 else "⬜"))
        buttons.append(types.InlineKeyboardButton(label, callback_data="skill:%s" % sid))
    for i in range(0, len(buttons), 3):
        kb.row(*buttons[i : i + 3])

    nav: List[types.InlineKeyboardButton] = []
    if start > 0:
        nav.append(types.InlineKeyboardButton("⬅️", callback_data="learn:%s:%d" % (exam, page - 1)))
    nav.append(types.InlineKeyboardButton("🏠", callback_data="learn:home"))
    if start + per_page < len(all_sk):
        nav.append(types.InlineKeyboardButton("➡️", callback_data="learn:%s:%d" % (exam, page + 1)))
    kb.row(*nav)
    return kb


def ikb_skill_actions(skill_id: str, exam: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("▶️ Практика", callback_data="practice:%s" % skill_id),
        types.InlineKeyboardButton("📘 Теория", callback_data="theory:%s" % skill_id),
    )
    kb.add(types.InlineKeyboardButton("🔙 К заданиям", callback_data="learn:%s:0" % exam))
    return kb


def ikb_task_options(session_id: str, options: List[str]) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    for i, opt in enumerate(options):
        kb.add(types.InlineKeyboardButton(opt, callback_data="ans:%s:%d" % (session_id, i)))
    kb.row(
        types.InlineKeyboardButton("⏭ Пропустить", callback_data="skip:%s" % session_id),
        types.InlineKeyboardButton("🏳️ Сдаться", callback_data="giveup:%s" % session_id),
    )
    return kb


def ikb_next(session_id: str, finished: bool) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏁 Итоги" if finished else "➡️ Далее", callback_data=("finish:%s" if finished else "next:%s") % session_id))
    return kb


def ikb_after_finish(skill_id: str, exam: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔁 Ещё раз", callback_data="practice:%s" % skill_id),
        types.InlineKeyboardButton("🔙 К заданиям", callback_data="learn:%s:0" % exam),
    )
    kb.add(types.InlineKeyboardButton("🏠 Меню", callback_data="learn:home"))
    return kb


def ikb_settings() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📋 История", callback_data="settings:history"))
    kb.add(types.InlineKeyboardButton("🧹 Очистить историю", callback_data="settings:clear"))
    kb.add(types.InlineKeyboardButton("ℹ️ О боте", callback_data="settings:about"))
    kb.add(types.InlineKeyboardButton("🧪 Диагностика", callback_data="settings:diag"))
    return kb


def _exam_title(exam: str) -> str:
    return {"oge": "ОГЭ", "ege_base": "ЕГЭ (База)", "ege_prof": "ЕГЭ (Профиль)", "school": "Школа"}.get(exam, exam)


# ---- Modes ----
@dataclass
class Mode:
    name: str
    data: Dict[str, Any]


user_modes: Dict[int, Mode] = {}
calc_buf: Dict[int, str] = {}


def set_mode(tg_id: int, name: str, **data: Any) -> None:
    user_modes[tg_id] = Mode(name=name, data=dict(data))


def clear_mode(tg_id: int) -> None:
    user_modes.pop(tg_id, None)


def get_mode(tg_id: int) -> Optional[Mode]:
    return user_modes.get(tg_id)


# ---- Welcome text ----
def welcome_text(first_name: str) -> str:
    # Текст как ты просил, плюс уточнения про режимы.
    return (
        "🎉 <b>Добро пожаловать, %s🧑‍💻!</b>\n\n"
        "🤖 <b>MathMaster AI Pro</b> — ваш интеллектуальный математический помощник!\n\n"
        "🚀 <b>ОСНОВНЫЕ ВОЗМОЖНОСТИ:</b>\n\n"
        "🧮 <b>ВЫЧИСЛЕНИЯ:</b>\n"
        "• Решение уравнений любой сложности\n"
        "• Производные и интегралы\n"
        "• Упрощение и разложение выражений\n"
        "• Матричные операции\n"
        "• Теория вероятностей\n\n"
        "📈 <b>ГРАФИКИ:</b>\n"
        "• 2D и 3D графики функций\n"
        "• Несколько графиков на одном поле\n\n"
        "📚 <b>ОБУЧЕНИЕ:</b>\n"
        "• 200+ уроков по всем темам\n"
        "• Подготовка к ЕГЭ 🎯\n"
        "• Квизы и тесты\n"
        "• Система прогресса\n\n"
        "🤖 <b>AI ПОМОЩНИК:</b>\n"
        "• Объяснение теории\n"
        "• Решение сложных задач\n"
        "• Проверка решений\n\n"
        "📷 <b>РЕШЕНИЕ ПО ФОТО:</b>\n"
        "• Распознавание математических задач\n"
        "• Решение с пошаговым объяснением\n\n"
        "💡 <b>ИСПОЛЬЗУЙТЕ МЕНЮ ДЛЯ НАВИГАЦИИ!</b>\n\n"
        "📊 <b>Быстрый старт:</b>\n"
        "1. Введите математическое выражение\n"
        "2. Используйте кнопки для выбора операции\n"
        "3. Задайте вопрос AI\n"
        "4. Отправьте фото с задачей\n\n"
        "<b>Примеры запросов:</b>\n"
        "• <code>2x + 5 = 13</code>\n"
        "• <code>производная от sin(x)</code>\n"
        "• <code>интеграл от x^2</code>\n"
        "• <code>построй график y = x^2</code>\n"
        "• <code>упрости (x+1)^2</code>\n\n"
        "ℹ️ Уроков в базе: <b>%d</b>"
    ) % (html_escape(first_name or "друг"), db.count_lessons())


# -------------------- Handlers --------------------
@bot.message_handler(commands=["start", "help", "menu"])
def on_start(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    calc_buf.pop(message.from_user.id, None)
    sessions.clear(message.from_user.id)
    bot.send_message(message.chat.id, welcome_text(message.from_user.first_name or ""), reply_markup=kb_main(), parse_mode="HTML")


@bot.message_handler(commands=["selftest", "diag"])
def on_selftest(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    try:
        import sys as _sys

        py_ver = _sys.version.split()[0]
    except Exception:
        py_ver = "unknown"

    rows: List[str] = ["🧪 <b>Self‑test</b>\n"]
    rows.append("Python: <code>%s</code>" % html_escape(py_ver))
    rows.append("SymPy: <b>%s</b>" % ("OK" if SYMPY_AVAILABLE else "MISSING"))
    rows.append("Plot: <b>%s</b>" % ("OK" if (NUMPY_AVAILABLE and MATPLOTLIB_AVAILABLE) else "MISSING"))
    rows.append("OCR: <b>%s</b>" % ("OK" if ocr.available() else "MISSING"))
    rows.append("AI keys: <b>%s</b>" % ("OK" if (OPENAI_API_KEY or DEEPSEEK_API_KEY) else "NO_KEYS"))
    rows.append("")

    if engine:
        ok, r = engine.eval("39*9")
        rows.append("calc 39*9: %s" % ("✅ <code>%s</code>" % html_escape(r) if ok else "❌ %s" % html_escape(r)))

        ok, _ = engine.solve_equation("2x+5=13")
        rows.append("solve 2x+5=13: %s" % ("✅" if ok else "❌"))

        ok, _ = engine.derivative("sin(x)")
        rows.append("derivative sin(x): %s" % ("✅" if ok else "❌"))

        ok, _ = engine.integral("x^2")
        rows.append("integral x^2: %s" % ("✅" if ok else "❌"))
    else:
        rows.append("❌ SymPy недоступен — вычисления/решения отключены.")

    bot.send_message(message.chat.id, "\n".join(rows), parse_mode="HTML")

    if engine and (NUMPY_AVAILABLE and MATPLOTLIB_AVAILABLE):
        try:
            buf = engine.plot_2d("x^2")
            bot.send_photo(message.chat.id, buf, caption="📈 Self‑test plot: y=x^2")
        except Exception:
            pass


@bot.message_handler(commands=["aitest", "ai_test"])
def on_aitest(message: types.Message) -> None:
    """Мини‑проверка внешнего AI (помогает понять, почему «AI не работает»)."""
    db.ensure_user(message.from_user)
    if OFFLINE_MODE:
        bot.send_message(message.chat.id, "⚠️ OFFLINE_MODE включён — внешний AI отключён.")
        return
    if not (OPENAI_API_KEY or DEEPSEEK_API_KEY):
        bot.send_message(
            message.chat.id,
            "❌ AI ключи не настроены.\nДобавьте в .env: OPENAI_API_KEY=… или DEEPSEEK_API_KEY=…",
        )
        return

    provs = ", ".join([p.name for p in ai.providers]) if getattr(ai, "providers", None) else "—"
    bot.send_chat_action(message.chat.id, "typing")
    prompt = "Ответь одним словом: OK."
    ans = ai.ask(prompt)
    txt = (
        "🤖 <b>AI test</b>\n\n"
        "<b>Провайдеры:</b> %s\n"
        "<b>Промпт:</b> <code>%s</code>\n\n"
        "<b>Ответ:</b>\n%s"
    ) % (html_escape(provs), html_escape(prompt), html_escape(ans))
    bot.send_message(message.chat.id, txt, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def on_help_btn(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    txt = (
        "ℹ️ <b>Помощь</b>\n\n"
        "• Для обучения: нажмите <b>📚 Обучение</b>\n"
        "• Для решения: <b>🎯 Решить</b> или просто отправьте пример\n"
        "• Для графиков: <b>📈 Графики</b>\n"
        "• Для матриц: <b>🧮 Матрицы</b>\n"
        "• Для фото: отправьте фото (подпись «рукопис» для рукописного)\n\n"
        "Примеры:\n"
        "• <code>x^2-5x+6=0</code>\n"
        "• <code>sin(pi/2)</code>\n"
        "• <code>sin(x)/x, x->0</code>"
    )
    bot.send_message(message.chat.id, txt, reply_markup=kb_main(), parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "📚 Обучение")
def on_learning(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    bot.send_message(message.chat.id, "📚 <b>Обучение (как Duolingo)</b>\n\nВыберите экзамен:", reply_markup=ikb_learning_home(message.from_user.id), parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "🎮 Тренировка")
def on_training(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    due = db.count_due_reviews(message.from_user.id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🔁 Повторение (%d)" % due, callback_data="review:start"))
    kb.add(types.InlineKeyboardButton("🎲 Случайное ОГЭ", callback_data="rand:oge"))
    kb.add(types.InlineKeyboardButton("🎲 Случайное ЕГЭ (база)", callback_data="rand:ege_base"))
    kb.add(types.InlineKeyboardButton("🎲 Случайное ЕГЭ (профиль)", callback_data="rand:ege_prof"))
    bot.send_message(message.chat.id, "🎮 <b>Тренировка</b>\n\nВыберите режим:", reply_markup=kb, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "📚 Уроки")
def on_lessons(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("Школа", callback_data="less:school:0"))
    kb.add(types.InlineKeyboardButton("ОГЭ", callback_data="less:oge:0"))
    kb.add(types.InlineKeyboardButton("ЕГЭ База", callback_data="less:ege_base:0"))
    kb.add(types.InlineKeyboardButton("ЕГЭ Профиль", callback_data="less:ege_prof:0"))
    bot.send_message(message.chat.id, "📚 <b>Уроки</b>\n\nВыберите раздел:", reply_markup=kb, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def on_stats(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    user = db.get_user(message.from_user.id)
    due = db.count_due_reviews(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "Профиль не найден. Нажмите /start.", reply_markup=kb_main())
        return
    txt = (
        "📊 <b>Статистика</b>\n\n"
        "🏆 Уровень: <b>%d</b>\n"
        "⭐ XP: <b>%d</b>\n"
        "🔥 Серия: <b>%d</b>\n"
        "🔁 К повторению: <b>%d</b>\n\n"
        "💡 Делайте 1–2 навыка в день для серии."
    ) % (int(user["level"]), int(user["xp"]), int(user["streak"]), int(due))
    bot.send_message(message.chat.id, txt, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "⚙️ Настройки")
def on_settings(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    bot.send_message(message.chat.id, "⚙️ <b>Настройки</b>", reply_markup=ikb_settings(), parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "🧮 Калькулятор")
def on_calc(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    set_mode(message.from_user.id, "calc")
    calc_buf[message.from_user.id] = ""
    bot.send_message(
        message.chat.id,
        "🧮 <b>Калькулятор</b>\n\nНабирайте выражение кнопками или пришлите целиком.\nНажмите <code>=</code> для вычисления.",
        reply_markup=kb_calc(),
        parse_mode="HTML",
    )


@bot.message_handler(func=lambda m: m.text == "🎯 Решить")
def on_solve_menu(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    bot.send_message(message.chat.id, "🎯 <b>Выберите операцию</b>", reply_markup=ikb_math_ops(), parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "📈 Графики")
def on_graphs(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    txt = "📈 <b>Графики</b>\n\nВыберите тип графика:"
    if not (MATPLOTLIB_AVAILABLE and NUMPY_AVAILABLE):
        txt += "\n\n⚠️ Для графиков нужны зависимости: numpy + matplotlib."
    bot.send_message(message.chat.id, txt, reply_markup=ikb_graph_ops(), parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "🧮 Матрицы")
def on_matrices(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    txt = (
        "🧮 <b>Матрицы</b>\n\n"
        "Формат матрицы A:\n"
        "• <code>[[1,2],[3,4]]</code>\n"
        "или\n"
        "• <code>1 2; 3 4</code>\n\n"
        "Выберите операцию:"
    )
    bot.send_message(message.chat.id, txt, reply_markup=ikb_matrix_ops(), parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "📷 Фото")
def on_photo_mode(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    txt = (
        "📷 <b>Решение по фото</b>\n\n"
        "Отправьте фото с примером/уравнением.\n"
        "Если рукописное — добавьте в подпись слово <code>рукопис</code>.\n"
    )
    if not ocr.available():
        txt += (
            "\n\n⚠️ <b>OCR не настроен.</b>\n"
            "Установите один из вариантов:\n"
            "• <b>EasyOCR</b> (лучше для рукописи): <code>pip install easyocr</code>\n"
            "• <b>Tesseract</b> (легче):\n"
            "  1) <code>brew install tesseract</code>\n"
            "  2) <code>pip install pytesseract</code>\n\n"
            "И в любом случае нужен <code>pip install pillow</code>."
        )
    bot.send_message(message.chat.id, txt, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "🤖 AI")
def on_ai_mode(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    set_mode(message.from_user.id, "ai")
    txt = "🤖 <b>AI‑помощник</b>\n\nНапишите вопрос или задачу."
    if OFFLINE_MODE:
        txt += "\n\n⚠️ Сейчас включён <code>OFFLINE_MODE=true</code> — ответы будут офлайн."
    elif not (OPENAI_API_KEY or DEEPSEEK_API_KEY):
        txt += (
            "\n\n⚠️ AI‑ключи не настроены.\n"
            "Добавьте в <code>.env</code> один из ключей:\n"
            "• <code>OPENAI_API_KEY=…</code>\n"
            "• <code>DEEPSEEK_API_KEY=…</code>\n"
        )
    bot.send_message(message.chat.id, txt, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "🔙 Меню")
def on_back_to_menu(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    clear_mode(message.from_user.id)
    calc_buf.pop(message.from_user.id, None)
    sessions.clear(message.from_user.id)
    bot.send_message(message.chat.id, "📋 <b>Главное меню</b>", reply_markup=kb_main(), parse_mode="HTML")


# ---- calculator mode handler ----
@bot.message_handler(func=lambda m: (get_mode(m.from_user.id).name if get_mode(m.from_user.id) else "") == "calc")
def on_calc_input(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    txt = (message.text or "").strip()
    uid = message.from_user.id
    if txt == "🔙 Меню":
        on_back_to_menu(message)
        return

    buf = calc_buf.get(uid, "")
    if txt == "C":
        calc_buf[uid] = ""
        bot.send_message(message.chat.id, "✅ Очищено.", reply_markup=kb_calc())
        return
    if txt == "⌫":
        calc_buf[uid] = buf[:-1]
        bot.send_message(message.chat.id, "🔢 <code>%s</code>" % html_escape(calc_buf[uid] or "0"), parse_mode="HTML")
        return
    if txt == "=":
        if not buf:
            bot.send_message(message.chat.id, "Введите выражение.", reply_markup=kb_calc())
            return
        if not engine:
            bot.send_message(message.chat.id, "sympy не установлен. Установите зависимости.", reply_markup=kb_main())
            return
        ok, msg, ans = engine.eval_full(buf)
        if ok:
            bot.send_message(message.chat.id, msg, parse_mode="HTML")
            db.add_history(uid, "calc", buf, ans)
        else:
            bot.send_message(message.chat.id, msg)
        calc_buf[uid] = ""
        return

    # pasted expression replaces buffer
    if any(ch in txt for ch in "+-*/^()=") and len(txt) > 2:
        calc_buf[uid] = txt
    else:
        calc_buf[uid] = buf + txt
    show = calc_buf[uid]
    if len(show) > 90:
        show = "…" + show[-89:]
    bot.send_message(message.chat.id, "🔢 <code>%s</code>" % html_escape(show), parse_mode="HTML")


# ---- photo handler ----
def _explain_equation_steps(raw_text: str) -> Optional[str]:
    if not engine or not SYMPY_AVAILABLE:
        return None
    try:
        norm = engine.normalize(raw_text)
        if "=" in norm:
            left, right = norm.split("=", 1)
            lhs = engine.parse(left)
            rhs = engine.parse(right)
        else:
            lhs = engine.parse(norm)
            rhs = sp.Integer(0)  # type: ignore[attr-defined]
        expr = sp.simplify(lhs - rhs)  # type: ignore[attr-defined]
        vars_ = sorted(list(expr.free_symbols), key=lambda s: str(s))
        var = None
        for s in vars_:
            if str(s) == "x":
                var = s
                break
        if var is None:
            var = vars_[0] if vars_ else sp.Symbol("x")  # type: ignore[attr-defined]

        try:
            poly = sp.Poly(expr, var)  # type: ignore[attr-defined]
        except Exception:
            return None
        deg = int(poly.degree())
        if deg == 1:
            a, b = poly.all_coeffs()
            if a == 0:
                return None
            x_sol = sp.simplify(-b / a)  # type: ignore[attr-defined]
            return (
                "📷 <b>Решение по фото (с объяснением)</b>\n\n"
                "<b>Уравнение:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n"
                "1) Переносим всё влево: <code>%s = 0</code>\n"
                "2) Это линейное: <code>%s·x + (%s) = 0</code>\n"
                "3) Делим на коэффициент при x: <code>x = -(%s)/(%s) = %s</code>\n\n"
                "<b>Ответ:</b> <code>%s</code>"
            ) % (
                html_escape(raw_text),
                html_escape(str(expr)),
                html_escape(str(a)),
                html_escape(str(b)),
                html_escape(str(b)),
                html_escape(str(a)),
                html_escape(str(x_sol)),
                html_escape(str(x_sol)),
            )
        if deg == 2:
            a, b, c = poly.all_coeffs()
            D = sp.simplify(b * b - 4 * a * c)  # type: ignore[attr-defined]
            sqrtD = sp.sqrt(D)  # type: ignore[attr-defined]
            x1 = sp.simplify((-b + sqrtD) / (2 * a))  # type: ignore[attr-defined]
            x2 = sp.simplify((-b - sqrtD) / (2 * a))  # type: ignore[attr-defined]
            return (
                "📷 <b>Решение по фото (с объяснением)</b>\n\n"
                "<b>Уравнение:</b> <code>%s</code>\n\n"
                "<b>Шаги:</b>\n"
                "1) Приводим к виду <code>ax^2+bx+c=0</code>\n"
                "2) Коэффициенты: a=<code>%s</code>, b=<code>%s</code>, c=<code>%s</code>\n"
                "3) Дискриминант: <code>D=b^2-4ac=%s</code>\n"
                "4) Корни: <code>x=(-b±√D)/(2a)</code>\n"
                "   • x₁=<code>%s</code>\n"
                "   • x₂=<code>%s</code>\n\n"
                "<b>Ответ:</b> <code>%s</code>, <code>%s</code>"
            ) % (
                html_escape(raw_text),
                html_escape(str(a)),
                html_escape(str(b)),
                html_escape(str(c)),
                html_escape(str(D)),
                html_escape(str(x1)),
                html_escape(str(x2)),
                html_escape(str(x1)),
                html_escape(str(x2)),
            )
    except Exception:
        return None


def _photo_solve_text(recognized: str) -> Tuple[str, str]:
    text = (recognized or "").strip()
    if not text:
        return "❌ Не удалось распознать текст.", "photo_empty"

    if engine:
        if "=" in text:
            explained = _explain_equation_steps(text)
            if explained:
                return explained, "photo_eq_explain"
            ok, out = engine.solve_equation(text)
            return out, "photo_equation"
        ok, msg, ans = engine.eval_full(text)
        if ok:
            return (
                "📷 <b>Решение по фото</b>\n\n"
                "<b>Распознано:</b> <code>%s</code>\n\n%s"
            ) % (html_escape(text), msg), "photo_calc_steps"
        # if eval failed, fall through to AI

    ans = ai.ask("Реши и объясни: %s" % text)
    return "🤖 <b>AI</b>:\n\n%s" % html_escape(ans), "photo_ai"


@bot.message_handler(content_types=["photo"])
def on_photo(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    caption = (message.caption or "").lower()
    handwritten = ("рукопис" in caption) or ("hand" in caption)

    bot.send_message(message.chat.id, "⏳ Распознаю изображение…")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        img_bytes = bot.download_file(file_info.file_path)
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Не удалось скачать фото: %s" % e)
        return

    if not ocr.available():
        bot.send_message(
            message.chat.id,
            "❌ <b>OCR не настроен.</b>\n\n"
            "Установите зависимости:\n"
            "1) <code>pip install pillow</code>\n\n"
            "<b>Вариант A (EasyOCR, лучше для рукописи):</b>\n"
            "2) <code>pip install easyocr</code>\n\n"
            "<b>Вариант B (Tesseract, легче):</b>\n"
            "2) <code>brew install tesseract</code>\n"
            "3) <code>pip install pytesseract</code>\n",
            parse_mode="HTML",
        )
        return

    res = ocr.extract(img_bytes, handwritten=handwritten)
    if not res.ok:
        bot.send_message(message.chat.id, "❌ OCR: %s" % res.text)
        return
    recognized = res.text
    bot.send_message(message.chat.id, "🔎 Распознано (%s): <code>%s</code>" % (res.engine, html_escape(recognized)), parse_mode="HTML")

    out, kind = _photo_solve_text(recognized)
    bot.send_message(message.chat.id, out, parse_mode="HTML")
    db.add_history(message.from_user.id, kind, recognized, out)


# ---- universal text ----
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message: types.Message) -> None:
    db.ensure_user(message.from_user)
    txt = (message.text or "").strip()
    if not txt:
        return

    md = get_mode(message.from_user.id)
    if md and md.name == "ai":
        clear_mode(message.from_user.id)
        bot.send_chat_action(message.chat.id, "typing")
        ans = ai.ask(txt)
        bot.send_message(message.chat.id, "🤖 <b>Ответ</b>:\n\n%s" % html_escape(ans), parse_mode="HTML")
        db.add_history(message.from_user.id, "ai", txt, ans)
        return

    if md and md.name.startswith("input_graph_"):
        kind = md.name.replace("input_graph_", "")
        clear_mode(message.from_user.id)
        handle_graph_input(message, kind, txt)
        return

    # Важно: input_graph_* тоже начинается с "input_", поэтому проверка графиков должна быть выше.
    if md and md.name.startswith("input_"):
        kind = md.name.replace("input_", "")
        clear_mode(message.from_user.id)
        handle_math_input(message, kind, txt)
        return

    if md and md.name.startswith("mat_"):
        kind = md.name.replace("mat_", "")
        clear_mode(message.from_user.id)
        handle_matrix_input(message, kind, txt)
        return

    # Default: try smart parse (equation/eval/keywords)
    low = txt.lower()
    if "производн" in low and engine:
        func = re.sub(r".*от\s+", "", txt, flags=re.IGNORECASE).strip()
        ok, out = engine.derivative(func or txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "derivative", txt, out)
        return
    if "интеграл" in low and engine:
        func = re.sub(r".*от\s+", "", txt, flags=re.IGNORECASE).strip()
        ok, out = engine.integral(func or txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "integral", txt, out)
        return
    if "упрости" in low and engine:
        expr = re.sub(r".*упрости\s+", "", txt, flags=re.IGNORECASE).strip()
        ok, out = engine.simplify_expr(expr or txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "simplify", txt, out)
        return
    if ("разложи" in low or "разложить" in low) and engine:
        expr = re.sub(r".*разлож(и|ить)\s+", "", txt, flags=re.IGNORECASE).strip()
        ok, out = engine.factor_expr(expr or txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "factor", txt, out)
        return
    if ("предел" in low or "lim" in low) and engine:
        ok, out = engine.limit_expr(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "limit", txt, out)
        return
    if ("график" in low or "plot" in low) and engine:
        func = re.sub(r".*(график|plot)\s+", "", txt, flags=re.IGNORECASE).strip()
        try:
            buf = engine.plot_2d(func or txt)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ График не построен: %s" % html_escape(str(e)), parse_mode="HTML")
            return
        bot.send_photo(message.chat.id, buf, caption="📈 y = %s" % func)
        db.add_history(message.from_user.id, "plot2d", txt, "ok")
        return

    # math direct
    if engine and (("=" in txt) or any(ch in txt for ch in "+-*/^()")):
        if "=" in txt:
            ok, out = engine.solve_equation(txt)
            bot.send_message(message.chat.id, out, parse_mode="HTML")
            db.add_history(message.from_user.id, "solve", txt, out)
        else:
            ok, msg, ans = engine.eval_full(txt)
            if ok:
                bot.send_message(message.chat.id, msg, parse_mode="HTML")
                db.add_history(message.from_user.id, "calc", txt, ans)
            else:
                bot.send_message(message.chat.id, msg)
        return

    bot.send_message(message.chat.id, "🤔 Не понял. Используйте меню или пришлите математический пример.", reply_markup=kb_main())


# ---- math op input ----
def handle_math_input(message: types.Message, kind: str, txt: str) -> None:
    if not engine:
        bot.send_message(message.chat.id, "sympy не установлен. Установите зависимости.", reply_markup=kb_main())
        return
    if kind == "eq":
        ok, out = engine.solve_equation(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "equation", txt, out)
        return
    if kind == "der":
        ok, out = engine.derivative(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "derivative", txt, out)
        return
    if kind == "int":
        ok, out = engine.integral(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "integral", txt, out)
        return
    if kind == "simp":
        ok, out = engine.simplify_expr(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "simplify", txt, out)
        return
    if kind == "fact":
        ok, out = engine.factor_expr(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "factor", txt, out)
        return
    if kind == "lim":
        ok, out = engine.limit_expr(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "limit", txt, out)
        return
    bot.send_message(message.chat.id, "Неизвестная операция.")


_NUM_RE = r"[-+]?\d+(?:\.\d+)?"


def _try_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except Exception:
        return None


def _fmt_range_val(x: float) -> str:
    try:
        if float(x).is_integer():
            return str(int(x))
        s = ("%0.6f" % float(x)).rstrip("0").rstrip(".")
        return s or str(x)
    except Exception:
        return str(x)


def _parse_2d_graph_request(raw: str) -> Tuple[str, float, float]:
    """
    Поддерживает:
    - "sin(x)"
    - "sin(x) -5 5"
    - "x^2 + 2x + 1 -10 10"
    """
    s = (raw or "").strip()
    m = re.match(r"^(.*)\s+(%s)\s+(%s)\s*$" % (_NUM_RE, _NUM_RE), s)
    if m:
        func = (m.group(1) or "").strip()
        a = _try_float(m.group(2))
        b = _try_float(m.group(3))
        if func and a is not None and b is not None:
            return func, float(a), float(b)
    return s, -10.0, 10.0


def _parse_multi_2d_graph_request(raw: str) -> Tuple[List[str], float, float]:
    """
    Поддерживает:
    - "x^2, sin(x), cos(x)"
    - "x^2, sin(x), cos(x) -5 5"
    """
    s = (raw or "").strip()
    x_min, x_max = -10.0, 10.0
    m = re.match(r"^(.*)\s+(%s)\s+(%s)\s*$" % (_NUM_RE, _NUM_RE), s)
    if m:
        body = (m.group(1) or "").strip()
        a = _try_float(m.group(2))
        b = _try_float(m.group(3))
        if a is not None and b is not None:
            s = body
            x_min, x_max = float(a), float(b)
    funcs = [f.strip() for f in s.split(",") if f.strip()]
    return funcs, x_min, x_max


def _parse_3d_graph_request(raw: str) -> Tuple[str, float, float, float, float]:
    """
    Поддерживает:
    - "sin(x)+cos(y)"
    - "sin(x)+cos(y) -5 5 -5 5"
    """
    s = (raw or "").strip()
    m = re.match(r"^(.*)\s+(%s)\s+(%s)\s+(%s)\s+(%s)\s*$" % (_NUM_RE, _NUM_RE, _NUM_RE, _NUM_RE), s)
    if m:
        func = (m.group(1) or "").strip()
        a = _try_float(m.group(2))
        b = _try_float(m.group(3))
        c = _try_float(m.group(4))
        d = _try_float(m.group(5))
        if func and None not in (a, b, c, d):
            return func, float(a), float(b), float(c), float(d)
    return s, -5.0, 5.0, -5.0, 5.0


def handle_graph_input(message: types.Message, kind: str, txt: str) -> None:
    if not engine:
        bot.send_message(message.chat.id, "sympy не установлен.", reply_markup=kb_main())
        return
    if kind == "2d":
        bot.send_chat_action(message.chat.id, "upload_photo")
        func, x_min, x_max = _parse_2d_graph_request(txt)
        try:
            buf = engine.plot_2d(func, x_min=x_min, x_max=x_max)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ График не построен: %s" % html_escape(str(e)), parse_mode="HTML")
            return
        bot.send_photo(
            message.chat.id,
            buf,
            caption="📈 y = %s\nx∈[%s,%s]" % (func, _fmt_range_val(x_min), _fmt_range_val(x_max)),
        )
        db.add_history(message.from_user.id, "plot2d", txt, "ok")
        return
    if kind == "multi":
        bot.send_chat_action(message.chat.id, "upload_photo")
        funcs, x_min, x_max = _parse_multi_2d_graph_request(txt)
        if len(funcs) < 2:
            bot.send_message(
                message.chat.id,
                "Нужно минимум 2 функции через запятую.\nПример: <code>x^2, sin(x), cos(x) -5 5</code>",
                parse_mode="HTML",
            )
            return
        try:
            buf = engine.plot_multi_2d(funcs, x_min=x_min, x_max=x_max)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Графики не построены: %s" % html_escape(str(e)), parse_mode="HTML")
            return
        bot.send_photo(
            message.chat.id,
            buf,
            caption="📊 Несколько графиков\nx∈[%s,%s]" % (_fmt_range_val(x_min), _fmt_range_val(x_max)),
        )
        db.add_history(message.from_user.id, "plot_multi", txt, "ok")
        return
    if kind == "3d":
        bot.send_chat_action(message.chat.id, "upload_photo")
        func, x_min, x_max, y_min, y_max = _parse_3d_graph_request(txt)
        try:
            buf = engine.plot_3d(func, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ 3D график не построен: %s" % html_escape(str(e)), parse_mode="HTML")
            return
        bot.send_photo(
            message.chat.id,
            buf,
            caption="🌐 z = %s\nx∈[%s,%s], y∈[%s,%s]"
            % (func, _fmt_range_val(x_min), _fmt_range_val(x_max), _fmt_range_val(y_min), _fmt_range_val(y_max)),
        )
        db.add_history(message.from_user.id, "plot3d", txt, "ok")
        return


def handle_matrix_input(message: types.Message, kind: str, txt: str) -> None:
    if not engine:
        bot.send_message(message.chat.id, "sympy не установлен.", reply_markup=kb_main())
        return
    if kind == "det":
        ok, out = engine.matrix_det(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "matrix_det", txt, out)
        return
    if kind == "inv":
        ok, out = engine.matrix_inv(txt)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "matrix_inv", txt, out)
        return
    if kind == "mul":
        # expect "A || B"
        if "||" not in txt:
            bot.send_message(message.chat.id, "Для умножения пришлите: <code>A || B</code>.\nПример: <code>1 2;3 4 || 5 6;7 8</code>", parse_mode="HTML")
            return
        a, b = [p.strip() for p in txt.split("||", 1)]
        ok, out = engine.matrix_mul(a, b)
        bot.send_message(message.chat.id, out, parse_mode="HTML")
        db.add_history(message.from_user.id, "matrix_mul", txt, out)
        return


# ---- practice helpers ----
def _get_skill_row(skill_id: str) -> Optional[sqlite3.Row]:
    conn = db._connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT exam, task_num, title, topic FROM skills WHERE id=?", (skill_id,))
        return cur.fetchone()
    finally:
        conn.close()


def start_practice(chat_id: int, tg_id: int, skill_id: str, *, seed: Optional[int] = None) -> Optional[PracticeSession]:
    row = _get_skill_row(skill_id)
    if not row:
        bot.send_message(chat_id, "❌ Навык не найден.")
        return None

    exam = str(row["exam"])
    task_num = int(row["task_num"])
    title = str(row["title"])
    topic = str(row["topic"])

    prog = db.get_user_skill_map(tg_id, exam)
    pr = prog.get(skill_id)
    lvl = int(pr["level"]) if pr else 0
    difficulty = max(1, min(5, lvl if lvl > 0 else 1))

    rng = random.Random()
    if seed is None:
        seed = (tg_id << 16) ^ int(time.time())
    rng.seed(seed)

    n_tasks = 7 + max(0, difficulty - 1)
    tasks = [gen_task_for_skill(rng, exam, task_num, topic=topic, difficulty=difficulty) for _ in range(n_tasks)]

    sid = new_session_id()
    sess = PracticeSession(
        session_id=sid,
        tg_id=tg_id,
        skill_id=skill_id,
        exam=exam,
        task_num=task_num,
        title=title,
        tasks=tasks,
    )
    sessions.set(tg_id, sess)
    send_current_task(chat_id, sess, edit_message_id=None)
    return sess


# ---- callbacks ----
@bot.callback_query_handler(func=lambda call: True)
def on_callback(call: types.CallbackQuery) -> None:
    db.ensure_user(call.from_user)
    data = call.data or ""
    try:
        # learning home
        if data == "learn:home":
            bot.edit_message_text(
                "📚 <b>Обучение</b>\n\nВыберите экзамен:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=ikb_learning_home(call.from_user.id),
                parse_mode="HTML",
            )
            bot.answer_callback_query(call.id)
            return

        # skills list
        if data.startswith("learn:") and data.count(":") == 2:
            _, exam, page_s = data.split(":")
            page = int(page_s)
            bot.edit_message_text(
                "📚 <b>%s</b>\n\nВыберите номер задания:" % _exam_title(exam),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=ikb_skills(exam, call.from_user.id, page),
                parse_mode="HTML",
            )
            bot.answer_callback_query(call.id)
            return

        # lessons list
        if data.startswith("less:") and data.count(":") == 2:
            _, exam, page_s = data.split(":")
            page = int(page_s)
            lessons = db.list_lessons(exam, limit=24)
            kb = types.InlineKeyboardMarkup(row_width=1)
            start = page * 10
            chunk = lessons[start : start + 10]
            for r in chunk:
                diff = int(r["difficulty"])
                stars = "⭐" * min(5, diff)
                kb.add(types.InlineKeyboardButton("%s (%s)" % (r["title"], stars), callback_data="lesson:%s" % r["id"]))
            nav = types.InlineKeyboardMarkup(row_width=3)
            nav_btns = []
            if start > 0:
                nav_btns.append(types.InlineKeyboardButton("⬅️", callback_data="less:%s:%d" % (exam, page - 1)))
            nav_btns.append(types.InlineKeyboardButton("🏠", callback_data="learn:home"))
            if start + 10 < len(lessons):
                nav_btns.append(types.InlineKeyboardButton("➡️", callback_data="less:%s:%d" % (exam, page + 1)))
            if nav_btns:
                kb.row(*nav_btns)
            bot.edit_message_text(
                "📚 <b>Уроки • %s</b>\n\nВыберите урок:" % _exam_title(exam),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=kb,
                parse_mode="HTML",
            )
            bot.answer_callback_query(call.id)
            return

        if data.startswith("lesson:"):
            lesson_id = data.split(":", 1)[1]
            row = db.get_lesson(lesson_id)
            if not row:
                bot.answer_callback_query(call.id, "Урок не найден")
                return
            exam = str(row["exam"])
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔙 К урокам", callback_data="less:%s:0" % exam))
            kb.add(types.InlineKeyboardButton("🏠", callback_data="learn:home"))
            bot.edit_message_text(str(row["content"]), call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")
            bot.answer_callback_query(call.id)
            return

        # skill view
        if data.startswith("skill:"):
            skill_id = data.split(":", 1)[1]
            # fetch skill
            exam = None
            task_num = None
            title = ""
            desc = ""
            skills = []
            # quick: infer exam prefix in id
            if skill_id.startswith("oge_"):
                exam = "oge"
            elif skill_id.startswith("ege_base_"):
                exam = "ege_base"
            elif skill_id.startswith("ege_prof_"):
                exam = "ege_prof"
            # fallback: read from db
            conn = db._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM skills WHERE id=?", (skill_id,))
                r = cur.fetchone()
                if not r:
                    bot.answer_callback_query(call.id, "Навык не найден")
                    return
                exam = str(r["exam"])
                task_num = int(r["task_num"])
                title = str(r["title"])
                desc = str(r["description"])
            finally:
                conn.close()

            prog = db.get_user_skill_map(call.from_user.id, exam)
            pr = prog.get(skill_id)
            lvl = int(pr["level"]) if pr else 0
            xp = int(pr["xp"]) if pr else 0
            cor = int(pr["correct"]) if pr else 0
            tot = int(pr["total"]) if pr else 0
            acc = 0.0 if tot == 0 else round(100.0 * cor / float(tot), 1)

            text = (
                "📚 <b>%s • Задание %d</b>\n<b>%s</b>\n\n%s\n\n⭐ Уровень: <b>%d/5</b>\n🎯 XP навыка: <b>%d</b>\n✅ Точность: <b>%s%%</b>"
                % (_exam_title(exam), int(task_num or 0), html_escape(title), html_escape(desc), lvl, xp, str(acc))
            )
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=ikb_skill_actions(skill_id, exam), parse_mode="HTML")
            bot.answer_callback_query(call.id)
            return

        if data.startswith("theory:"):
            skill_id = data.split(":", 1)[1]
            conn = db._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT exam, task_num, title, topic FROM skills WHERE id=?", (skill_id,))
                r = cur.fetchone()
                if not r:
                    bot.answer_callback_query(call.id, "Навык не найден")
                    return
                exam = str(r["exam"])
                num = int(r["task_num"])
                title = str(r["title"])
                topic = str(r["topic"])
            finally:
                conn.close()

            # Prefer dedicated cards for this task
            theory_id = f"{exam}:task{num:02d}:theory"
            ex_id = f"{exam}:task{num:02d}:examples"
            mis_id = f"{exam}:task{num:02d}:mistakes"
            blocks: List[str] = []
            for lid in (theory_id, ex_id, mis_id):
                row = db.get_lesson(lid)
                if row:
                    blocks.append(str(row["content"]))

            if not blocks:
                # Fallback: by topic
                lesson_rows = db.list_lessons(exam, topic=topic if topic != "Смешанное" else None, limit=6)
                teaser = "\n".join(["• %s" % html_escape(l["title"]) for l in lesson_rows[:5]])
                blocks = [("Рекомендуемые уроки:\n%s" % (teaser or "• (пока нет)"))]

            text = "📘 <b>Теория</b>\n\n<b>%s • №%d</b>\n%s\n\n%s" % (
                _exam_title(exam),
                num,
                html_escape(title),
                "\n\n".join(blocks),
            )
            # Telegram limit protection
            if len(text) > 3900:
                text = text[:3900] + "…"

            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=ikb_skill_actions(skill_id, exam), parse_mode="HTML")
            bot.answer_callback_query(call.id)
            return

        if data.startswith("practice:"):
            skill_id = data.split(":", 1)[1]
            sess = start_practice(call.message.chat.id, call.from_user.id, skill_id)
            bot.answer_callback_query(call.id, "Старт!" if sess else "Ошибка")
            return

        if data.startswith("ans:"):
            _, sid, idx_s = data.split(":")
            idx = int(idx_s)
            sess = sessions.get(call.from_user.id)
            if not sess or sess.session_id != sid:
                bot.answer_callback_query(call.id, "Сессия устарела. Запустите практику заново.")
                return
            task = sess.current()
            if not task:
                bot.answer_callback_query(call.id, "Сессия завершена.")
                return
            is_correct = idx == task.correct_index
            if is_correct:
                sess.correct += 1
            # progress
            db.bump_user_skill(call.from_user.id, sess.skill_id, is_correct, 20 if is_correct else 5)
            db.add_xp(call.from_user.id, 10 if is_correct else 2, today_utc_date())

            picked = task.options[idx] if 0 <= idx < len(task.options) else "?"
            status = "✅ Верно!" if is_correct else "❌ Неверно."
            text = (
                "%s\n\n<b>Ваш ответ:</b> <code>%s</code>\n<b>Правильный:</b> <code>%s</code>\n\n📌 <b>Разбор:</b>\n%s"
                % (status, html_escape(picked), html_escape(task.answer_text), html_escape(task.explanation))
            )
            sess.advance()
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=ikb_next(sess.session_id, sess.finished), parse_mode="HTML")
            bot.answer_callback_query(call.id, "Ок")
            return

        if data.startswith("skip:") or data.startswith("giveup:"):
            action, sid = data.split(":")
            sess = sessions.get(call.from_user.id)
            if not sess or sess.session_id != sid:
                bot.answer_callback_query(call.id, "Сессия устарела.")
                return
            task = sess.current()
            if not task:
                bot.answer_callback_query(call.id, "Сессия завершена.")
                return
            status = "⏭ Пропущено." if action == "skip" else "🏳️ Вы сдались."
            text = "%s\n\n<b>Правильный ответ:</b> <code>%s</code>\n\n📌 <b>Разбор:</b>\n%s" % (
                status,
                html_escape(task.answer_text),
                html_escape(task.explanation),
            )
            sess.advance()
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=ikb_next(sess.session_id, sess.finished), parse_mode="HTML")
            bot.answer_callback_query(call.id, "Ок")
            return

        if data.startswith("next:"):
            sid = data.split(":", 1)[1]
            sess = sessions.get(call.from_user.id)
            if not sess or sess.session_id != sid:
                bot.answer_callback_query(call.id, "Сессия устарела.")
                return
            send_current_task(call.message.chat.id, sess, edit_message_id=call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        if data.startswith("finish:"):
            sid = data.split(":", 1)[1]
            sess = sessions.get(call.from_user.id)
            if not sess or sess.session_id != sid:
                bot.answer_callback_query(call.id, "Сессия устарела.")
                return

            correct = sess.correct
            total = len(sess.tasks)
            grade = grade_from_accuracy(correct, total)
            prev_row = db.get_review(call.from_user.id, sess.skill_id)
            prev = None
            if prev_row:
                prev = ReviewState(float(prev_row["interval_days"]), float(prev_row["ease"]), str(prev_row["due_at"]))
            new_state = update_review(prev, grade)
            db.upsert_review(call.from_user.id, sess.skill_id, new_state.due_at, new_state.interval_days, new_state.ease)
            sessions.clear(call.from_user.id)

            acc = 0.0 if total == 0 else round(100.0 * correct / float(total), 1)
            text = (
                "🏁 <b>Итоги</b>\n\n"
                "<b>%s • Задание %d</b>\n<b>%s</b>\n\n"
                "✅ Правильно: <b>%d/%d</b> (%s%%)\n"
                "🔁 Следующее повторение: <b>%s</b> (UTC)\n"
                "📚 Оценка: <b>%d/5</b>"
            ) % (_exam_title(sess.exam), sess.task_num, html_escape(sess.title), correct, total, str(acc), html_escape(new_state.due_at), grade)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=ikb_after_finish(sess.skill_id, sess.exam), parse_mode="HTML")
            bot.answer_callback_query(call.id, "Готово!")
            return

        if data == "review:start":
            due = db.list_due_reviews(call.from_user.id, limit=1)
            if not due:
                bot.answer_callback_query(call.id, "Пока нечего повторять 🙂")
                bot.send_message(call.message.chat.id, "🔁 Сейчас нет задач к повторению. Решите пару навыков в «Обучение».")
                return
            skill_id = str(due[0]["skill_id"])
            bot.answer_callback_query(call.id, "Поехали!")
            start_practice(call.message.chat.id, call.from_user.id, skill_id)
            return

        if data.startswith("rand:"):
            exam = data.split(":", 1)[1]
            skills = db.list_skills(exam)
            if not skills:
                bot.answer_callback_query(call.id, "Нет навыков")
                return
            s = random.choice(skills)
            skill_id = str(s["id"])
            bot.answer_callback_query(call.id, "Случайная практика!")
            start_practice(call.message.chat.id, call.from_user.id, skill_id)
            return

        if data == "settings:about":
            about = (
                "ℹ️ О MathMaster AI\n\n"
                "🤖 Версия: 3.0.0\n"
                "📅 Дата сборки: 2026\n"
                "👨‍💻 Разработчик: MathMaster Team @lumix1111\n\n"
                "Технологии:\n"
                "• Python 3.11+\n"
                "• SymPy - символьная математика\n"
                "• Matplotlib - построение графиков\n"
                "• SQLite - база данных\n"
                "• AI интеграция (DeepSeek, OpenAI)\n\n"
                "Особенности:\n"
                "• Полностью бесплатный\n"
                "• Постоянные обновления\n"
                "• Поддержка пользователей\n"
                "• Кроссплатформенность\n\n"
                "Контакты:\n"
                "• Поддержка: @MathMasterSupport\n"
                "• Предложения: @MathMasterFeedback\n"
                "• Баги и ошибки: @MathMasterBugs\n\n"
                "💡 Лицензия: MIT Open Source License\n\n"
                "❤️ Спасибо, что используете MathMaster AI!"
            )
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔙 К настройкам", callback_data="settings:home"))
            bot.edit_message_text(about, call.message.chat.id, call.message.message_id, reply_markup=kb)
            bot.answer_callback_query(call.id)
            return

        if data == "settings:diag":
            py_ver = "unknown"
            try:
                import sys as _sys

                py_ver = _sys.version.split()[0]
            except Exception:
                pass
            ssl_ver = "unknown"
            req_ver = "unknown"
            u3_ver = "unknown"
            tb_ver = "unknown"
            try:
                import ssl as _ssl

                ssl_ver = str(getattr(_ssl, "OPENSSL_VERSION", "unknown"))
            except Exception:
                pass
            try:
                import requests as _requests

                req_ver = str(getattr(_requests, "__version__", "unknown"))
            except Exception:
                pass
            try:
                import urllib3 as _urllib3  # type: ignore

                u3_ver = str(getattr(_urllib3, "__version__", "unknown"))
            except Exception:
                pass
            try:
                import telebot as _telebot

                tb_ver = str(getattr(_telebot, "__version__", "unknown"))
            except Exception:
                pass

            extra_hint = ""
            if "LibreSSL" in ssl_ver and u3_ver.startswith("2"):
                extra_hint = (
                    "\n\n⚠️ <b>Важное:</b> LibreSSL + urllib3 v2 часто ломают сеть (Telegram/AI).\n"
                    "Решение:\n"
                    "• <code>pip install \"urllib3&lt;2\" --upgrade --force-reinstall</code>\n"
                    "Или используйте Python/venv с OpenSSL (python.org / Homebrew / pyenv)."
                )
            diag = (
                "🧪 Диагностика\n\n"
                f"Python: {py_ver}\n"
                f"ssl: {ssl_ver}\n"
                f"requests: {req_ver}\n"
                f"urllib3: {u3_ver}\n"
                f"pyTelegramBotAPI: {tb_ver}\n\n"
                f"SymPy: {'OK' if SYMPY_AVAILABLE else 'MISSING'}\n"
                f"Plot (numpy+matplotlib): {'OK' if (NUMPY_AVAILABLE and MATPLOTLIB_AVAILABLE) else 'MISSING'}\n"
                f"OCR (pillow + easyocr/tesseract): {'OK' if ocr.available() else 'MISSING'}\n"
                f"AI ключи: {'OK' if (OPENAI_API_KEY or DEEPSEEK_API_KEY) else 'NO_KEYS'}\n"
                f"OFFLINE_MODE: {'ON' if OFFLINE_MODE else 'OFF'}\n\n"
                "Если не работают графики — установите: numpy + matplotlib.\n"
                "Если не работает фото — установите: pillow + easyocr (или pytesseract + tesseract)."
            ) + extra_hint
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔙 К настройкам", callback_data="settings:home"))
            bot.edit_message_text(diag, call.message.chat.id, call.message.message_id, reply_markup=kb)
            bot.answer_callback_query(call.id)
            return

        if data == "settings:home":
            bot.edit_message_text("⚙️ Настройки", call.message.chat.id, call.message.message_id, reply_markup=ikb_settings(), parse_mode="HTML")
            bot.answer_callback_query(call.id)
            return

        if data == "settings:history":
            rows = db.get_history(call.from_user.id, 10)
            if not rows:
                bot.answer_callback_query(call.id, "История пуста")
                bot.send_message(call.message.chat.id, "📋 История пуста.")
                return
            parts = ["📋 <b>История</b> (10)\n"]
            for r in rows:
                parts.append("• <b>%s</b>: <code>%s</code>" % (html_escape(str(r["kind"])), html_escape(str(r["query"])[:40])))
            bot.send_message(call.message.chat.id, "\n".join(parts), parse_mode="HTML")
            bot.answer_callback_query(call.id)
            return

        if data == "settings:clear":
            db.clear_history(call.from_user.id)
            bot.answer_callback_query(call.id, "Очищено")
            bot.send_message(call.message.chat.id, "✅ История очищена.")
            return

        if data.startswith("op:"):
            op = data.split(":", 1)[1]
            set_mode(call.from_user.id, "input_%s" % op)
            bot.answer_callback_query(call.id)
            if op == "eq":
                bot.send_message(
                    call.message.chat.id,
                    "🧮 <b>Решение уравнения</b>\n\n"
                    "Введите уравнение. Примеры:\n"
                    "• <code>2x + 5 = 13</code>\n"
                    "• <code>x^2 - 5x + 6 = 0</code>\n"
                    "• <code>sin(x) = 1/2</code>\n",
                    parse_mode="HTML",
                )
            elif op == "der":
                bot.send_message(
                    call.message.chat.id,
                    "📊 <b>Производная</b>\n\n"
                    "Введите функцию (по x). Примеры:\n"
                    "• <code>x^3 + 2x^2 - 5x + 1</code>\n"
                    "• <code>sin(x)*cos(x)</code>\n"
                    "• <code>exp(2x) + ln(x)</code>\n",
                    parse_mode="HTML",
                )
            elif op == "int":
                bot.send_message(
                    call.message.chat.id,
                    "∫ <b>Интеграл</b>\n\n"
                    "Введите функцию (по x). Примеры:\n"
                    "• <code>x^2</code>\n"
                    "• <code>sin(x)</code>\n"
                    "• <code>1/(1+x^2)</code>\n",
                    parse_mode="HTML",
                )
            elif op == "simp":
                bot.send_message(
                    call.message.chat.id,
                    "📐 <b>Упрощение</b>\n\n"
                    "Введите выражение. Примеры:\n"
                    "• <code>(x+1)^2 - x^2 - 2x</code>\n"
                    "• <code>sin(x)^2 + cos(x)^2</code>\n",
                    parse_mode="HTML",
                )
            elif op == "fact":
                bot.send_message(
                    call.message.chat.id,
                    "🧩 <b>Разложение на множители</b>\n\n"
                    "Введите выражение. Примеры:\n"
                    "• <code>x^2 - 4</code>\n"
                    "• <code>x^2 - 5x + 6</code>\n"
                    "• <code>x^3 - 8</code>\n",
                    parse_mode="HTML",
                )
            else:
                bot.send_message(
                    call.message.chat.id,
                    "📈 <b>Предел</b>\n\n"
                    "Введите как:\n"
                    "• <code>sin(x)/x, x->0</code>\n"
                    "• <code>(x^2-1)/(x-1), x->1</code>\n"
                    "• <code>1/x, x->oo</code>\n",
                    parse_mode="HTML",
                )
            return

        if data.startswith("graph:"):
            kind = data.split(":", 1)[1]
            set_mode(call.from_user.id, "input_graph_%s" % kind)
            bot.answer_callback_query(call.id)
            if kind == "2d":
                bot.send_message(
                    call.message.chat.id,
                    "📈 <b>2D график</b>\n\n"
                    "Введите функцию.\n"
                    "Можно указать диапазон: <code>f(x) xmin xmax</code>\n\n"
                    "Примеры:\n"
                    "• <code>sin(x)</code>\n"
                    "• <code>x^2 -5 5</code>",
                    parse_mode="HTML",
                )
            elif kind == "multi":
                bot.send_message(
                    call.message.chat.id,
                    "📊 <b>Несколько 2D графиков</b>\n\n"
                    "Введите функции через запятую.\n"
                    "Можно указать диапазон в конце: <code>..., xmin xmax</code>\n\n"
                    "Пример:\n"
                    "• <code>x^2, sin(x), cos(x) -5 5</code>",
                    parse_mode="HTML",
                )
            else:
                bot.send_message(
                    call.message.chat.id,
                    "🌐 <b>3D график</b>\n\n"
                    "Введите <code>z = f(x,y)</code>.\n"
                    "Можно указать диапазоны: <code>f(x,y) xmin xmax ymin ymax</code>\n\n"
                    "Пример:\n"
                    "• <code>sin(x)+cos(y) -5 5 -5 5</code>",
                    parse_mode="HTML",
                )
            return

        if data.startswith("mat:"):
            kind = data.split(":", 1)[1]
            set_mode(call.from_user.id, "mat_%s" % kind)
            bot.answer_callback_query(call.id)
            if kind == "mul":
                bot.send_message(call.message.chat.id, "Введите <code>A || B</code>.\nПример: <code>1 2;3 4 || 5 6;7 8</code>", parse_mode="HTML")
            else:
                bot.send_message(call.message.chat.id, "Введите матрицу A.", parse_mode="HTML")
            return

        bot.answer_callback_query(call.id)

    except Exception:
        try:
            bot.answer_callback_query(call.id, "Ошибка")
        except Exception:
            pass


def send_current_task(chat_id: int, sess: PracticeSession, edit_message_id: Optional[int]) -> None:
    t = sess.current()
    if not t:
        bot.send_message(chat_id, "Сессия завершена.", reply_markup=kb_main())
        return
    header = "<b>%s • Задание %d</b>\n<b>%s</b>\n" % (_exam_title(sess.exam), sess.task_num, html_escape(sess.title))
    progress = "\n\n<i>Вопрос %d/%d</i>" % (sess.index + 1, len(sess.tasks))
    # t.prompt может содержать "<" ">" (неравенства) — экранируем для HTML.
    text = header + "\n" + html_escape(t.prompt) + progress
    kb = ikb_task_options(sess.session_id, t.options)
    if edit_message_id is None:
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
    else:
        bot.edit_message_text(text, chat_id, edit_message_id, reply_markup=kb, parse_mode="HTML")


if __name__ == "__main__":
    print("=" * 70)
    print("🚀 MathMaster AI Pro (single-file) starting…")
    print("=" * 70)
    print("DB:", DB_PATH)
    print("Lessons:", db.count_lessons())
    print("SymPy:", "OK" if SYMPY_AVAILABLE else "MISSING")
    print("Plot:", "OK" if (MATPLOTLIB_AVAILABLE and NUMPY_AVAILABLE) else "MISSING")
    print("OCR:", "OK" if ocr.available() else "MISSING")
    print("AI:", "OFFLINE" if OFFLINE_MODE else ("OK" if (OPENAI_API_KEY or DEEPSEEK_API_KEY) else "NO_KEYS"))
    print("=" * 70)
    # авто‑перезапуск polling при сетевых таймаутах
    while True:
        try:
            # timeout (read) должен быть больше long_polling_timeout, иначе будут ReadTimeout.
            bot.infinity_polling(timeout=240, long_polling_timeout=60)
        except Exception as e:
            print("⚠️ polling error:", e)
            time.sleep(5)
